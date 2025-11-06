"""Главное меню и команды мастер-бота"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import get_session, get_master_by_telegram, create_master_account, get_or_create_city
from bot.utils.impersonation import get_impersonation_banner
from bot.utils.geocoding import get_city_from_location, search_city_by_name
from .common import WAITING_CITY_NAME, WAITING_CITY_SELECT
from .onboarding import show_onboarding, get_onboarding_progress

logger = logging.getLogger(__name__)


async def start_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовая команда для мастера"""
    user = update.effective_user
    
    with get_session() as session:
        master = get_master_by_telegram(session, user.id)
        
        if not master:
            # Создаем нового мастера
            name = user.full_name or user.first_name or "Мастер"
            
            # Пытаемся получить фото профиля пользователя
            avatar_file_id = None
            try:
                photos = await context.bot.get_user_profile_photos(user.id, limit=1)
                if photos and photos.total_count > 0:
                    # Берем самое большое фото (последнее в списке, так как они отсортированы по размеру)
                    photo = photos.photos[0][-1]  # photos[0] - массив размеров, [-1] - самый большой
                    avatar_file_id = photo.file_id
                    logger.info(f"Auto-loaded profile photo for master {user.id}: {avatar_file_id}")
            except Exception as e:
                logger.warning(f"Could not get profile photo for user {user.id}: {e}")
            
            # Создаем мастера без города (город определится позже по геолокации)
            master = create_master_account(session, user.id, name, avatar_url=avatar_file_id)
            logger.info(f"Created new master account: {master.id}")
        
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
    if update.message and context.user_data.get('waiting_city_name') and not update.message.location:
        # Пропускаем в receive_city_name
        return None
    
    return None


async def receive_city_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить название города и найти его в интернете"""
    # Проверяем, что это не геолокация (геолокация обрабатывается отдельным handler)
    if update.message and update.message.location:
        return ConversationHandler.END
    
    # Проверяем, ожидаем ли мы ввод города
    if not context.user_data.get('waiting_city_name'):
        # Если не ожидаем, завершаем ConversationHandler
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
    
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_CITY_SELECT


async def select_city_from_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбрать город из результатов поиска"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем индекс города: select_city_0
    city_index = int(query.data.split('_')[2])
    
    cities = context.user_data.get('city_search_results')
    if not cities or city_index >= len(cities):
        await query.message.edit_text("❌ Ошибка: город не найден в результатах поиска.")
        return ConversationHandler.END
    
    city_data = cities[city_index]
    
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
        session.commit()
        
        text = f"✅ <b>Город выбран!</b>\n\n"
        text += f"📍 <b>{city.name_ru}</b>\n"
        if city.country_code:
            text += f"🌍 {city.name_local}\n"
            text += f"🇬🇧 {city.name_en}\n"
        text += f"\nТеперь клиенты смогут найти вас по городу!"
        
        # Очищаем данные
        context.user_data.pop('waiting_city_name', None)
        context.user_data.pop('city_search_results', None)
        context.user_data.pop('city_query', None)
        context.user_data.pop('waiting_location', None)
        context.user_data.pop('master_id', None)
        
        await query.message.edit_text(
            text,
            parse_mode='HTML'
        )
        
        # Показываем анбординг или главное меню
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
            session.commit()
            
            text = f"✅ Город определен: <b>{city.name_ru}</b>\n\n"
            text += f"🇷🇺 {city.name_ru}\n"
            text += f"🌍 {city.name_local}\n"
            text += f"🇬🇧 {city.name_en}\n\n"
            text += "Теперь клиенты смогут найти вас по городу!"
        else:
            text = "⚠️ Не удалось определить город по геолокации.\n\n"
            text += "Вы можете продолжить без указания города."
        
        # Убираем клавиатуру
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Очищаем флаг ожидания геолокации
        context.user_data.pop('waiting_location', None)
        context.user_data.pop('master_id', None)
        
        # Показываем анбординг или главное меню
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

