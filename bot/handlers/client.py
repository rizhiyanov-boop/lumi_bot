"""Обработчики для клиентского бота"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import (
    get_session,
    get_or_create_user,
    get_master_by_telegram,
    add_user_master_link,
    remove_user_master_link,
    get_client_masters,
    get_services_by_master,
    get_bookings_for_client,
    create_booking,
    check_booking_conflict,
    get_portfolio_photos,
    get_all_cities,
    get_masters_by_city
)
from bot.utils.schedule_utils import get_available_time_slots, has_available_slots_on_date, format_time
from datetime import datetime, timedelta, date
from bot.database.models import Service
from bot.config import BOT_TOKEN
from telegram import Bot
import logging

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler бронирования
WAITING_BOOKING_DATE, WAITING_BOOKING_TIME, WAITING_BOOKING_COMMENT = range(3)


async def start_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовая команда для клиентского бота"""
    user = update.effective_user
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        
        # Проверяем deep link
        logger.info(f"Start command received. User: {user.id}, args: {context.args}")
        
        if context.args and len(context.args) > 0:
            arg = context.args[0]
            logger.info(f"Processing deep link argument: {arg}")
            
            # Формат: payment_return_MASTER_ID (возврат после оплаты)
            if arg.startswith('payment_return_'):
                try:
                    master_id_str = arg.replace('payment_return_', '')
                    master_id = int(master_id_str)
                    logger.info(f"Payment return for master_id: {master_id}")
                    
                    # Импортируем функции для работы с платежами
                    from bot.database.db import get_master_by_id, get_payment_by_id
                    from bot.utils.yookassa_api import get_payment_status
                    from bot.database.db import update_payment_status, update_master_subscription
                    from bot.config import PREMIUM_DURATION_DAYS
                    from datetime import datetime, timedelta
                    
                    master = get_master_by_id(session, master_id)
                    if not master:
                        await update.message.reply_text(
                            "❌ Мастер не найден",
                            parse_mode='HTML'
                        )
                        return
                    
                    # Ищем последний pending платеж для этого мастера
                    from bot.database.models import Payment
                    payment = session.query(Payment).filter_by(
                        master_account_id=master_id,
                        status='pending'
                    ).order_by(Payment.created_at.desc()).first()
                    
                    if payment:
                        # Проверяем статус платежа
                        payment_data = get_payment_status(payment.payment_id)
                        if payment_data:
                            status = payment_data.get('status')
                            paid = payment_data.get('paid', False)
                            
                            if status != payment.status:
                                paid_at = None
                                if status == 'succeeded' and paid:
                                    paid_at = datetime.utcnow()
                                
                                update_payment_status(session, payment.payment_id, status, paid_at)
                                
                                if status == 'succeeded' and paid:
                                    expires_at = datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)
                                    update_master_subscription(session, master_id, 'premium', expires_at)
                                    
                                    await update.message.reply_text(
                                        "✅ <b>Оплата успешно завершена!</b>\n\n"
                                        f"⭐ Премиум подписка активирована на {PREMIUM_DURATION_DAYS} дней.\n\n"
                                        "Спасибо за покупку!",
                                        parse_mode='HTML'
                                    )
                                    return
                    
                    await update.message.reply_text(
                        "💳 <b>Оплата обрабатывается</b>\n\n"
                        "Если оплата уже прошла, подписка будет активирована автоматически.\n"
                        "Если есть проблемы, свяжитесь с поддержкой.",
                        parse_mode='HTML'
                    )
                    return
                except Exception as e:
                    logger.error(f"Error processing payment return: {e}", exc_info=True)
                    await update.message.reply_text(
                        "❌ Ошибка обработки возврата после оплаты",
                        parse_mode='HTML'
                    )
                    return
            
            # Формат: m_MASTER_ID (сокращенный) или master_TELEGRAM_ID (старый формат для обратной совместимости)
            if arg.startswith('m_') or arg.startswith('master_'):
                try:
                    from bot.database.db import get_master_by_id
                    
                    if arg.startswith('m_'):
                        # Новый формат: m_MASTER_ID
                        master_id_str = arg.replace('m_', '')
                        logger.info(f"Extracted master_id string: {master_id_str}")
                        
                        master_id = int(master_id_str)
                        logger.info(f"Looking for master with id: {master_id}")
                        
                        master = get_master_by_id(session, master_id)
                    else:
                        # Старый формат: master_TELEGRAM_ID (для обратной совместимости)
                        master_telegram_id_str = arg.replace('master_', '')
                        logger.info(f"Extracted master_telegram_id string: {master_telegram_id_str}")
                        
                        master_telegram_id = int(master_telegram_id_str)
                        logger.info(f"Looking for master with telegram_id: {master_telegram_id}")
                        
                        master = get_master_by_telegram(session, master_telegram_id)
                    
                    if master:
                        logger.info(f"Master found: {master.name} (id={master.id}, telegram_id={master.telegram_id})")
                        
                        # Проверяем, не пытается ли пользователь добавить самого себя
                        if master.telegram_id == user.id:
                            logger.warning(f"User {user.id} trying to add themselves as master (allowed but unusual)")
                        
                        # Добавляем связь
                        link = add_user_master_link(session, client_user, master)
                        logger.info(f"Link created/retrieved: user_id={link.user_id}, master_id={link.master_account_id}")
                        
                        text = f"""✅ <b>Мастер добавлен!</b>

👤 <b>{master.name}</b>
📝 {master.description or '<i>Описание не указано</i>'}

Теперь вы можете записаться к этому мастеру!"""
                        
                        keyboard = [
                            [InlineKeyboardButton("💼 Услуги мастера", callback_data=f"view_master_{master.id}")],
                            [InlineKeyboardButton("📋 Записаться", callback_data=f"book_master_{master.id}")],
                            [InlineKeyboardButton("« Мои мастера", callback_data="client_masters")]
                        ]
                        
                        # Пытаемся отправить фото профиля мастера, если оно есть
                        if master.avatar_url:
                            try:
                                from bot.config import BOT_TOKEN
                                from telegram import Bot as TelegramBot
                                import io
                                import asyncio
                                import requests
                                
                                # Скачиваем фото профиля через мастер-бот, так как file_id не работает между разными ботами
                                master_bot = TelegramBot(token=BOT_TOKEN)
                                file = await master_bot.get_file(master.avatar_url)
                                file_path = file.file_path
                                
                                # Убираем возможный префикс, если он есть
                                if file_path.startswith('https://api.telegram.org/file/bot'):
                                    parts = file_path.split('/file/bot')
                                    if len(parts) > 1:
                                        path_after_token = parts[1].split('/', 1)
                                        if len(path_after_token) > 1:
                                            file_path = path_after_token[1]
                                
                                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                                
                                def download_file(url):
                                    response = requests.get(url, timeout=30)
                                    response.raise_for_status()
                                    return response.content
                                
                                file_content = await asyncio.to_thread(download_file, file_url)
                                photo_data = io.BytesIO(file_content)
                                photo_data.seek(0)
                                
                                # Отправляем фото с подписью и кнопками
                                await update.message.reply_photo(
                                    photo=photo_data,
                                    caption=text,
                                    parse_mode='HTML',
                                    reply_markup=InlineKeyboardMarkup(keyboard)
                                )
                                return
                            except Exception as e:
                                logger.warning(f"Could not send master avatar photo: {e}, sending text message instead")
                                # Если не получилось отправить фото, отправляем просто текст
                        
                        # Если фото нет или не удалось отправить, отправляем просто текст
                        await update.message.reply_text(
                            text,
                            parse_mode='HTML',
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        return
                    else:
                        if arg.startswith('m_'):
                            logger.warning(f"Master with id={master_id} not found in database")
                        else:
                            logger.warning(f"Master with telegram_id={master_telegram_id} not found in database")
                        await update.message.reply_text(
                            f"❌ Мастер не найден.\n\nПроверьте правильность ссылки.",
                            parse_mode='HTML'
                        )
                        return
                except ValueError as e:
                    logger.error(f"Error parsing master ID: {e}")
                    await update.message.reply_text(
                        f"❌ Ошибка обработки ссылки: неверный формат ID мастера.",
                        parse_mode='HTML'
                    )
                    return
                except Exception as e:
                    logger.error(f"Unexpected error processing deep link: {e}", exc_info=True)
                    await update.message.reply_text(
                        f"❌ Произошла ошибка при добавлении мастера: {str(e)}",
                        parse_mode='HTML'
                    )
                    return
        
        # Обычный старт без deep link
        masters = get_client_masters(session, client_user)
        
        text = f"""👋 <b>Добро пожаловать в Lumi Beauty!</b>

Здесь вы можете:
• Добавлять мастеров по QR-коду или ссылке
• Просматривать услуги и цены
• Записываться на удобное время
• Управлять своими записями

📊 <b>Ваша статистика:</b>
👥 Добавлено мастеров: {len(masters)}

Выберите действие:"""
    
        keyboard = get_client_menu_buttons()
    
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def client_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список мастеров клиента с выбором"""
    query = update.callback_query
    if query:
        await query.answer()
    user = update.effective_user
    
    # Извлекаем данные мастеров внутри сессии
    masters_data = []
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        links = get_client_masters(session, client_user)
        
        if not links:
            text = "👥 <b>Мои мастера</b>\n\nУ вас пока нет добавленных мастеров.\n\nПопросите мастера отправить вам QR-код или ссылку для записи!"
            keyboard = [
                [InlineKeyboardButton("« Назад", callback_data="client_menu")]
            ]
            
            if query:
                try:
                    if query.message.photo:
                        await query.message.delete()
                    await query.message.reply_text(
                        text,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception:
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
            return
        
        # Извлекаем данные мастеров внутри сессии
        for link in links:
            master = link.master_account
            services = get_services_by_master(session, master.id, active_only=True)
            
            # Формируем список услуг для мастера
            services_list = []
            for svc in services:
                services_list.append({
                    'title': svc.title,
                    'price': svc.price,
                    'duration': svc.duration_mins
                })
            
            masters_data.append({
                'id': master.id,
                'name': master.name,
                'description': master.description or '',
                'avatar_url': master.avatar_url,
                'services': services_list,
                'services_count': len(services_list),
                'telegram_id': master.telegram_id
            })
    
    # Формируем список мастеров с подробной информацией
    text = "👥 <b>Мои мастера</b>\n\n"
    text += "Выберите мастера:\n\n"
    
    # Добавляем информацию о каждом мастере
    MAX_MESSAGE_LENGTH = 4000  # Оставляем запас для HTML-тегов
    for i, master_info in enumerate(masters_data, 1):
        master_text = f"<b>{i}. 👤 {master_info['name']}</b>\n"
        
        # Описание
        if master_info['description']:
            # Ограничиваем длину описания для компактности
            desc = master_info['description']
            if len(desc) > 100:
                desc = desc[:97] + "..."
            master_text += f"📝 {desc}\n"
        else:
            master_text += f"📝 <i>Описание не указано</i>\n"
        
        # Услуги
        if master_info['services']:
            master_text += f"💼 <b>Услуги ({master_info['services_count']}):</b>\n"
            # Показываем первые 5 услуг для компактности
            for svc in master_info['services'][:5]:
                master_text += f"  • {svc['title']} — {svc['price']}₽ ({svc['duration']} мин)\n"
            if master_info['services_count'] > 5:
                master_text += f"  <i>... и еще {master_info['services_count'] - 5}</i>\n"
        else:
            master_text += f"💼 <i>Услуги не добавлены</i>\n"
        
        master_text += "\n"
        
        # Проверяем, не превысит ли добавление этого мастера лимит
        if len(text) + len(master_text) > MAX_MESSAGE_LENGTH:
            text += f"\n<i>... и еще {len(masters_data) - i + 1} мастер(ов)</i>"
            break
        
        text += master_text
    
    keyboard = []
    for master_info in masters_data:
        # Добавляем кнопку для каждого мастера
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {master_info['name']}",
                callback_data=f"view_master_{master_info['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("« Назад", callback_data="client_menu")
    ])
    
    # Отправляем список
    if query:
        try:
            if query.message.photo:
                await query.message.delete()
        except Exception:
            pass
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


async def view_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр профиля мастера"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[2])
    
    # Извлекаем все необходимые данные внутри сессии
    master_name = None
    master_description = None
    services_data = []
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        # Проверяем блокировку
        if master.is_blocked:
            await query.message.edit_text(
                "⚠️ <b>Мастер временно недоступен</b>\n\n"
                "Этот мастер был заблокирован администратором.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="client_masters")
                ]])
            )
            return
        
        # Извлекаем данные мастера внутри сессии
        master_name = master.name
        master_description = master.description
        
        services = get_services_by_master(session, master.id)
        
        # Извлекаем данные услуг внутри сессии и группируем по категориям
        services_by_category = {}
        for svc in services:
            if svc.category:
                cat_name = svc.category.title
                cat_emoji = svc.category.emoji if svc.category.emoji else "📁"
                category_key = f"{cat_emoji} {cat_name}"
            else:
                category_key = "📁 Без категории"
            
            if category_key not in services_by_category:
                services_by_category[category_key] = []
            
            services_by_category[category_key].append({
                'title': svc.title,
                'price': svc.price,
                'duration': svc.duration_mins
            })
    
    # Формируем текст после закрытия сессии
    total_services = sum(len(svcs) for svcs in services_by_category.values())
    text = f"""👤 <b>{master_name}</b>

📝 <b>Описание:</b>
{master_description or '<i>Описание не указано</i>'}

💼 <b>Услуги ({total_services}):</b>
"""
        
    if services_by_category:
        # Группируем по категориям с эмодзи
        for category_key, svcs in services_by_category.items():
            text += f"\n<b>{category_key}:</b>\n"
            for svc in svcs:
                text += f"  • {svc['title']} — {svc['price']}₽ ({svc['duration']} мин)\n"
    else:
        text += "\n<i>Мастер пока не добавил услуги</i>"
    
    # Получаем фото профиля мастера
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        if master:
            master_avatar = master.avatar_url
        else:
            master_avatar = None
    
    keyboard = [
        [InlineKeyboardButton("📋 Записаться", callback_data=f"book_master_{master_id}")],
        [InlineKeyboardButton("🗑 Удалить мастера", callback_data=f"remove_master_{master_id}")],
        [InlineKeyboardButton("« Назад", callback_data="client_masters")]
    ]
    
    # Удаляем старое сообщение
    try:
        await query.message.delete()
    except:
        pass  # Игнорируем ошибку удаления, если сообщение уже удалено
    
    # Определяем, какое фото использовать: сначала фото профиля мастера, затем первое из портфолио
    photo_to_send = None
    photo_caption = text
    
    # Приоритет 1: фото профиля мастера
    if master_avatar:
        try:
            from bot.config import BOT_TOKEN
            from telegram import Bot as TelegramBot
            import io
            import asyncio
            import requests
            
            # Скачиваем фото профиля через мастер-бот, так как file_id не работает между разными ботами
            master_bot = TelegramBot(token=BOT_TOKEN)
            file = await master_bot.get_file(master_avatar)
            file_path = file.file_path
            
            # Убираем возможный префикс, если он есть
            if file_path.startswith('https://api.telegram.org/file/bot'):
                parts = file_path.split('/file/bot')
                if len(parts) > 1:
                    path_after_token = parts[1].split('/', 1)
                    if len(path_after_token) > 1:
                        file_path = path_after_token[1]
            
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            
            def download_file(url):
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                return response.content
            
            file_content = await asyncio.to_thread(download_file, file_url)
            photo_to_send = io.BytesIO(file_content)
            photo_to_send.seek(0)
        except Exception as e:
            logger.error(f"Error downloading master avatar: {e}", exc_info=True)
            # Если не получилось скачать фото профиля, пробуем портфолио
            photo_to_send = None
    
    # Портфолио теперь привязано к услугам, поэтому не показываем его здесь
    
    # Отправляем сообщение с фото (если есть) или текстом
    if photo_to_send:
        try:
            await query.message.chat.send_photo(
                photo=photo_to_send,
                caption=photo_caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.warning(f"Failed to send photo: {e}")
            # Если не получилось отправить фото, отправляем просто текст
            await query.message.chat.send_message(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        # Отправляем текстовое сообщение
        await query.message.chat.send_message(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def remove_master_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления мастера"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    master_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        client_user = get_or_create_user(session, user.id)
        remove_user_master_link(session, client_user, master)
        
        text = f"✅ Мастер <b>{master.name}</b> удален из вашего списка."
    
    keyboard = [
        [InlineKeyboardButton("« Мои мастера", callback_data="client_masters")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def book_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать процесс записи к мастеру"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        services = get_services_by_master(session, master.id, active_only=True)
        
        if not services:
            text = f"❌ У мастера <b>{master.name}</b> пока нет доступных услуг."
            keyboard = [
                [InlineKeyboardButton("« Назад", callback_data=f"view_master_{master.id}")]
            ]
            await query.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Фильтруем услуги с ценой > 0
        available_services = [svc for svc in services if svc.price > 0]
        
        if not available_services:
            text = f"❌ У мастера <b>{master.name}</b> нет доступных услуг для бронирования.\n\n"
            text += "Все услуги имеют нулевую цену. Обратитесь к мастеру."
            keyboard = [
                [InlineKeyboardButton("« Назад", callback_data=f"view_master_{master.id}")]
            ]
            await query.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        text = f"📋 <b>Запись к мастеру {master.name}</b>\n\nВыберите услугу:"
        keyboard = []
        
        for svc in available_services:
            keyboard.append([
                InlineKeyboardButton(
                    f"{svc.title} — {svc.price}₽",
                    callback_data=f"select_service_{svc.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"view_master_{master.id}")])
    
    # Проверяем, можно ли редактировать сообщение (если это фото, нужно удалить и отправить новое)
    try:
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        # Если не получилось отредактировать (например, это фото), удаляем и отправляем новое
        logger.info(f"Could not edit message in book_master, deleting and sending new: {e}")
        try:
            await query.message.delete()
        except:
            pass  # Игнорируем ошибку удаления, если сообщение уже удалено
        
        await query.message.chat.send_message(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора услуги - переход к выбору даты"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем старые данные бронирования, если они есть (для повторных записей)
    booking_keys = [k for k in list(context.user_data.keys()) if k.startswith('booking_')]
    for key in booking_keys:
        del context.user_data[key]
    
    # Принудительно завершаем предыдущий разговор, если он активен
    # Это позволяет перезапустить ConversationHandler для новой записи
    from telegram.ext import ConversationHandler
    # Проверяем, есть ли активное состояние разговора и завершаем его
    conversation_key = f'conversation_{update.effective_user.id}'
    if conversation_key in context.user_data:
        # Очищаем состояние разговора для этого пользователя
        del context.user_data[conversation_key]
    
    # Также проверяем стандартный способ хранения состояния
    if 'conversation' in context.user_data:
        conversation_state = context.user_data.get('conversation')
        if isinstance(conversation_state, dict) and 'booking' in conversation_state:
            del conversation_state['booking']
    
    # Получаем ID услуги из callback_data: select_service_123
    service_id = int(query.data.split('_')[2])
    user = update.effective_user
    
    with get_session() as session:
        # Получаем услугу
        service = session.query(Service).filter_by(id=service_id, active=True).first()
        
        if not service:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Проверяем, что цена услуги больше 0
        if service.price <= 0:
            await query.message.edit_text(
                "❌ <b>Услуга недоступна для бронирования</b>\n\n"
                "Цена услуги должна быть больше нуля. Обратитесь к мастеру для исправления.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"book_master_{service.master_account.id}")
                ]])
            )
            return ConversationHandler.END
        
        master = service.master_account
        
        # Сохраняем данные в контексте
        context.user_data['booking_service_id'] = service_id
        context.user_data['booking_master_id'] = master.id
        context.user_data['booking_duration'] = service.duration_mins
        context.user_data['booking_price'] = service.price
        context.user_data['booking_cooling'] = service.cooling_period_mins or 0
        
        # Получаем портфолио услуги
        portfolio_photos = get_portfolio_photos(session, service_id)
        
        # Показываем доступные даты (5 недель = 35 дней)
        today = date.today()
        available_dates = []
        
        for i in range(1, 36):  # От завтра до 35 дней вперед
            check_date = today + timedelta(days=i)
            
            # Проверяем есть ли свободные слоты на эту дату
            if has_available_slots_on_date(
                session,
                master.id,
                check_date,
                service.duration_mins,
                service.cooling_period_mins or 0
            ):
                available_dates.append(check_date)
        
        # Формируем текст с информацией об услуге
        text = f"""📋 <b>Запись на: {service.title}</b>

💰 Цена: {service.price}₽
⏱ Длительность: {service.duration_mins} мин"""
        
        if not available_dates:
            # Извлекаем telegram_id мастера внутри сессии
            master_telegram_id = master.telegram_id
            
            text += f"""

❌ К сожалению, у мастера <b>{master.name}</b> нет свободных окон на ближайшие 5 недель.

Попробуйте позже или свяжитесь с мастером напрямую."""
            
            keyboard = [
                [InlineKeyboardButton("« Назад", callback_data=f"book_master_{master.id}")]
            ]
            
            # Добавляем кнопку для связи с мастером, если есть telegram_id
            if master_telegram_id:
                keyboard.insert(0, [
                    InlineKeyboardButton(
                        "💬 Написать мастеру",
                        url=f"tg://user?id={master_telegram_id}"
                    )
                ])
            
            # Отправляем сообщение с портфолио (если есть) или текстом
            await _send_service_selection_with_portfolio(query, context, text, keyboard, portfolio_photos, service)
            return ConversationHandler.END
        
        # Сохраняем все доступные даты в контексте для пагинации
        context.user_data['booking_available_dates'] = [d.isoformat() for d in available_dates]
        context.user_data['booking_date_page'] = 0  # Начинаем с первой страницы
        # Сохраняем портфолио в контексте для использования при пагинации
        context.user_data['booking_portfolio_photos'] = [p.id for p in portfolio_photos] if portfolio_photos else []
        
        # Показываем первую страницу (7 дней) с портфолио
        await _show_date_page(query, context, service, master, 0, portfolio_photos)
    
    return WAITING_BOOKING_DATE


async def _send_service_selection_with_portfolio(query, context, text, keyboard, portfolio_photos, service):
    """Отправить сообщение с выбором услуги и портфолио (если есть)"""
    # Удаляем старое сообщение
    try:
        await query.message.delete()
    except:
        pass
    
    if portfolio_photos and len(portfolio_photos) > 0:
        try:
            from bot.config import BOT_TOKEN
            from telegram import Bot as TelegramBot, InputMediaPhoto
            import io
            import asyncio
            import requests
            
            # Скачиваем все фото портфолио
            media_group = []
            for i, photo in enumerate(portfolio_photos):
                try:
                    photo_file_id = photo.file_id
                    
                    # Скачиваем фото через мастер-бот
                    master_bot = TelegramBot(token=BOT_TOKEN)
                    file = await master_bot.get_file(photo_file_id)
                    file_path = file.file_path
                    
                    # Убираем возможный префикс, если он есть
                    if file_path.startswith('https://api.telegram.org/file/bot'):
                        parts = file_path.split('/file/bot')
                        if len(parts) > 1:
                            path_after_token = parts[1].split('/', 1)
                            if len(path_after_token) > 1:
                                file_path = path_after_token[1]
                    
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                    
                    def download_file(url):
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        return response.content
                    
                    file_content = await asyncio.to_thread(download_file, file_url)
                    photo_data = io.BytesIO(file_content)
                    photo_data.seek(0)
                    
                    # Для последнего фото добавляем только информацию о портфолио
                    if i == len(portfolio_photos) - 1:
                        caption = f"📸 <b>Портфолио услуги</b> ({len(portfolio_photos)} фото)"
                        media_group.append(InputMediaPhoto(media=photo_data, caption=caption, parse_mode='HTML'))
                    else:
                        media_group.append(InputMediaPhoto(media=photo_data))
                except Exception as e:
                    logger.error(f"Error downloading portfolio photo {i+1}: {e}", exc_info=True)
                    continue
            
            if media_group:
                # В Telegram API нельзя добавить inline-кнопки к медиа-группе напрямую
                # Отправляем альбом, затем сразу отправляем текстовое сообщение с информацией и кнопками
                sent_messages = await query.message.chat.send_media_group(media=media_group)
                
                # Сразу после альбома отправляем текстовое сообщение с информацией об услуге и кнопками
                await query.message.chat.send_message(
                    text=text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Если не удалось скачать фото, отправляем просто текст
                await query.message.chat.send_message(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logger.error(f"Error sending portfolio album: {e}", exc_info=True)
            # Если не получилось отправить альбом, отправляем просто текст
            await query.message.chat.send_message(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        # Если нет портфолио, отправляем просто текст
        await query.message.chat.send_message(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def _show_date_page(query, context, service, master, page: int, portfolio_photos=None):
    """Показать страницу с датами (7 дней в столбик)"""
    available_dates_str = context.user_data.get('booking_available_dates', [])
    available_dates = [datetime.strptime(d, '%Y-%m-%d').date() for d in available_dates_str]
    
    if not available_dates:
        await query.message.edit_text("❌ Нет доступных дат")
        return
    
    # Вычисляем количество страниц (по 7 дней на страницу)
    total_pages = (len(available_dates) + 6) // 7
    
    # Ограничиваем page
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    context.user_data['booking_date_page'] = page
    
    # Берем 7 дней для текущей страницы
    start_idx = page * 7
    end_idx = min(start_idx + 7, len(available_dates))
    page_dates = available_dates[start_idx:end_idx]
    
    # Формируем текст
    text = f"""📋 <b>Запись на: {service.title}</b>

💰 Цена: {service.price}₽
⏱ Длительность: {service.duration_mins} мин

Выберите дату:"""
    
    # Формируем кнопки - по одной дате в ряд (один столбик)
    keyboard = []
    weekdays_full = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    weekdays_short = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    for check_date in page_dates:
        weekday_name = weekdays_full[check_date.weekday()]
        weekday_short = weekdays_short[check_date.weekday()]
        
        # Форматируем дату
        if check_date == date.today() + timedelta(days=1):
            date_text = f"Завтра ({weekday_short})"
        elif check_date == date.today() + timedelta(days=2):
            date_text = f"Послезавтра ({weekday_short})"
        else:
            date_text = f"{check_date.strftime('%d.%m')} ({weekday_name})"
        
        keyboard.append([
            InlineKeyboardButton(
                date_text,
                callback_data=f"select_date_{check_date.strftime('%Y-%m-%d')}"
            )
        ])
    
    # Кнопки пагинации
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton("◀️ Предыдущая неделя", callback_data=f"date_page_{page-1}"))
    if page < total_pages - 1:
        pagination_row.append(InlineKeyboardButton("Следующая неделя ▶️", callback_data=f"date_page_{page+1}"))
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"book_master_{master.id}")])
    
    # Если это первая страница и есть портфолио, показываем альбом
    if page == 0 and portfolio_photos:
        try:
            await query.message.delete()
        except:
            pass
        
        try:
            from bot.config import BOT_TOKEN
            from telegram import Bot as TelegramBot, InputMediaPhoto
            import io
            import asyncio
            import requests
            
            # Скачиваем все фото портфолио
            media_group = []
            for i, photo in enumerate(portfolio_photos):
                try:
                    photo_file_id = photo.file_id
                    
                    # Скачиваем фото через мастер-бот
                    master_bot = TelegramBot(token=BOT_TOKEN)
                    file = await master_bot.get_file(photo_file_id)
                    file_path = file.file_path
                    
                    # Убираем возможный префикс, если он есть
                    if file_path.startswith('https://api.telegram.org/file/bot'):
                        parts = file_path.split('/file/bot')
                        if len(parts) > 1:
                            path_after_token = parts[1].split('/', 1)
                            if len(path_after_token) > 1:
                                file_path = path_after_token[1]
                    
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                    
                    def download_file(url):
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        return response.content
                    
                    file_content = await asyncio.to_thread(download_file, file_url)
                    photo_data = io.BytesIO(file_content)
                    photo_data.seek(0)
                    
                    # Для последнего фото добавляем только информацию о портфолио
                    if i == len(portfolio_photos) - 1:
                        caption = f"📸 <b>Портфолио услуги</b> ({len(portfolio_photos)} фото)"
                        media_group.append(InputMediaPhoto(media=photo_data, caption=caption, parse_mode='HTML'))
                    else:
                        media_group.append(InputMediaPhoto(media=photo_data))
                except Exception as e:
                    logger.error(f"Error downloading portfolio photo {i+1}: {e}", exc_info=True)
                    continue
            
            if media_group:
                # В Telegram API нельзя добавить inline-кнопки к медиа-группе напрямую
                # Отправляем альбом, затем сразу отправляем текстовое сообщение с информацией и кнопками
                sent_messages = await query.message.chat.send_media_group(media=media_group)
                
                # Сразу после альбома отправляем текстовое сообщение с информацией об услуге и кнопками
                await query.message.chat.send_message(
                    text=text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Если не удалось скачать фото, отправляем просто текст
                await query.message.chat.send_message(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logger.error(f"Error sending portfolio album in _show_date_page: {e}", exc_info=True)
            # Если не получилось отправить альбом, отправляем просто текст
            await query.message.chat.send_message(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        # Для последующих страниц просто редактируем текст
        try:
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            # Если не получилось отредактировать, удаляем и отправляем новое
            logger.info(f"Could not edit message in _show_date_page, deleting and sending new: {e}")
            try:
                await query.message.delete()
            except:
                pass
            
            await query.message.chat.send_message(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора даты - показ доступного времени или пагинация"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, это пагинация или выбор даты
    if query.data.startswith('date_page_'):
        # Это пагинация
        page = int(query.data.split('_')[2])
        service_id = context.user_data.get('booking_service_id')
        master_id = context.user_data.get('booking_master_id')
        
        if not service_id or not master_id:
            await query.message.edit_text("❌ Ошибка: данные бронирования не найдены")
            return ConversationHandler.END
        
        with get_session() as session:
            service = session.query(Service).filter_by(id=service_id).first()
            master = service.master_account
            
            # Загружаем портфолио из контекста (только для первой страницы)
            portfolio_photos = None
            if page == 0:
                portfolio_photo_ids = context.user_data.get('booking_portfolio_photos', [])
                if portfolio_photo_ids:
                    from bot.database.models import Portfolio
                    portfolio_photos = session.query(Portfolio).filter(
                        Portfolio.id.in_(portfolio_photo_ids)
                    ).order_by(Portfolio.order_index.asc()).all()
            
            await _show_date_page(query, context, service, master, page, portfolio_photos)
            return WAITING_BOOKING_DATE
    
    # Получаем дату из callback_data: select_date_2025-11-03
    date_str = query.data.split('_')[2]
    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    user = update.effective_user
    
    service_id = context.user_data.get('booking_service_id')
    master_id = context.user_data.get('booking_master_id')
    duration = context.user_data.get('booking_duration')
    cooling = context.user_data.get('booking_cooling')
    
    if not all([service_id, master_id, duration]):
        await query.message.edit_text("❌ Ошибка: данные бронирования не найдены")
        return ConversationHandler.END
    
    with get_session() as session:
        service = session.query(Service).filter_by(id=service_id).first()
        master = service.master_account
        
        # Получаем доступные слоты на эту дату
        available_slots = get_available_time_slots(
            session,
            master_id,
            selected_date,
            duration,
            cooling,
            min_time_from_now=60  # Минимум через час
        )
        
        if not available_slots:
            # Если слотов нет (например, все уже заняли), показываем сообщение
            text = f"""📋 <b>Выбранная дата: {selected_date.strftime('%d.%m.%Y')}</b>

❌ К сожалению, на эту дату нет свободных окон.

Выберите другую дату:"""
            
            # Возвращаемся к выбору даты - пересчитываем доступные даты
            today = date.today()
            available_dates = []
            
            for i in range(1, 36):
                check_date = today + timedelta(days=i)
                if has_available_slots_on_date(session, master_id, check_date, duration, cooling):
                    available_dates.append(check_date)
            
            # Сохраняем даты в контексте
            context.user_data['booking_available_dates'] = [d.isoformat() for d in available_dates]
            current_page = context.user_data.get('booking_date_page', 0)
            
            # Показываем текущую страницу
            await _show_date_page(query, context, service, master, current_page)
            return WAITING_BOOKING_DATE
        
        # Сохраняем выбранную дату
        context.user_data['booking_date'] = selected_date.isoformat()
        
        # Формируем текст и кнопки со временем
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        weekday_name = weekdays[selected_date.weekday()]
        
        text = f"""📋 <b>Выбранная дата: {selected_date.strftime('%d.%m.%Y')} ({weekday_name})</b>

💼 Услуга: {service.title}
⏱ Длительность: {duration} мин

Выберите время:"""
        
        keyboard = []
        
        # Группируем слоты по 3 в ряд
        for i in range(0, len(available_slots), 3):
            row = []
            for j in range(i, min(i+3, len(available_slots))):
                slot_start, slot_end = available_slots[j]
                time_str = format_time(slot_start)
                row.append(InlineKeyboardButton(
                    time_str,
                    callback_data=f"select_time_{time_str}"
                ))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("« Назад к выбору даты", callback_data=f"select_service_{service_id}")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_BOOKING_TIME


async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора времени - переход к комментарию/подтверждению"""
    query = update.callback_query
    await query.answer()
    
    # Получаем время из callback_data: select_time_14:00
    time_str = query.data.split('_')[2]  # 14:00
    
    service_id = context.user_data.get('booking_service_id')
    master_id = context.user_data.get('booking_master_id')
    duration = context.user_data.get('booking_duration')
    price = context.user_data.get('booking_price')
    date_str = context.user_data.get('booking_date')
    
    if not all([service_id, master_id, duration, price, date_str]):
        await query.message.edit_text("❌ Ошибка: данные бронирования не найдены")
        return ConversationHandler.END
    
    # Парсим дату и время
    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    from datetime import time as dt_time
    time_parts = time_str.split(':')
    start_time = datetime.combine(selected_date, dt_time(
        hour=int(time_parts[0]),
        minute=int(time_parts[1])
    ))
    
    end_time = start_time + timedelta(minutes=duration)
    
    # Сохраняем время
    context.user_data['booking_start_dt'] = start_time.isoformat()
    context.user_data['booking_end_dt'] = end_time.isoformat()
    
    with get_session() as session:
        service = session.query(Service).filter_by(id=service_id).first()
        master = service.master_account
        
        # Проверяем конфликт еще раз (на случай если кто-то занял время пока выбирали)
        if check_booking_conflict(session, master_id, start_time, end_time):
            text = f"""❌ <b>Время уже занято</b>

К сожалению, выбранное время {time_str} уже занято другим клиентом.

Выберите другое время:"""
            
            # Получаем доступные слоты снова
            available_slots = get_available_time_slots(
                session,
                master_id,
                selected_date,
                duration,
                context.user_data.get('booking_cooling', 0),
                min_time_from_now=60
            )
            
            keyboard = []
            for i in range(0, len(available_slots), 3):
                row = []
                for j in range(i, min(i+3, len(available_slots))):
                    slot_start, _ = available_slots[j]
                    time_str_slot = format_time(slot_start)
                    row.append(InlineKeyboardButton(
                        time_str_slot,
                        callback_data=f"select_time_{time_str_slot}"
                    ))
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"select_service_{service_id}")])
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING_BOOKING_TIME
        
        # Показываем подтверждение с возможностью добавить комментарий
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        
        text = f"""📋 <b>Подтверждение записи</b>

👤 Мастер: <b>{master.name}</b>
💼 Услуга: {service.title}
📅 Дата: {selected_date.strftime('%d.%m.%Y')} ({weekdays[selected_date.weekday()]})
⏰ Время: {time_str} - {end_time.strftime('%H:%M')}
💰 Цена: {price}₽

Вы можете добавить комментарий (опционально), или нажмите "Подтвердить" для завершения записи."""
        
        # Извлекаем master_id внутри сессии
        master_id_for_callback = master.id
        
        keyboard = [
            [InlineKeyboardButton("✏️ Добавить комментарий", callback_data="add_comment")],
            [InlineKeyboardButton("✅ Подтвердить запись", callback_data="confirm_booking")],
            [InlineKeyboardButton("« Отмена", callback_data=f"book_master_{master_id_for_callback}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_BOOKING_COMMENT


async def add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос комментария"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "📝 <b>Введите комментарий к записи</b>\n\n<i>Или нажмите 'Пропустить' для завершения без комментария</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭ Пропустить", callback_data="skip_comment")
        ]])
    )
    
    return WAITING_BOOKING_COMMENT


async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен комментарий"""
    comment = update.message.text.strip()
    
    if len(comment) > 500:
        await update.message.reply_text(
            "❌ Комментарий слишком длинный (максимум 500 символов). Попробуйте короче:"
        )
        return WAITING_BOOKING_COMMENT
    
    context.user_data['booking_comment'] = comment
    
    # Показываем подтверждение с комментарием
    await show_booking_confirmation(update, context, comment)
    
    return WAITING_BOOKING_COMMENT


async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск комментария"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['booking_comment'] = ''
    await show_booking_confirmation(update, context, '')
    
    return WAITING_BOOKING_COMMENT


async def show_booking_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, comment: str = ''):
    """Показать финальное подтверждение"""
    service_id = context.user_data.get('booking_service_id')
    master_id = context.user_data.get('booking_master_id')
    price = context.user_data.get('booking_price')
    date_str = context.user_data.get('booking_date')
    start_dt_str = context.user_data.get('booking_start_dt')
    end_dt_str = context.user_data.get('booking_end_dt')
    
    if not all([service_id, master_id, price, date_str, start_dt_str, end_dt_str]):
        return
    
    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    start_dt = datetime.fromisoformat(start_dt_str)
    end_dt = datetime.fromisoformat(end_dt_str)
    
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    with get_session() as session:
        service = session.query(Service).filter_by(id=service_id).first()
        master = service.master_account
        
        text = f"""📋 <b>Подтверждение записи</b>

👤 Мастер: <b>{master.name}</b>
💼 Услуга: {service.title}
📅 Дата: {selected_date.strftime('%d.%m.%Y')} ({weekdays[selected_date.weekday()]})
⏰ Время: {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}
💰 Цена: {price}₽"""
        
        if comment:
            text += f"\n📝 Комментарий: {comment}"
        
        text += "\n\nПодтвердите запись:"
        
        # Извлекаем master_id внутри сессии
        master_id_for_callback = master.id
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить запись", callback_data="confirm_booking")],
            [InlineKeyboardButton("« Отмена", callback_data=f"book_master_{master_id_for_callback}")]
        ]
        
        if isinstance(update, Update) and update.message:
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


async def notify_master_about_booking(master_telegram_id: int, client_name: str, service_title: str, 
                                       start_dt: datetime, price: float, comment: str = ''):
    """Отправить уведомление мастеру о новой записи"""
    try:
        if not BOT_TOKEN:
            logger.warning("BOT_TOKEN не установлен, невозможно отправить уведомление мастеру")
            return
        
        bot = Bot(token=BOT_TOKEN)
        
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        
        text = f"""🔔 <b>Новая запись!</b>

👤 Клиент: <b>{client_name}</b>
💼 Услуга: {service_title}
📅 Дата и время: {start_dt.strftime('%d.%m.%Y %H:%M')} ({weekdays[start_dt.weekday()]})
💰 Цена: {price}₽"""
        
        if comment:
            text += f"\n📝 Комментарий: {comment}"
        
        text += "\n\nПроверьте раздел \"📋 Записи\" для просмотра всех записей."
        
        await bot.send_message(
            chat_id=master_telegram_id,
            text=text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления мастеру {master_telegram_id}: {e}", exc_info=True)


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финальное подтверждение и создание записи"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    service_id = context.user_data.get('booking_service_id')
    master_id = context.user_data.get('booking_master_id')
    price = context.user_data.get('booking_price')
    start_dt_str = context.user_data.get('booking_start_dt')
    end_dt_str = context.user_data.get('booking_end_dt')
    comment = context.user_data.get('booking_comment', '')
    
    # Проверяем, что цена больше 0
    if price is None or price <= 0:
        await query.message.edit_text(
            "❌ Ошибка: цена услуги должна быть больше нуля. Обратитесь к мастеру.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data=f"book_master_{master_id}")
            ]])
        )
        return ConversationHandler.END
    
    if not all([service_id, master_id, price, start_dt_str, end_dt_str]):
        await query.message.edit_text("❌ Ошибка: данные бронирования не найдены")
        return ConversationHandler.END
    
    start_dt = datetime.fromisoformat(start_dt_str)
    end_dt = datetime.fromisoformat(end_dt_str)
    
    master_telegram_id = None
    client_name = user.full_name or user.first_name or "Клиент"
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        
        # Финальная проверка конфликта
        if check_booking_conflict(session, master_id, start_dt, end_dt):
            await query.message.edit_text(
                "❌ К сожалению, это время уже занято другим клиентом. Попробуйте выбрать другое время.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"book_master_{master_id}")
                ]])
            )
            return ConversationHandler.END
        
        # Получаем telegram_id мастера для уведомления
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        if master:
            master_telegram_id = master.telegram_id
        
        service = session.query(Service).filter_by(id=service_id).first()
        
        # Создаем бронирование
        booking = create_booking(
            session,
            client_user.id,
            master_id,
            service_id,
            start_dt,
            end_dt,
            price,
            comment
        )
        
        service_title = service.title
        master_name = master.name if master else "Мастер"
        
        # Очищаем данные
        context.user_data.clear()
        
        text = f"""✅ <b>Запись успешно создана!</b>

👤 Мастер: <b>{master_name}</b>
💼 Услуга: {service_title}
📅 Дата и время: {start_dt.strftime('%d.%m.%Y %H:%M')}
💰 Цена: {price}₽"""
        
        if comment:
            text += f"\n📝 Комментарий: {comment}"
        
        text += "\n\nМы уведомили мастера о вашей записи."
        
        keyboard = [
            [InlineKeyboardButton("📋 Мои записи", callback_data="client_bookings")],
            [InlineKeyboardButton("« Главное меню", callback_data="client_menu")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Отправляем уведомление мастеру асинхронно (после закрытия сессии)
    if master_telegram_id:
        await notify_master_about_booking(
            master_telegram_id,
            client_name,
            service_title,
            start_dt,
            price,
            comment
        )
    
    return ConversationHandler.END


async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена бронирования"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # Очищаем данные
        context.user_data.clear()
        
        await query.message.edit_text(
            "❌ Запись отменена",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Главное меню", callback_data="client_menu")
            ]])
        )
    else:
        # Если отмена из сообщения (например /cancel)
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Запись отменена",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Главное меню", callback_data="client_menu")
            ]])
        )
    
    return ConversationHandler.END


async def client_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать записи клиента"""
    query = update.callback_query
    if query:
        await query.answer()
    user = update.effective_user
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        bookings = get_bookings_for_client(session, client_user.id)
        
        # Фильтруем будущие записи
        now = datetime.now()
        future_bookings = [b for b in bookings if b.start_dt > now]
        
        if not future_bookings:
            text = "📋 <b>Мои записи</b>\n\nУ вас пока нет предстоящих записей."
        else:
            text = f"📋 <b>Мои записи ({len(future_bookings)})</b>\n\n"
            for booking in sorted(future_bookings, key=lambda x: x.start_dt)[:10]:
                master = booking.master_account
                text += f"👤 <b>{master.name}</b>\n"
                text += f"📅 {booking.start_dt.strftime('%d.%m.%Y %H:%M')}\n"
                text += f"💼 {booking.service.title}\n"
                text += f"💰 {booking.price}₽\n"
                if booking.comment:
                    text += f"📝 {booking.comment}\n"
                text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("« Назад", callback_data="client_menu")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def get_client_menu_buttons():
    """Получить кнопки главного меню клиента (для автоматической синхронизации команд)"""
    return [
        [InlineKeyboardButton("👥 Мои мастера", callback_data="client_masters")],
        [InlineKeyboardButton("🔍 Найти мастеров", callback_data="client_search_masters")],
        [InlineKeyboardButton("📋 Мои записи", callback_data="client_bookings")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="client_help")]
    ]


def get_client_menu_commands():
    """Автоматически генерировать список команд на основе кнопок меню"""
    from telegram import BotCommand
    
    # Маппинг callback_data → (команда, описание)
    callback_to_command = {
        "client_masters": ("masters", "Мои мастера"),
        "client_search_masters": ("search", "Найти мастеров"),
        "client_bookings": ("bookings", "Мои записи"),
        "client_help": ("help", "Помощь"),
    }
    
    buttons = get_client_menu_buttons()
    commands = [BotCommand("start", "Главное меню")]  # Всегда есть start
    
    for row in buttons:
        for button in row:
            callback_data = button.callback_data
            if callback_data in callback_to_command:
                cmd, desc = callback_to_command[callback_data]
                commands.append(BotCommand(cmd, desc))
    
    return commands


async def client_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в главное меню клиента"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        masters = get_client_masters(session, client_user)
        
        text = f"""👋 <b>Lumi Beauty</b>

📊 <b>Ваша статистика:</b>
👥 Добавлено мастеров: {len(masters)}

Выберите действие:"""
    
    keyboard = get_client_menu_buttons()
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def client_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь для клиента"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    
    # Получаем список мастеров для добавления ссылок на ЛС
    master_links = []
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        masters = get_client_masters(session, client_user)
        for link in masters:
            master = link.master_account
            if master:
                master_links.append({
                    'name': master.name,
                    'telegram_id': master.telegram_id
                })
    
    text = """ℹ️ <b>Помощь</b>

<b>Как записаться к мастеру?</b>
1. Попросите мастера отправить вам QR-код или ссылку
2. Перейдите по ссылке или отсканируйте QR
3. Мастер автоматически добавится в ваш список
4. Выберите услугу и запишитесь!

<b>Как удалить мастера?</b>
Откройте профиль мастера и нажмите "Удалить мастера"

<b>Как посмотреть свои записи?</b>
Нажмите "Мои записи" в главном меню"""
    
    keyboard = []
    
    # Добавляем кнопки для связи с мастерами, если они есть
    if master_links:
        text += "\n\n<b>Связаться с мастером:</b>"
        for master_info in master_links[:5]:  # Ограничиваем 5 мастерами
            keyboard.append([
                InlineKeyboardButton(
                    f"💬 Написать {master_info['name']}",
                    url=f"tg://user?id={master_info['telegram_id']}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="client_menu")])
    
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


async def client_search_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск мастеров по городам"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    
    with get_session() as session:
        # Получаем все города
        all_cities = get_all_cities(session)
        
        # Фильтруем: показываем только города, где есть хотя бы один активный мастер
        from bot.database.models import MasterAccount
        cities_with_masters = []
        for city in all_cities:
            masters_count = session.query(MasterAccount).filter_by(
                city_id=city.id,
                is_blocked=False
            ).count()
            if masters_count > 0:
                cities_with_masters.append((city, masters_count))
        
        if not cities_with_masters:
            text = "🔍 <b>Поиск мастеров</b>\n\n"
            text += "❌ Пока нет доступных городов с мастерами.\n\n"
            text += "Мастера еще не зарегистрировались в системе или не указали свой город."
            
            keyboard = [
                [InlineKeyboardButton("« Назад", callback_data="client_menu")]
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
            return
        
        text = "🔍 <b>Поиск мастеров</b>\n\n"
        text += "Выберите город:\n\n"
        
        keyboard = []
        for city, masters_count in cities_with_masters:
            # Показываем название на русском и количество мастеров
            keyboard.append([
                InlineKeyboardButton(
                    f"📍 {city.name_ru} ({masters_count})",
                    callback_data=f"search_city_{city.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="client_menu")
        ])
        
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


async def client_search_city_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать мастеров в выбранном городе"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID города из callback_data: search_city_1
    city_id = int(query.data.split('_')[2])
    
    user = update.effective_user
    
    with get_session() as session:
        from bot.database.models import City
        city = session.query(City).filter_by(id=city_id).first()
        
        if not city:
            await query.message.edit_text(
                "❌ Город не найден",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="client_search_masters")
                ]])
            )
            return
        
        # Получаем мастеров в этом городе, исключая уже добавленных
        masters = get_masters_by_city(session, city_id, exclude_user_id=user.id, active_only=True)
        
        # Логируем для отладки
        from bot.database.models import MasterAccount
        all_masters_in_city = session.query(MasterAccount).filter_by(city_id=city_id, is_blocked=False).count()
        logger.info(f"Searching masters in city {city_id} ({city.name_ru}): found {len(masters)} masters (total in city: {all_masters_in_city})")
        
        text = f"🔍 <b>Мастера в городе: {city.name_ru}</b>\n\n"
        
        if not masters:
            # Проверяем, есть ли вообще мастера в этом городе (возможно, все уже добавлены)
            if all_masters_in_city > 0:
                text += f"✅ В этом городе есть {all_masters_in_city} мастер(ов), но все они уже добавлены в ваш список.\n\n"
                text += "Попробуйте выбрать другой город."
            else:
                text += "❌ В этом городе пока нет доступных мастеров.\n\n"
                text += "Попробуйте выбрать другой город."
            
            keyboard = [
                [InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")]
            ]
        else:
            text += f"Найдено мастеров: {len(masters)}\n\n"
            
            keyboard = []
            for master in masters:
                # Показываем имя мастера и количество услуг
                services_count = len(get_services_by_master(session, master.id, active_only=True))
                keyboard.append([
                    InlineKeyboardButton(
                        f"👤 {master.name} ({services_count} услуг)",
                        callback_data=f"search_view_master_{master.id}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")
            ])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def client_search_view_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр мастера из поиска (с возможностью добавления)"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID мастера из callback_data: search_view_master_1
    master_id = int(query.data.split('_')[3])
    
    user = update.effective_user
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        # Проверяем, не добавлен ли уже этот мастер
        client_user = get_or_create_user(session, user.id)
        from bot.database.models import UserMaster
        existing_link = session.query(UserMaster).filter_by(
            user_id=client_user.id,
            master_account_id=master_id
        ).first()
        
        # Получаем услуги мастера
        services = get_services_by_master(session, master.id, active_only=True)
        
        # Формируем текст
        text = f"👤 <b>{master.name}</b>\n\n"
        
        if master.city:
            text += f"📍 Город: {master.city.name_ru}\n"
        
        if master.description:
            text += f"📝 {master.description}\n\n"
        else:
            text += "📝 <i>Описание не указано</i>\n\n"
        
        text += f"💼 <b>Услуги ({len(services)}):</b>\n"
        
        if services:
            # Показываем первые 5 услуг
            for svc in services[:5]:
                text += f"  • {svc.title} — {svc.price}₽ ({svc.duration_mins} мин)\n"
            if len(services) > 5:
                text += f"  <i>... и еще {len(services) - 5}</i>\n"
        else:
            text += "<i>Услуги не добавлены</i>\n"
        
        keyboard = []
        
        if not existing_link:
            # Если мастер еще не добавлен, показываем кнопку добавления
            keyboard.append([
                InlineKeyboardButton("➕ Добавить мастера", callback_data=f"search_add_master_{master_id}")
            ])
        else:
            # Если уже добавлен, показываем кнопку просмотра
            keyboard.append([
                InlineKeyboardButton("👁 Просмотреть профиль", callback_data=f"view_master_{master_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("📋 Записаться", callback_data=f"book_master_{master_id}")
        ])
        
        # Определяем, откуда вернуться
        if master.city:
            keyboard.append([
                InlineKeyboardButton("« Назад к мастерам города", callback_data=f"search_city_{master.city.id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")
            ])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def client_search_add_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить мастера из поиска"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID мастера из callback_data: search_add_master_1
    master_id = int(query.data.split('_')[3])
    
    user = update.effective_user
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        client_user = get_or_create_user(session, user.id)
        
        # Добавляем связь
        link = add_user_master_link(session, client_user, master)
        logger.info(f"Master {master_id} added to user {user.id} from search")
        
        text = f"✅ <b>Мастер добавлен!</b>\n\n"
        text += f"👤 <b>{master.name}</b>\n\n"
        text += "Теперь вы можете записаться к этому мастеру!"
        
        keyboard = [
            [InlineKeyboardButton("💼 Услуги мастера", callback_data=f"view_master_{master_id}")],
            [InlineKeyboardButton("📋 Записаться", callback_data=f"book_master_{master_id}")],
            [InlineKeyboardButton("🔍 Найти еще мастеров", callback_data="client_search_masters")],
            [InlineKeyboardButton("« Главное меню", callback_data="client_menu")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# Командные обработчики (дублируют главное меню для Bot Commands)
async def client_masters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /masters - показывает мастеров"""
    await client_masters(update, context)


async def client_bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /bookings - показывает записи"""
    await client_bookings(update, context)


async def client_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help - показывает помощь"""
    await client_help(update, context)


async def client_master_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр фото мастера клиентом"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master or not master.avatar_url:
            await query.message.edit_text(
                "❌ Фото мастера недоступно",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"view_master_{master_id}")
                ]])
            )
            return
    
    try:
        await query.message.delete()
        await query.message.chat.send_photo(
            photo=master.avatar_url,
            caption=f"🖼 <b>Фото мастера</b>\n\n👤 {master.name}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data=f"view_master_{master_id}")
            ]])
        )
    except Exception as e:
        logger.error(f"Error sending master photo: {e}")
        await query.message.edit_text(
            "❌ Не удалось загрузить фото",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data=f"view_master_{master_id}")
            ]])
        )


async def client_service_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр портфолио услуги клиентом"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: client_service_portfolio_123
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        from bot.database.models import Service
        from bot.database.db import get_service_by_id
        service = get_service_by_id(session, service_id)
        
        if not service:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        portfolio_photos = get_portfolio_photos(session, service_id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                f"📸 <b>Портфолио пусто</b>\n\n💼 Услуга: <b>{service.title}</b>\n\nМастер еще не добавил работы в портфолио этой услуги.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"view_master_{service.master_account_id}")
                ]])
            )
            return
        
        # Сохраняем данные для навигации
        context.user_data['client_portfolio_index'] = 0
        context.user_data['client_portfolio_photos'] = [p.id for p in portfolio_photos]
        context.user_data['client_portfolio_service_id'] = service_id
        
        # Отправляем первое фото
        first_photo = portfolio_photos[0]
        caption = f"📸 <b>Портфолио услуги</b>\n\n💼 <b>{service.title}</b>\n\n(1/{len(portfolio_photos)})"
        if first_photo.caption:
            caption += f"\n\n{first_photo.caption}"
        
        keyboard = []
        if len(portfolio_photos) > 1:
            keyboard.append([
                InlineKeyboardButton("▶️ Следующее", callback_data="client_portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data=f"view_master_{service.master_account_id}")
        ])
        
        await query.message.delete()
        try:
            # Пробуем отправить фото через file_id
            await query.message.chat.send_photo(
                photo=first_photo.file_id,
                caption=caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error sending portfolio photo via file_id: {e}", exc_info=True)
            # Если file_id не работает (разные боты), получаем файл через мастер-бот
            try:
                from bot.config import BOT_TOKEN
                from telegram import Bot as TelegramBot
                import io
                import asyncio
                import requests
                
                logger.info(f"Attempting to download photo via master bot. file_id: {first_photo.file_id}")
                master_bot = TelegramBot(token=BOT_TOKEN)
                file = await master_bot.get_file(first_photo.file_id)
                logger.info(f"Got file info. file_path: {file.file_path}, file_size: {file.file_size}")
                
                if not file.file_path:
                    raise ValueError("file_path is None or empty")
                
                # Получаем полный URL файла
                # file_path должен быть относительным путем (например, "photos/file_3.jpg")
                # Если он уже содержит полный URL, это ошибка API
                file_path = file.file_path
                
                # Убираем возможный префикс, если он есть
                if file_path.startswith('https://api.telegram.org/file/bot'):
                    # Если уже полный URL, извлекаем относительный путь
                    # Формат: https://api.telegram.org/file/bot{TOKEN}/{path}
                    parts = file_path.split('/file/bot')
                    if len(parts) > 1:
                        # Извлекаем путь после токена
                        path_after_token = parts[1].split('/', 1)
                        if len(path_after_token) > 1:
                            file_path = path_after_token[1]
                
                # Формируем полный URL с токеном мастер-бота
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                logger.info(f"Downloading file from URL: {file_url}")
                
                # Пробуем сначала отправить по URL напрямую
                try:
                    logger.info("Trying to send photo via URL")
                    await query.message.chat.send_photo(
                        photo=file_url,
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    logger.info("Photo sent successfully via URL")
                except Exception as url_error:
                    logger.warning(f"Failed to send via URL: {url_error}, trying to download")
                    # Если не получилось, скачиваем файл
                    def download_file(url):
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        return response.content
                    
                    file_content = await asyncio.to_thread(download_file, file_url)
                    logger.info(f"Downloaded file. Size: {len(file_content)} bytes")
                    photo_data = io.BytesIO(file_content)
                    photo_data.seek(0)
                    
                    # Отправляем файл в клиент-бот
                    logger.info("Sending photo to client bot")
                    await query.message.chat.send_photo(
                        photo=photo_data,
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    logger.info("Photo sent successfully")
            except Exception as e2:
                logger.error(f"Error sending portfolio photo via file download: {e2}", exc_info=True)
                await query.message.chat.send_message(
                    text=f"❌ Не удалось загрузить фото портфолио.\n\n{caption}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )


async def client_portfolio_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Следующее фото в портфолио (клиент)"""
    query = update.callback_query
    await query.answer()
    
    photo_ids = context.user_data.get('client_portfolio_photos', [])
    service_id = context.user_data.get('client_portfolio_service_id')
    
    if not photo_ids or not service_id:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('client_portfolio_index', 0)
    current_index = (current_index + 1) % len(photo_ids)
    context.user_data['client_portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        from bot.database.db import get_service_by_id
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        service = get_service_by_id(session, service_id)
        
        if not photo or not service:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Портфолио услуги</b>\n\n💼 <b>{service.title}</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data="client_portfolio_prev"),
                InlineKeyboardButton("▶️ Следующее", callback_data="client_portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data=f"view_master_{service.master_account_id}")
        ])
        
        from telegram import InputMediaPhoto
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error editing portfolio photo via file_id: {e}", exc_info=True)
            # Если file_id не работает (разные боты), получаем файл через мастер-бот
            try:
                from bot.config import BOT_TOKEN
                from telegram import Bot as TelegramBot
                import io
                import asyncio
                import requests
                
                logger.info(f"Attempting to download photo via master bot. file_id: {photo.file_id}")
                master_bot = TelegramBot(token=BOT_TOKEN)
                file = await master_bot.get_file(photo.file_id)
                logger.info(f"Got file info. file_path: {file.file_path}, file_size: {file.file_size}")
                
                if not file.file_path:
                    raise ValueError("file_path is None or empty")
                
                # Получаем полный URL файла
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
                logger.info(f"Downloading file from URL: {file_url}")
                
                # Скачиваем файл через HTTP (используем asyncio для неблокирующего запроса)
                def download_file(url):
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    return response.content
                
                file_content = await asyncio.to_thread(download_file, file_url)
                logger.info(f"Downloaded file. Size: {len(file_content)} bytes")
                photo_data = io.BytesIO(file_content)
                photo_data.seek(0)
                
                # Удаляем старое сообщение и отправляем новое
                await query.message.delete()
                logger.info("Sending photo to client bot")
                await query.message.chat.send_photo(
                    photo=photo_data,
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.info("Photo sent successfully")
            except Exception as e2:
                logger.error(f"Error editing portfolio photo via file download: {e2}", exc_info=True)
                await query.message.edit_text(
                    text=f"❌ Не удалось загрузить фото портфолио.\n\n{caption}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )


async def client_portfolio_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предыдущее фото в портфолио (клиент)"""
    query = update.callback_query
    await query.answer()
    
    photo_ids = context.user_data.get('client_portfolio_photos', [])
    service_id = context.user_data.get('client_portfolio_service_id')
    
    if not photo_ids or not service_id:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('client_portfolio_index', 0)
    current_index = (current_index - 1) % len(photo_ids)
    context.user_data['client_portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        from bot.database.db import get_service_by_id
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        service = get_service_by_id(session, service_id)
        
        if not photo or not service:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Портфолио услуги</b>\n\n💼 <b>{service.title}</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data="client_portfolio_prev"),
                InlineKeyboardButton("▶️ Следующее", callback_data="client_portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data=f"view_master_{service.master_account_id}")
        ])
        
        from telegram import InputMediaPhoto
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error editing portfolio photo via file_id: {e}", exc_info=True)
            # Если file_id не работает (разные боты), получаем файл через мастер-бот
            try:
                from bot.config import BOT_TOKEN
                from telegram import Bot as TelegramBot
                import io
                import asyncio
                import requests
                
                logger.info(f"Attempting to download photo via master bot. file_id: {photo.file_id}")
                master_bot = TelegramBot(token=BOT_TOKEN)
                file = await master_bot.get_file(photo.file_id)
                logger.info(f"Got file info. file_path: {file.file_path}, file_size: {file.file_size}")
                
                if not file.file_path:
                    raise ValueError("file_path is None or empty")
                
                # Получаем полный URL файла
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
                logger.info(f"Downloading file from URL: {file_url}")
                
                # Скачиваем файл через HTTP (используем asyncio для неблокирующего запроса)
                def download_file(url):
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    return response.content
                
                file_content = await asyncio.to_thread(download_file, file_url)
                logger.info(f"Downloaded file. Size: {len(file_content)} bytes")
                photo_data = io.BytesIO(file_content)
                photo_data.seek(0)
                
                # Удаляем старое сообщение и отправляем новое
                await query.message.delete()
                logger.info("Sending photo to client bot")
                await query.message.chat.send_photo(
                    photo=photo_data,
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.info("Photo sent successfully")
            except Exception as e2:
                logger.error(f"Error editing portfolio photo via file download: {e2}", exc_info=True)
                await query.message.edit_text(
                    text=f"❌ Не удалось загрузить фото портфолио.\n\n{caption}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

