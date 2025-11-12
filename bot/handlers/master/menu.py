"""Главное меню и команды мастер-бота"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import get_session, get_master_by_telegram, create_master_account, get_or_create_city, add_user_master_link
from bot.database.models import User, MasterAccount
from bot.utils.impersonation import get_impersonation_banner
from bot.utils.geocoding import get_city_from_location, search_city_by_name
from .common import WAITING_CITY_NAME, WAITING_CITY_SELECT, WAITING_REGISTRATION_NAME, WAITING_REGISTRATION_DESCRIPTION, WAITING_REGISTRATION_PHOTO
from .onboarding import show_onboarding, get_onboarding_progress

logger = logging.getLogger(__name__)


async def start_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовая команда для мастера"""
    user = update.effective_user
    
    # Проверяем deep link для приглашения от клиента
    if update.message and context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith('invite_client_'):
            try:
                client_id = int(arg.replace('invite_client_', ''))
                context.user_data['invited_by_client_id'] = client_id
                logger.info(f"Master {user.id} invited by client {client_id}")
            except ValueError:
                logger.error(f"Invalid client_id in invite link: {arg}")
    
    with get_session() as session:
        master = get_master_by_telegram(session, user.id)
        
        if not master:
            # Если мастера нет, запускаем процесс регистрации профиля
            # client_id уже сохранен в context.user_data
            await start_registration(update, context)
            return
        
        # Если мастер уже зарегистрирован и пришел по ссылке приглашения
        invited_by_client_id = context.user_data.get('invited_by_client_id')
        if invited_by_client_id:
            await handle_client_invitation_after_registration(session, master.id, invited_by_client_id, update, context)
            # Очищаем флаг после обработки
            context.user_data.pop('invited_by_client_id', None)
            # Не продолжаем обычный флоу, так как handle_client_invitation_after_registration уже показал меню
            return
        
        # Проверяем, нужно ли запросить город (если у мастера нет city_id)
        if not master.city_id:
            # Сразу запрашиваем геолокацию
            location_keyboard = ReplyKeyboardMarkup(
                [
                    [KeyboardButton("📍 Отправить геолокацию", request_location=True)]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            text = f"👋 Добро пожаловать, <b>{master.name}</b>!\n\n"
            text += "📍 <b>Определение города</b>\n\n"
            text += "Для того, чтобы клиенты могли найти вас, укажите ваш город.\n\n"
            text += "Нажмите кнопку ниже, чтобы отправить геолокацию для автоматического определения города.\n\n"
            text += "💡 <i>Если вы не хотите отправлять геолокацию, просто введите название вашего города в сообщении.</i>"
            
            # Сохраняем в контексте, что ожидаем геолокацию или ввод города
            context.user_data['waiting_location'] = True
            context.user_data['waiting_city_name'] = True  # Также ожидаем ввод текста (если откажется от геолокации)
            context.user_data['master_id'] = master.id
            logger.info(f"Set waiting_location=True, waiting_city_name=True and master_id={master.id} for user {user.id}")
            
            if update.message:
                await update.message.reply_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=location_keyboard
                )
                logger.info(f"Sent location request to user {user.id} via message")
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=location_keyboard
                )
                await update.callback_query.answer()
                logger.info(f"Sent location request to user {user.id} via callback_query")
            
            # Не возвращаем состояние - ConversationHandler активируется автоматически через entry point
            return
        
        # Проверяем статус анбординга
        progress_info = get_onboarding_progress(session, master)
        
        # Если анбординг не завершен, показываем пошаговый анбординг
        if not progress_info['is_complete']:
            await show_onboarding(update, context)
            return
        
        # Если анбординг завершен, показываем главное меню
        text = f"👋 Добро пожаловать, <b>{master.name}</b>!\n\n"
        text += "✅ Настройка завершена!\n\n"
        text += get_impersonation_banner(context)
        
        keyboard = [
            [InlineKeyboardButton("💼 Ваши услуги", callback_data="master_services")],
            [InlineKeyboardButton("📅 Расписание", callback_data="master_schedule")],
            [InlineKeyboardButton("👤➡️ Пригласить клиента", callback_data="master_qr")],
            [InlineKeyboardButton("📋 Записи", callback_data="master_bookings")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")]
        ]
        
        if update.message:
            await update.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif update.callback_query:
            await update.callback_query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.callback_query.answer()


async def master_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик главного меню"""
    return await start_master(update, context)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать регистрацию профиля мастера - шаг 1: имя"""
    user = update.effective_user
    if not user:
        logger.error("[REGISTRATION] No user in update!")
        return
    
    telegram_name = user.full_name or user.first_name or "Мастер"
    
    logger.info(f"[REGISTRATION] Starting registration for user {user.id} ({user.username})")
    
    text = "👋 <b>Добро пожаловать!</b>\n\n"
    text += "Давайте настроим ваш профиль. Это займет всего пару минут.\n\n"
    text += "📝 <b>Шаг 1 из 3: Укажите ваше имя</b>\n\n"
    text += f"Ваше имя в Telegram: <b>{telegram_name}</b>\n\n"
    text += "Вы можете использовать имя из Telegram или ввести свое."
    
    keyboard = [
        [InlineKeyboardButton(f"✅ Использовать '{telegram_name}'", callback_data="use_telegram_name")],
        [InlineKeyboardButton("✏️ Ввести другое имя", callback_data="enter_custom_name")]
    ]
    
    try:
        if update.message:
            logger.info(f"[REGISTRATION] Sending message to user {user.id}")
            await update.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"[REGISTRATION] Message sent successfully to user {user.id}")
        elif update.callback_query:
            logger.info(f"[REGISTRATION] Editing message for user {user.id}")
            await update.callback_query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.callback_query.answer()
            logger.info(f"[REGISTRATION] Message edited successfully for user {user.id}")
        else:
            logger.error(f"[REGISTRATION] No message or callback_query in update for user {user.id}")
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"[REGISTRATION] Error sending message to user {user.id}: {e}", exc_info=True)
        raise
    
    # Сохраняем имя из Telegram для возможного использования
    context.user_data['telegram_name'] = telegram_name
    context.user_data['registration_step'] = 'name'
    
    logger.info(f"[REGISTRATION] Registration started, returning WAITING_REGISTRATION_NAME")
    return WAITING_REGISTRATION_NAME


async def use_telegram_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Использовать имя из Telegram"""
    query = update.callback_query
    if not query:
        logger.error(f"[REGISTRATION] use_telegram_name called without callback_query for user {update.effective_user.id}")
        return ConversationHandler.END
    
    # Отвечаем на callback_query сразу, чтобы Telegram знал, что запрос обработан
    await query.answer()
    
    telegram_name = context.user_data.get('telegram_name', 'Мастер')
    context.user_data['master_name'] = telegram_name
    context.user_data['registration_step'] = 'description'
    
    logger.info(f"[REGISTRATION] User {update.effective_user.id} chose to use Telegram name: {telegram_name}")
    
    # Переходим к шагу 2: описание
    try:
        master_name = context.user_data.get('master_name', 'Мастер')
        
        text = f"✅ Имя установлено: <b>{master_name}</b>\n\n"
        text += "📝 <b>Шаг 2 из 3: Добавьте описание (необязательно)</b>\n\n"
        text += "Расскажите о себе, вашем опыте и услугах.\n"
        text += "Это поможет клиентам лучше вас узнать.\n\n"
        text += "💡 <i>Вы можете пропустить этот шаг и добавить описание позже.</i>"
        
        keyboard = [
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")],
            [InlineKeyboardButton("✏️ Ввести описание", callback_data="enter_description")]
        ]
        
        # Обновляем сообщение
        try:
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"[REGISTRATION] Message edited successfully for user {update.effective_user.id}")
        except Exception as edit_error:
            # Если не удалось отредактировать сообщение (например, MessageNotModified), 
            # отправляем новое сообщение
            logger.warning(f"[REGISTRATION] Could not edit message for user {update.effective_user.id}: {edit_error}")
            try:
                await query.message.reply_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.info(f"[REGISTRATION] New message sent successfully for user {update.effective_user.id}")
            except Exception as send_error:
                logger.error(f"[REGISTRATION] Could not send new message for user {update.effective_user.id}: {send_error}")
                raise
    except Exception as e:
        logger.error(f"[REGISTRATION] Error in use_telegram_name for user {update.effective_user.id}: {e}", exc_info=True)
        try:
            await query.message.reply_text(
                f"❌ Произошла ошибка: {str(e)}\n\nПопробуйте еще раз или введите имя вручную.",
                parse_mode='HTML'
            )
        except:
            pass
        return ConversationHandler.END
    
    logger.info(f"[REGISTRATION] Returning WAITING_REGISTRATION_DESCRIPTION for user {update.effective_user.id}")
    return WAITING_REGISTRATION_DESCRIPTION


async def enter_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросить ввод имени вручную"""
    query = update.callback_query
    await query.answer()
    
    text = "✏️ <b>Введите ваше имя:</b>\n\n"
    text += "Имя будет отображаться в вашем профиле для клиентов."
    
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="back_to_name_choice")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_REGISTRATION_NAME


async def back_to_name_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к выбору имени"""
    query = update.callback_query
    await query.answer()
    
    await start_registration(update, context)
    return WAITING_REGISTRATION_NAME


async def receive_registration_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить имя мастера при регистрации"""
    if not update.message or not update.message.text:
        return WAITING_REGISTRATION_NAME
    
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ Имя слишком короткое. Минимум 2 символа.")
        return WAITING_REGISTRATION_NAME
    
    if len(name) > 100:
        await update.message.reply_text("❌ Имя слишком длинное. Максимум 100 символов.")
        return WAITING_REGISTRATION_NAME
    
    context.user_data['master_name'] = name
    context.user_data['registration_step'] = 'description'
    
    # Переходим к шагу 2: описание
    await start_registration_description(update, context)
    
    return WAITING_REGISTRATION_DESCRIPTION


async def start_registration_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: запрос описания"""
    master_name = context.user_data.get('master_name', 'Мастер')
    
    text = f"✅ Имя установлено: <b>{master_name}</b>\n\n"
    text += "📝 <b>Шаг 2 из 3: Добавьте описание (необязательно)</b>\n\n"
    text += "Расскажите о себе, вашем опыте и услугах.\n"
    text += "Это поможет клиентам лучше вас узнать.\n\n"
    text += "💡 <i>Вы можете пропустить этот шаг и добавить описание позже.</i>"
    
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")],
        [InlineKeyboardButton("✏️ Ввести описание", callback_data="enter_description")]
    ]
    
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.callback_query.answer()


async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросить ввод описания"""
    query = update.callback_query
    await query.answer()
    
    text = "✏️ <b>Введите описание:</b>\n\n"
    text += "Например: 'Опытный мастер маникюра с 5-летним стажем. Специализируюсь на классическом и дизайнерском маникюре.'"
    
    keyboard = [[InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_REGISTRATION_DESCRIPTION


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить описание"""
    query = update.callback_query
    if query:
        await query.answer()
    
    context.user_data['master_description'] = ''
    context.user_data['registration_step'] = 'photo'
    
    # Переходим к шагу 3: фото
    await start_registration_photo(update, context)
    
    return WAITING_REGISTRATION_PHOTO


async def receive_registration_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить описание мастера при регистрации"""
    if not update.message or not update.message.text:
        return WAITING_REGISTRATION_DESCRIPTION
    
    description = update.message.text.strip()
    
    if len(description) > 1000:
        await update.message.reply_text("❌ Описание слишком длинное. Максимум 1000 символов.")
        return WAITING_REGISTRATION_DESCRIPTION
    
    context.user_data['master_description'] = description
    context.user_data['registration_step'] = 'photo'
    
    # Переходим к шагу 3: фото
    await start_registration_photo(update, context)
    
    return WAITING_REGISTRATION_PHOTO


async def start_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 3: запрос фото"""
    master_name = context.user_data.get('master_name', 'Мастер')
    description = context.user_data.get('master_description', '')
    
    text = f"✅ Имя: <b>{master_name}</b>\n"
    if description:
        text += f"✅ Описание: {description[:50]}{'...' if len(description) > 50 else ''}\n\n"
    else:
        text += "✅ Описание: не указано\n\n"
    
    text += "🖼 <b>Шаг 3 из 3: Добавьте фото профиля (необязательно)</b>\n\n"
    text += "Фото поможет клиентам лучше вас запомнить.\n\n"
    text += "💡 <i>Вы можете пропустить этот шаг и добавить фото позже.</i>"
    
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_photo")],
        [InlineKeyboardButton("📷 Загрузить фото", callback_data="upload_registration_photo")]
    ]
    
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.callback_query.answer()


async def upload_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросить загрузку фото"""
    query = update.callback_query
    await query.answer()
    
    text = "📷 <b>Отправьте фото:</b>\n\n"
    text += "Отправьте фото, которое будет отображаться в вашем профиле."
    
    keyboard = [[InlineKeyboardButton("⏭ Пропустить", callback_data="skip_photo")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['uploading_registration_photo'] = True
    return WAITING_REGISTRATION_PHOTO


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить фото и завершить регистрацию"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    context.user_data.pop('uploading_registration_photo', None)
    
    # Проверяем, есть ли фото профиля в Telegram
    try:
        profile_photos = await context.bot.get_user_profile_photos(user_id=user.id, limit=1)
        if profile_photos and profile_photos.total_count > 0:
            # Получаем самое большое фото из профиля
            photo_sizes = profile_photos.photos[0]
            # Берем последний (самый большой) размер
            largest_photo = photo_sizes[-1]
            file_id = largest_photo.file_id
            
            # Сохраняем фото профиля
            context.user_data['master_avatar'] = file_id
            context.user_data['used_telegram_profile_photo'] = True  # Флаг, что использовали фото профиля
            logger.info(f"Using Telegram profile photo for user {user.id}")
        else:
            # Фото профиля нет
            context.user_data['master_avatar'] = None
            context.user_data['used_telegram_profile_photo'] = False
    except Exception as e:
        # Если не удалось получить фото профиля (например, API ошибка)
        logger.warning(f"Could not get profile photo for user {user.id}: {e}")
        context.user_data['master_avatar'] = None
        context.user_data['used_telegram_profile_photo'] = False
    
    # Завершаем регистрацию и создаем мастера
    await finish_registration(update, context)
    
    return ConversationHandler.END


async def receive_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить фото мастера при регистрации"""
    if not update.message or not update.message.photo:
        return WAITING_REGISTRATION_PHOTO
    
    if not context.user_data.get('uploading_registration_photo'):
        return ConversationHandler.END
    
    # Получаем самое большое фото
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    context.user_data['master_avatar'] = file_id
    context.user_data['used_telegram_profile_photo'] = False  # Явно указываем, что фото загружено вручную
    context.user_data.pop('uploading_registration_photo', None)
    
    # Завершаем регистрацию и создаем мастера
    await finish_registration(update, context)
    
    return ConversationHandler.END


async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершить регистрацию и создать мастера"""
    user = update.effective_user
    master_name = context.user_data.get('master_name')
    master_description = context.user_data.get('master_description', '')
    master_avatar = context.user_data.get('master_avatar')
    
    if not master_name:
        logger.error(f"Master name not found in context for user {user.id}")
        error_text = "❌ Ошибка: имя не найдено. Попробуйте начать заново: /start"
        if update.message:
            await update.message.reply_text(error_text)
        elif update.callback_query:
            await update.callback_query.message.reply_text(error_text)
            await update.callback_query.answer()
        return
    
    # Создаем мастера
    with get_session() as session:
        master = create_master_account(
            session,
            user.id,
            master_name,
            description=master_description,
            avatar_url=master_avatar
        )
        logger.info(f"Created new master account: {master.id}")
        
        # Если мастер был приглашен клиентом, создаем связь
        if 'invited_by_client_id' in context.user_data:
            client_id = context.user_data.get('invited_by_client_id')
            await create_client_master_link_after_registration(session, master.id, client_id, update, context)
            context.user_data.pop('invited_by_client_id', None)
        
        # Сохраняем флаг использования фото профиля перед очисткой
        used_profile_photo = context.user_data.get('used_telegram_profile_photo', False)
        
        # Очищаем данные регистрации
        context.user_data.pop('master_name', None)
        context.user_data.pop('master_description', None)
        context.user_data.pop('master_avatar', None)
        context.user_data.pop('telegram_name', None)
        context.user_data.pop('registration_step', None)
        context.user_data.pop('uploading_registration_photo', None)
        context.user_data.pop('used_telegram_profile_photo', None)  # Очищаем флаг после использования
        
        # Показываем сообщение об успешной регистрации
        
        text = "✅ <b>Регистрация завершена!</b>\n\n"
        text += f"👤 Имя: <b>{master.name}</b>\n"
        if master.description:
            text += f"📝 Описание: {master.description}\n"
        
        # Информация о фото
        if master.avatar_url:
            if used_profile_photo:
                text += f"🖼 Фото: ✅ Использовано фото профиля Telegram\n\n"
            else:
                text += f"🖼 Фото: ✅ Загружено\n\n"
        else:
            text += f"🖼 Фото: ⏭ Не добавлено\n\n"
        
        text += "📍 Теперь укажите ваш город, чтобы клиенты могли вас найти."
        
        # Запрашиваем город
        location_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("📍 Отправить геолокацию", request_location=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        # Сохраняем в контексте, что ожидаем геолокацию или ввод города
        context.user_data['waiting_location'] = True
        context.user_data['waiting_city_name'] = True
        context.user_data['master_id'] = master.id
        
        # Определяем, откуда пришел update
        if update.message:
            await update.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=location_keyboard
            )
        elif update.callback_query:
            # Если пришло из callback_query, редактируем сообщение или отправляем новое
            try:
                await update.callback_query.message.edit_text(
                    text,
                    parse_mode='HTML'
                )
                await update.callback_query.message.reply_text(
                    "📍 Отправьте геолокацию или введите название города:",
                    reply_markup=location_keyboard
                )
            except Exception as e:
                # Если не удалось отредактировать (например, сообщение слишком старое), отправляем новое
                logger.warning(f"Could not edit message, sending new one: {e}")
                await update.callback_query.message.reply_text(
                    text + "\n\n📍 Отправьте геолокацию или введите название города:",
                    parse_mode='HTML',
                    reply_markup=location_keyboard
                )
            await update.callback_query.answer()


async def start_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать ввод города вручную (entry point для ConversationHandler)"""
    # Проверяем, что это кнопка "Ввести город вручную" (для обратной совместимости)
    if update.message and update.message.text == "✏️ Ввести город вручную":
        text = "✏️ <b>Ввод города вручную</b>\n\n"
        text += "Введите название вашего города:\n\n"
        text += "Например: Москва, Санкт-Петербург, Казань"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data="cancel_city_input")]]
        
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Сохраняем флаг ожидания ввода города
        context.user_data['waiting_city_name'] = True
        if 'master_id' not in context.user_data:
            # Если master_id не установлен, получаем его из сессии
            with get_session() as session:
                user = update.effective_user
                master = get_master_by_telegram(session, user.id)
                if master:
                    context.user_data['master_id'] = master.id
        
        return WAITING_CITY_NAME
    
    # Если это обычный текст и мы ожидаем ввод города (из start_master)
    # НО не создаем услугу в данный момент
    if (update.message and 
        context.user_data.get('waiting_city_name') and 
        not update.message.location and
        'service_name' not in context.user_data and
        'service_price' not in context.user_data):
        # Активируем ConversationHandler, передавая управление receive_city_name
        logger.info("Activating city input conversation from start_city_input")
        return WAITING_CITY_NAME
    
    return None


async def check_city_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка, нужно ли активировать ConversationHandler для ввода города"""
    # Проверяем, что это текстовое сообщение
    if not update.message or not update.message.text:
        return None
    
    # Проверяем, что ожидается ввод города
    if not context.user_data.get('waiting_city_name'):
        return None
    
    # Проверяем, что пользователь НЕ создает услугу
    if 'service_name' in context.user_data or 'service_price' in context.user_data:
        logger.debug("User is creating service, not activating city input")
        return None
    
    # Если это не команда и не геолокация - активируем ввод города
    if not update.message.location:
        logger.info("Activating city input conversation - user entered city name")
        return WAITING_CITY_NAME
    
    return None


async def receive_city_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить название города и найти его в интернете"""
    # Проверяем, что это не геолокация (геолокация обрабатывается отдельным handler)
    if update.message and update.message.location:
        return ConversationHandler.END
    
    # Проверяем, ожидаем ли мы ввод города
    if not context.user_data.get('waiting_city_name'):
        # Если не ожидаем, завершаем ConversationHandler, чтобы не перехватывать другие сообщения
        return ConversationHandler.END
    
    # Дополнительная проверка: если пользователь находится в процессе создания услуги,
    # не перехватываем сообщения о цене, длительности и т.д.
    # Проверяем, есть ли активные состояния для добавления услуги
    if 'service_name' in context.user_data or 'service_price' in context.user_data:
        # Пользователь создает услугу - не перехватываем
        logger.debug("User is creating service, not intercepting city input")
        return ConversationHandler.END
    
    # Проверяем, что это текст (не команда и не кнопка)
    if not update.message or not update.message.text:
        return ConversationHandler.END
    
    city_query = update.message.text.strip()
    
    if len(city_query) < 2:
        await update.message.reply_text(
            "❌ Название города слишком короткое. Введите минимум 2 символа.",
            parse_mode='HTML'
        )
        return WAITING_CITY_NAME
    
    # Ищем город в интернете
    await update.message.reply_text("🔍 Ищу город в интернете...")
    
    cities = search_city_by_name(city_query, limit=10)
    
    if not cities:
        text = f"❌ Не удалось найти город по запросу: <b>{city_query}</b>\n\n"
        text += "Попробуйте:\n"
        text += "• Указать более точное название\n"
        text += "• Использовать другое написание\n"
        text += "• Отправить геолокацию вместо ввода"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать еще раз", callback_data="retry_city_input")],
            [InlineKeyboardButton("« Отмена", callback_data="cancel_city_input")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_CITY_NAME
    
    # Сохраняем результаты поиска в контексте
    context.user_data['city_search_results'] = cities
    context.user_data['city_query'] = city_query
    
    # Показываем список найденных городов
    text = f"🔍 <b>Найдено городов: {len(cities)}</b>\n\n"
    text += "Выберите ваш город:\n\n"
    
    # Словарь сокращений типов населенных пунктов
    city_type_abbr = {
        'city': 'г.',
        'town': 'пгт.',
        'village': 'д.',
        'municipality': 'м.',
        'city_district': 'р-н'
    }
    
    keyboard = []
    for i, city in enumerate(cities[:10], 1):  # Показываем максимум 10
        # Формируем текст кнопки: тип, название города, страна
        city_type = city.get('city_type', 'city')
        type_abbr = city_type_abbr.get(city_type, 'г.')
        
        city_label = f"{type_abbr} {city['name_ru']}"
        if city.get('country'):
            city_label += f", {city['country']}"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{i}. {city_label}",
                callback_data=f"select_city_{i-1}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Искать другой город", callback_data="retry_city_input"),
        InlineKeyboardButton("« Отмена", callback_data="cancel_city_input")
    ])
    
    message = await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"City search results shown, returning WAITING_CITY_SELECT state. Found {len(cities)} cities.")
    logger.info(f"City search results saved to context: {[c.get('name_ru', 'Unknown') for c in cities[:5]]}")
    
    return WAITING_CITY_SELECT


async def select_city_from_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбрать город из результатов поиска"""
    try:
        logger.info(f"=== select_city_from_search called ===")
        logger.info(f"Update type: {type(update)}")
        logger.info(f"Has callback_query: {update.callback_query is not None}")
        
        if update.callback_query:
            logger.info(f"Callback query data: {update.callback_query.data}")
        else:
            logger.error("select_city_from_search: No callback_query in update")
            return ConversationHandler.END
        
        query = update.callback_query
        await query.answer()
        
        # Извлекаем индекс города: select_city_0
        try:
            city_index = int(query.data.split('_')[2])
            logger.info(f"Selected city index: {city_index}")
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing city index from callback_data '{query.data}': {e}")
            await query.message.edit_text("❌ Ошибка: неверный формат данных.")
            return ConversationHandler.END
        
        cities = context.user_data.get('city_search_results')
        logger.info(f"City search results in context: {len(cities) if cities else 0} cities")
        logger.info(f"Context user_data keys: {list(context.user_data.keys())}")
        
        if not cities:
            logger.error("No city search results in context.user_data")
            await query.message.edit_text("❌ Ошибка: результаты поиска городов не найдены. Попробуйте поискать город заново.")
            # Попробуем вернуться к поиску города
            await start_city_input(update, context)
            return WAITING_CITY_NAME
        
        if city_index >= len(cities):
            logger.error(f"City index {city_index} is out of range. Total cities: {len(cities)}")
            await query.message.edit_text(f"❌ Ошибка: неверный индекс города. Попробуйте выбрать город из списка.")
            return WAITING_CITY_SELECT
        
        city_data = cities[city_index]
        logger.info(f"Selected city: {city_data.get('name_ru', 'Unknown')}")
    except Exception as e:
        logger.error(f"Unexpected error in select_city_from_search: {e}", exc_info=True)
        if update.callback_query:
            try:
                await update.callback_query.message.edit_text("❌ Произошла ошибка при выборе города. Попробуйте еще раз.")
            except:
                pass
        return ConversationHandler.END
    
    with get_session() as session:
        master_id = context.user_data.get('master_id')
        if not master_id:
            user = update.effective_user
            master = get_master_by_telegram(session, user.id)
            if master:
                master_id = master.id
            else:
                await query.message.edit_text("❌ Ошибка: мастер не найден.")
                return ConversationHandler.END
        
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Ошибка: мастер не найден.")
            return ConversationHandler.END
        
        # Создаем или получаем город
        city = get_or_create_city(
            session,
            name_ru=city_data['name_ru'],
            name_local=city_data['name_local'],
            name_en=city_data['name_en'],
            latitude=city_data['latitude'],
            longitude=city_data['longitude'],
            country_code=city_data['country_code']
        )
        
        # Привязываем город к мастеру
        master.city_id = city.id
        
        # Обновляем сообщение, чтобы показать, что бот обрабатывает запрос
        try:
            await query.message.edit_text(
                f"⍱ Обрабатываем...",
                parse_mode='HTML'
            )
        except Exception:
            pass  # Игнорируем ошибки при обновлении сообщения
        
        # Автоматически определяем и обновляем валюту на основе страны города
        # Используем асинхронную версию, которая проверяет БД и запрашивает API
        if city.country_code:
            try:
                from bot.utils.currency import get_currency_by_country_async
                import asyncio
                
                # Добавляем общий таймаут для запроса валюты (30 секунд)
                # Если запрос зависает, используем fallback
                try:
                    currency = await asyncio.wait_for(
                        get_currency_by_country_async(session, city.country_code),
                        timeout=30.0
                    )
                    master.currency = currency
                    logger.info(f"Currency {currency} set for master {master_id} based on country {city.country_code}")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout while fetching currency for country {city.country_code}, using RUB fallback")
                    master.currency = 'RUB'  # Fallback на рубли
                except Exception as e:
                    logger.error(f"Error fetching currency for country {city.country_code}: {e}", exc_info=True)
                    master.currency = 'RUB'  # Fallback на рубли
            except Exception as e:
                logger.error(f"Unexpected error while setting currency: {e}", exc_info=True)
                master.currency = 'RUB'  # Fallback на рубли
        else:
            # Если нет кода страны, используем RUB по умолчанию
            master.currency = 'RUB'
        
        session.commit()
        session.refresh(master)  # Обновляем объект мастера после коммита
        
        # Очищаем данные
        context.user_data.pop('waiting_city_name', None)
        context.user_data.pop('city_search_results', None)
        context.user_data.pop('city_query', None)
        context.user_data.pop('waiting_location', None)
        context.user_data.pop('master_id', None)
        
        await query.message.edit_text(
            "✅ Город выбран!",
            parse_mode='HTML'
        )
        
        # Показываем анбординг или главное меню
        # Обновляем объект мастера перед проверкой прогресса
        session.refresh(master)
        progress_info = get_onboarding_progress(session, master)
        if not progress_info['is_complete']:
            await show_onboarding(update, context)
        else:
            # Показываем главное меню
            menu_text = f"👋 Добро пожаловать, <b>{master.name}</b>!\n\n"
            menu_text += "✅ Настройка завершена!\n\n"
            menu_text += get_impersonation_banner(context)
            
            keyboard = [
                [InlineKeyboardButton("💼 Ваши услуги", callback_data="master_services")],
                [InlineKeyboardButton("📅 Расписание", callback_data="master_schedule")],
                [InlineKeyboardButton("👤➡️ Пригласить клиента", callback_data="master_qr")],
                [InlineKeyboardButton("📋 Записи", callback_data="master_bookings")],
                [InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")]
            ]
            
            await query.message.reply_text(
                menu_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    return ConversationHandler.END


async def retry_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторить ввод города"""
    query = update.callback_query
    if query:
        await query.answer()
    
    text = "✏️ <b>Ввод города вручную</b>\n\n"
    text += "Введите название вашего города:\n\n"
    text += "Например: Москва, Санкт-Петербург, Казань"
    
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="cancel_city_input")]]
    
    if query:
        try:
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            await query.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    context.user_data['waiting_city_name'] = True
    return WAITING_CITY_NAME


async def cancel_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить ввод города"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Очищаем данные
    context.user_data.pop('waiting_city_name', None)
    context.user_data.pop('city_search_results', None)
    context.user_data.pop('city_query', None)
    
    text = "❌ Ввод города отменен.\n\n"
    text += "Вы можете продолжить без указания города или указать его позже в настройках."
    
    keyboard = [
        [InlineKeyboardButton("« Главное меню", callback_data="master_menu")]
    ]
    
    if query:
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return ConversationHandler.END


async def handle_test_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Специальный обработчик для тестового города (для E2E тестов)"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    
    # Проверяем, что это тестовый город
    if text != "тестовый123123123129543":
        return
    
    logger.info(f"Test city input detected for user {update.effective_user.id}")
    
    # Получаем или создаем тестовый город в БД
    from bot.database.db import get_session, get_city_by_name, create_city, get_master_by_telegram, update_master
    
    with get_session() as session:
        # Ищем тестовый город
        test_city = get_city_by_name(session, "Тестовый Город")
        
        if not test_city:
            # Создаем тестовый город
            test_city = create_city(
                session,
                name="Тестовый Город",
                latitude=55.7558,  # Москва
                longitude=37.6173,
                country="Россия",
                timezone="Europe/Moscow"
            )
            logger.info(f"Created test city: {test_city.name} (id={test_city.id})")
        
        # Получаем мастера
        master = get_master_by_telegram(session, update.effective_user.id)
        
        if master:
            # Обновляем город мастера
            update_master(session, master.id, city_id=test_city.id)
            logger.info(f"Updated master {master.id} with test city {test_city.id}")
            
            # Очищаем флаги ожидания
            context.user_data.pop('waiting_location', None)
            context.user_data.pop('waiting_city_name', None)
            
            # Отправляем подтверждение
            text = f"✅ Город установлен: <b>{test_city.name}</b>\n\n"
            text += "Теперь вы можете добавлять услуги и принимать записи!"
            
            from telegram import ReplyKeyboardRemove
            await update.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Показываем главное меню
            from bot.handlers.master.menu import show_master_menu
            await show_master_menu(update, context)
        else:
            logger.error(f"Master not found for user {update.effective_user.id}")
            await update.message.reply_text(
                "❌ Ошибка: мастер не найден. Попробуйте начать заново: /start",
                parse_mode='HTML'
            )


async def receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения геолокации для определения города"""
    logger.info(f"receive_location called for user {update.effective_user.id}, waiting_location={context.user_data.get('waiting_location')}")
    if not context.user_data.get('waiting_location'):
        logger.info(f"Not waiting for location, ignoring")
        return
    
    location = update.message.location
    if not location:
        await update.message.reply_text(
            "❌ Не удалось получить геолокацию. Попробуйте еще раз.",
            parse_mode='HTML'
        )
        return
    
    latitude = location.latitude
    longitude = location.longitude
    
    # Определяем город по геолокации
    city_data = get_city_from_location(latitude, longitude)
    
    with get_session() as session:
        master_id = context.user_data.get('master_id')
        if not master_id:
            await update.message.reply_text("❌ Ошибка: не найден ID мастера.")
            return
        
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await update.message.reply_text("❌ Ошибка: мастер не найден.")
            return
        
        if city_data:
            # Создаем или получаем город
            city = get_or_create_city(
                session,
                name_ru=city_data['name_ru'],
                name_local=city_data['name_local'],
                name_en=city_data['name_en'],
                latitude=city_data['latitude'],
                longitude=city_data['longitude'],
                country_code=city_data['country_code']
            )
            
            # Привязываем город к мастеру
            master.city_id = city.id
            
            # Автоматически определяем и обновляем валюту на основе страны города
            # Используем асинхронную версию, которая проверяет БД и запрашивает API
            if city.country_code:
                try:
                    from bot.utils.currency import get_currency_by_country_async
                    import asyncio
                    
                    # Добавляем общий таймаут для запроса валюты (30 секунд)
                    # Если запрос зависает, используем fallback
                    try:
                        currency = await asyncio.wait_for(
                            get_currency_by_country_async(session, city.country_code),
                            timeout=30.0
                        )
                        master.currency = currency
                        logger.info(f"Currency {currency} set for master {master_id} based on country {city.country_code}")
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout while fetching currency for country {city.country_code}, using RUB fallback")
                        master.currency = 'RUB'  # Fallback на рубли
                    except Exception as e:
                        logger.error(f"Error fetching currency for country {city.country_code}: {e}", exc_info=True)
                        master.currency = 'RUB'  # Fallback на рубли
                except Exception as e:
                    logger.error(f"Unexpected error while setting currency: {e}", exc_info=True)
                    master.currency = 'RUB'  # Fallback на рубли
            else:
                # Если нет кода страны, используем RUB по умолчанию
                master.currency = 'RUB'
            
            session.commit()
            session.refresh(master)  # Обновляем объект мастера после коммита
        
        # Очищаем флаг ожидания геолокации
        context.user_data.pop('waiting_location', None)
        context.user_data.pop('master_id', None)
        
        # Убираем клавиатуру
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(
            "✅ Город определен!",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Показываем анбординг или главное меню
        # Обновляем объект мастера перед проверкой прогресса
        session.refresh(master)
        progress_info = get_onboarding_progress(session, master)
        if not progress_info['is_complete']:
            await show_onboarding(update, context)
        else:
            # Показываем главное меню
            menu_text = f"👋 Добро пожаловать, <b>{master.name}</b>!\n\n"
            menu_text += "✅ Настройка завершена!\n\n"
            menu_text += get_impersonation_banner(context)
            
            keyboard = [
                [InlineKeyboardButton("💼 Ваши услуги", callback_data="master_services")],
                [InlineKeyboardButton("📅 Расписание", callback_data="master_schedule")],
                [InlineKeyboardButton("👤➡️ Пригласить клиента", callback_data="master_qr")],
                [InlineKeyboardButton("📋 Записи", callback_data="master_bookings")],
                [InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")]
            ]
            
            await update.message.reply_text(
                menu_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def master_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройки мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    text = "⚙️ <b>Настройки</b>\n\n"
    text += "• Профиль\n"
    text += "• Подписка\n"
    text += get_impersonation_banner(context)
    
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="master_profile")],
        [InlineKeyboardButton("💎 Подписка", callback_data="master_premium")],
        [InlineKeyboardButton("« Назад", callback_data="master_menu")]
    ]
    
    if query:
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.message:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def create_client_master_link_after_registration(session, master_id: int, client_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать связь между клиентом и мастером после регистрации мастера"""
    try:
        # Получаем клиента по ID
        client_user = session.query(User).filter_by(id=client_id).first()
        if not client_user:
            logger.warning(f"Client with id={client_id} not found")
            return
        
        # Получаем мастера
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        if not master:
            logger.warning(f"Master with id={master_id} not found")
            return
        
        # Создаем связь
        add_user_master_link(session, client_user, master)
        logger.info(f"Created link between client {client_id} and master {master_id}")
        
        # Отправляем уведомление мастеру (если это возможно)
        text = "✅ <b>Вы успешно зарегистрированы!</b>\n\n"
        text += "🎉 Отлично! Вы были приглашены клиентом и автоматически добавлены в его список мастеров.\n\n"
        text += "Теперь этот клиент сможет записаться к вам на услуги!"
        
        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error creating client-master link: {e}", exc_info=True)


async def handle_client_invitation_after_registration(session, master_id: int, client_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать приглашение от клиента для уже зарегистрированного мастера"""
    try:
        # Получаем клиента по ID
        client_user = session.query(User).filter_by(id=client_id).first()
        if not client_user:
            logger.warning(f"Client with id={client_id} not found")
            text = "❌ Клиент, который вас пригласил, не найден в системе."
            if update.message:
                await update.message.reply_text(text, parse_mode='HTML')
            elif update.callback_query:
                await update.callback_query.message.reply_text(text, parse_mode='HTML')
            return
        
        # Получаем мастера
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        if not master:
            logger.warning(f"Master with id={master_id} not found")
            return
        
        # Проверяем, не добавлен ли уже этот клиент
        from bot.database.models import UserMaster
        existing_link = session.query(UserMaster).filter_by(
            user_id=client_user.id,
            master_account_id=master.id
        ).first()
        
        if existing_link:
            text = "✅ <b>Этот клиент уже в вашем списке!</b>\n\n"
            text += "Клиент, который вас пригласил, уже может записаться к вам на услуги."
        else:
            # Создаем связь
            add_user_master_link(session, client_user, master)
            logger.info(f"Created link between client {client_id} and master {master_id}")
            text = "✅ <b>Клиент добавлен в ваш список!</b>\n\n"
            text += "🎉 Отлично! Клиент, который вас пригласил, теперь может записаться к вам на услуги."
        
        # Отправляем уведомление
        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode='HTML')
            await update.callback_query.answer()
        
        # Показываем главное меню через стандартный флоу
        # Используем get_onboarding_progress из импорта в начале файла
        progress_info = get_onboarding_progress(session, master)
        
        if not progress_info['is_complete']:
            from .onboarding import show_onboarding
            # Временно убираем флаг приглашения, чтобы не зациклиться
            temp_flag = context.user_data.pop('invited_by_client_id', None)
            await show_onboarding(update, context)
            if temp_flag:
                context.user_data['invited_by_client_id'] = temp_flag
        else:
            menu_text = f"👋 Добро пожаловать, <b>{master.name}</b>!\n\n✅ Настройка завершена!\n\n"
            menu_text += get_impersonation_banner(context)
            keyboard = [
                [InlineKeyboardButton("💼 Ваши услуги", callback_data="master_services")],
                [InlineKeyboardButton("📅 Расписание", callback_data="master_schedule")],
                [InlineKeyboardButton("👤➡️ Пригласить клиента", callback_data="master_qr")],
                [InlineKeyboardButton("📋 Записи", callback_data="master_bookings")],
                [InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")]
            ]
            if update.message:
                await update.message.reply_text(
                    menu_text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    menu_text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
    except Exception as e:
        logger.error(f"Error handling client invitation: {e}", exc_info=True)

