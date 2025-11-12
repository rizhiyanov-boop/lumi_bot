"""Обработчики для клиентского бота"""
from typing import Dict, List
import qrcode
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

# Константы
MASTERS_PER_PAGE = 7
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
from bot.database.models import Service, ServiceCategory, MasterAccount, UserMaster
from bot.config import BOT_TOKEN
from bot.utils.currency import format_price
from telegram import Bot
import logging

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler бронирования
WAITING_BOOKING_DATE, WAITING_BOOKING_TIME, WAITING_BOOKING_COMMENT = range(3)


def _get_client_search_state(context: ContextTypes.DEFAULT_TYPE) -> Dict:
    """Получить (или инициализировать) состояние поиска мастеров для клиента"""
    return context.user_data.setdefault('client_search_state', {})


def _build_category_items(session, city_id: int) -> List[Dict]:
    """
    Собрать категории услуг, доступные в выбранном городе.
    Возвращает список категорий, сгруппированных по ключу/названию и содержащих мастеров.
    """
    results = (
        session.query(
            ServiceCategory.id.label("category_id"),
            ServiceCategory.title.label("title"),
            ServiceCategory.emoji.label("emoji"),
            ServiceCategory.category_key.label("category_key"),
            MasterAccount.id.label("master_id"),
        )
        .join(Service, Service.category_id == ServiceCategory.id)
        .join(MasterAccount, Service.master_account_id == MasterAccount.id)
        .filter(
            MasterAccount.city_id == city_id,
            MasterAccount.is_blocked.is_(False),
            Service.active.is_(True),
        )
        .all()
    )
    
    category_map: Dict[str, Dict] = {}
    for row in results:
        group_key = row.category_key or row.title.strip().lower()
        if not group_key:
            # fallback: используем id категории, чтобы не потерять данные
            group_key = f"category_{row.category_id}"
        
        entry = category_map.setdefault(
            group_key,
            {
                "title": row.title,
                "emoji": row.emoji,
                "category_ids": set(),
                "master_ids": set(),
            },
        )
        # Обновляем человекочитабельное название/эмодзи, если новых нет
        if not entry.get("emoji") and row.emoji:
            entry["emoji"] = row.emoji
        if len(row.title) > len(entry["title"]):
            # Берем наиболее длинное название (обычно более информативное)
            entry["title"] = row.title
        
        entry["category_ids"].add(row.category_id)
        entry["master_ids"].add(row.master_id)
    
    category_items: List[Dict] = []
    for entry in category_map.values():
        if not entry["master_ids"]:
            continue
        category_items.append(
            {
                "title": entry["title"],
                "emoji": entry["emoji"],
                "category_ids": list(entry["category_ids"]),
                "master_ids": list(entry["master_ids"]),
                "masters_count": len(entry["master_ids"]),
            }
        )
    
    category_items.sort(key=lambda item: item["title"].lower())
    return category_items


def _compose_categories_markup(city_name: str, city_id: int, category_items: List[Dict]):
    """Сформировать текст и клавиатуру выбора категорий"""
    text = f"🔍 <b>Город: {city_name}</b>\n\n"
    text += "Выберите категорию, чтобы увидеть услуги и мастеров:\n\n"
    
    buttons: List[InlineKeyboardButton] = []
    for idx, item in enumerate(category_items):
        emoji = item["emoji"] or "📂"
        label = f"{emoji} {item['title']} ({item['masters_count']})"
        buttons.append(InlineKeyboardButton(label, callback_data=f"search_category_idx_{idx}"))
    
    keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)] or [[]]
    keyboard.append([InlineKeyboardButton("📋 Все мастера города", callback_data=f"search_city_all_{city_id}")])
    keyboard.append([InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")])
    
    return text, InlineKeyboardMarkup(keyboard)


def _compose_services_response(context: ContextTypes.DEFAULT_TYPE, category_idx: int):
    """
    Собрать текст и клавиатуру для списка услуг выбранной категории.
    Обновляет состояние поиска (selected_category_idx, services).
    """
    state = _get_client_search_state(context)
    categories = state.get('categories') or []
    city_id = state.get('city_id')
    city_name = state.get('city_name', 'неизвестный город')
    
    if city_id is None or category_idx >= len(categories):
        raise ValueError("Invalid category index or city not selected")
    
    category_item = categories[category_idx]
    state['selected_category_idx'] = category_idx
    state['selected_service_idx'] = None
    
    with get_session() as session:
        service_items = _build_service_items(session, city_id, category_item)
        state['services'] = service_items
    
    text = f"🔍 <b>{city_name}</b>\n"
    text += f"Категория: <b>{category_item['title']}</b>\n\n"
    
    if not service_items:
        text += "ℹ️ В этой категории пока нет услуг.\n\n"
        text += "Вы можете посмотреть всех мастеров категории."
        
        keyboard = [
            [InlineKeyboardButton("📋 Все мастера категории", callback_data="search_category_all")],
            [InlineKeyboardButton("« Назад к категориям", callback_data="search_categories_back")]
        ]
    else:
        text += "Выберите услугу, чтобы увидеть мастеров:\n\n"
        buttons = []
        for idx, item in enumerate(service_items):
            label = f"💼 {item['title']} ({item['masters_count']})"
            buttons.append(InlineKeyboardButton(label, callback_data=f"search_service_idx_{idx}"))
        
        keyboard = [buttons[i:i + 1] for i in range(0, len(buttons), 1)]
        keyboard.append([InlineKeyboardButton("📋 Все мастера категории", callback_data="search_category_all")])
        keyboard.append([InlineKeyboardButton("« Назад к категориям", callback_data="search_categories_back")])
    
    return text, InlineKeyboardMarkup(keyboard)


def _build_service_items(session, city_id: int, category_item: Dict) -> List[Dict]:
    """
    Собрать услуги в рамках выбранной категории и города.
    Возвращает список услуг с перечнем мастеров, которые их оказывают.
    """
    if not category_item.get("category_ids"):
        return []
    
    results = (
        session.query(
            Service.id.label("service_id"),
            Service.title.label("title"),
            Service.price.label("price"),
            Service.duration_mins.label("duration"),
            Service.master_account_id.label("master_id"),
        )
        .join(MasterAccount, Service.master_account_id == MasterAccount.id)
        .filter(
            MasterAccount.city_id == city_id,
            MasterAccount.is_blocked.is_(False),
            Service.active.is_(True),
            Service.category_id.in_(category_item["category_ids"]),
        )
        .all()
    )
    
    service_map: Dict[str, Dict] = {}
    for row in results:
        service_key = row.title.strip().lower()
        if not service_key:
            service_key = f"service_{row.service_id}"
        
        entry = service_map.setdefault(
            service_key,
            {
                "title": row.title,
                "master_ids": set(),
                "service_ids": [],
                "master_services": {},
            },
        )
        entry["service_ids"].append(row.service_id)
        entry["master_ids"].add(row.master_id)
        # Сохраняем первую попавшуюся услугу мастера (если несколько, берем самую дешевую)
        existing = entry["master_services"].get(row.master_id)
        if existing is None or row.price < existing["price"]:
            entry["master_services"][row.master_id] = {
                "service_id": row.service_id,
                "price": row.price,
                "duration": row.duration,
            }
    
    service_items: List[Dict] = []
    for entry in service_map.values():
        if not entry["master_ids"]:
            continue
        service_items.append(
            {
                "title": entry["title"],
                "master_ids": list(entry["master_ids"]),
                "service_ids": entry["service_ids"],
                "master_services": entry["master_services"],
                "masters_count": len(entry["master_ids"]),
            }
        )
    
    service_items.sort(key=lambda item: item["title"].lower())
    return service_items


def _filter_masters_for_client(session, master_ids: List[int], user_telegram_id: int) -> List[MasterAccount]:
    """Отфильтровать мастеров, исключив заблокированных и уже добавленных клиентом"""
    if not master_ids:
        return []
    
    masters = (
        session.query(MasterAccount)
        .filter(
            MasterAccount.id.in_(master_ids),
            MasterAccount.is_blocked.is_(False),
        )
        .order_by(MasterAccount.name.asc())
        .all()
    )
    
    if not masters or not user_telegram_id:
        return masters
    
    user = get_or_create_user(session, user_telegram_id)
    if not user:
        return masters
    
    added_master_ids = {
        link.master_account_id
        for link in session.query(UserMaster).filter_by(user_id=user.id).all()
    }
    
    if not added_master_ids:
        return masters
    
    filtered = [master for master in masters if master.id not in added_master_ids]
    logger.info(
        f"Filtered masters for user {user_telegram_id}: "
        f"{len(filtered)} of {len(masters)} remain after excluding already added"
    )
    return filtered


def _format_masters_list_page(masters_data: List[Dict], page: int = 0, per_page: int = MASTERS_PER_PAGE, display_type: str = 'service') -> tuple[str, List[List[InlineKeyboardButton]], int]:
    """
    Форматирует список мастеров с пагинацией.
    display_type: 'service', 'category', 'city' - для правильной генерации callback_data пагинации
    Возвращает: (текст, клавиатура, общее количество страниц)
    """
    total_pages = (len(masters_data) + per_page - 1) // per_page if masters_data else 0
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_masters = masters_data[start_idx:end_idx]
    
    text = ""
    keyboard = []
    
    if not page_masters:
        text += "❌ Мастера не найдены.\n\n"
    else:
        if total_pages > 1:
            text += f"Мастера (страница {page + 1} из {total_pages}):\n\n"
        else:
            text += f"Мастера ({len(masters_data)}):\n\n"
        for master_data in page_masters:
            details = ""
            if master_data.get('service_info'):
                price_text = format_price(master_data['service_info']['price'], master_data.get('currency', 'RUB'))
                details = f" — {price_text}, {master_data['service_info']['duration']} мин"
            elif master_data.get('price'):
                price_text = format_price(master_data['price'], master_data.get('currency', 'RUB'))
                details = f" — {price_text}"
            
            label = f"👤 {master_data['name']}"
            if master_data.get('already_added'):
                label += " • уже в списке"
            text += f"• {master_data['name']}{details}\n"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"search_view_master_{master_data['id']}")])
        text += "\n"
    
    # Пагинация
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀ Назад", callback_data=f"masters_page_{display_type}_{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ▶", callback_data=f"masters_page_{display_type}_{page + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
    
    return text, keyboard, total_pages


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
                'telegram_id': master.telegram_id,
                'currency': master.currency or 'RUB'
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
            from bot.utils.currency import format_price
            master_currency = master_info.get('currency', 'RUB')
            master_text += f"💼 <b>Услуги ({master_info['services_count']}):</b>\n"
            # Показываем первые 5 услуг для компактности
            for svc in master_info['services'][:5]:
                price_formatted = format_price(svc['price'], master_currency)
                master_text += f"  • {svc['title']} — {price_formatted} ({svc['duration']} мин)\n"
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
    
    # Оптимизация: получаем все данные в одной сессии
    master_name = None
    master_description = None
    master_currency = 'RUB'
    master_avatar = None
    master_telegram_id = None
    services_by_category = {}
    
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
        
        # Извлекаем все данные мастера в одной сессии
        master_name = master.name
        master_description = master.description
        master_currency = master.currency or 'RUB'
        master_avatar = master.avatar_url
        master_telegram_id = master.telegram_id
        
        # Получаем услуги
        services = get_services_by_master(session, master.id)
        
        # Группируем услуги по категориям
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
    
    from bot.utils.currency import format_price
    
    # Формируем текст
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
                price_formatted = format_price(svc['price'], master_currency)
                text += f"  • {svc['title']} — {price_formatted} ({svc['duration']} мин)\n"
    else:
        text += "\n<i>Мастер пока не добавил услуги</i>"
    
    keyboard = [
        [InlineKeyboardButton("📋 Записаться", callback_data=f"book_master_{master_id}")]
    ]
    
    # Добавляем кнопку для связи с мастером
    if master_telegram_id:
        keyboard.append([
            InlineKeyboardButton(
                "💬 Написать мастеру",
                url=f"tg://user?id={master_telegram_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="client_masters")])
    
    # Определяем, какое фото использовать
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
    
    # Редактируем существующее сообщение вместо удаления и отправки нового
    try:
        # Проверяем, есть ли фото в текущем сообщении
        has_photo_in_message = query.message.photo is not None and len(query.message.photo) > 0
        
        if photo_to_send:
            # Если есть фото для отправки
            if has_photo_in_message:
                # Редактируем медиа (фото) с новым текстом
                from telegram import InputMediaPhoto
                await query.message.edit_media(
                    media=InputMediaPhoto(
                        media=photo_to_send,
                        caption=photo_caption,
                        parse_mode='HTML'
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Если в сообщении не было фото, удаляем и отправляем новое с фото
                # (нельзя изменить текстовое сообщение на фото)
                try:
                    await query.message.delete()
                except:
                    pass
                await query.message.chat.send_photo(
                    photo=photo_to_send,
                    caption=photo_caption,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            # Если нет фото для отправки
            if has_photo_in_message:
                # Если в сообщении было фото, удаляем и отправляем текстовое
                # (нельзя изменить фото на текст)
                try:
                    await query.message.delete()
                except:
                    pass
                await query.message.chat.send_message(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Просто редактируем текст
                await query.message.edit_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}, trying to send new message")
        # Если редактирование не удалось, отправляем новое сообщение
        try:
            await query.message.delete()
        except:
            pass
        if photo_to_send:
            await query.message.chat.send_photo(
                photo=photo_to_send,
                caption=photo_caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
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
        [InlineKeyboardButton("⚙️ Настройки", callback_data="client_settings")],
        [InlineKeyboardButton("« Главное меню", callback_data="client_menu")]
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
        
        from bot.utils.currency import format_price
        
        for svc in available_services:
            price_formatted = format_price(svc.price, master.currency)
            keyboard.append([
                InlineKeyboardButton(
                    f"{svc.title} — {price_formatted}",
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
        from bot.utils.currency import format_price
        price_formatted = format_price(service.price, master.currency)
        
        text = f"""📋 <b>Запись на: {service.title}</b>

💰 Цена: {price_formatted}
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
            # Передаем только service_id, так как объект service отсоединен от сессии
            await _send_service_selection_with_portfolio(query, context, text, keyboard, portfolio_photos, service_id)
            return ConversationHandler.END
        
        # Сохраняем все доступные даты в контексте для пагинации
        context.user_data['booking_available_dates'] = [d.isoformat() for d in available_dates]
        context.user_data['booking_date_page'] = 0  # Начинаем с первой страницы
        # Сохраняем портфолио в контексте для использования при пагинации
        context.user_data['booking_portfolio_photos'] = [p.id for p in portfolio_photos] if portfolio_photos else []
        
        # Показываем первую страницу (7 дней) с портфолио
        # Передаем только service_id, так как объекты service и master отсоединены от сессии
        await _show_date_page(query, context, service_id, 0, portfolio_photos)
    
    return WAITING_BOOKING_DATE


async def _send_service_selection_with_portfolio(query, context, text, keyboard, portfolio_photos, service_id):
    """Отправить сообщение с выбором услуги и портфолио (если есть)"""
    # service_id передается для совместимости, но не используется, так как text уже содержит всю информацию
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


async def _show_date_page(query, context, service_id: int, page: int, portfolio_photos=None):
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
    
    # Получаем мастера для валюты и данные услуги
    master_id = None  # Инициализируем перед блоком with
    service_price = None
    service_title = None
    service_duration = None
    master_currency = 'RUB'
    
    with get_session() as session:
        from bot.database.models import Service, MasterAccount
        # Получаем услугу и мастера в одной сессии
        service_obj = session.query(Service).filter_by(id=service_id).first()
        if not service_obj:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        # Получаем данные мастера для валюты
        master_id = service_obj.master_account_id
        master_obj = session.query(MasterAccount).filter_by(id=master_id).first() if master_id else None
        
        # Получаем значения атрибутов внутри сессии
        service_price = service_obj.price
        service_title = service_obj.title
        service_duration = service_obj.duration_mins
        master_currency = master_obj.currency if master_obj and master_obj.currency else 'RUB'
    
    # Проверяем, что все необходимые данные получены
    if not master_id:
        await query.message.edit_text("❌ Ошибка: не удалось определить мастера услуги")
        return
    
    # Формируем текст
    from bot.utils.currency import format_price
    price_formatted = format_price(service_price, master_currency)
    
    text = f"""📋 <b>Запись на: {service_title}</b>

💰 Цена: {price_formatted}
⏱ Длительность: {service_duration} мин

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
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"book_master_{master_id}")])
    
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
            # Загружаем портфолио из контекста (только для первой страницы)
            portfolio_photos = None
            if page == 0:
                portfolio_photo_ids = context.user_data.get('booking_portfolio_photos', [])
                if portfolio_photo_ids:
                    from bot.database.models import Portfolio
                    portfolio_photos = session.query(Portfolio).filter(
                        Portfolio.id.in_(portfolio_photo_ids)
                    ).order_by(Portfolio.order_index.asc()).all()
            
            # Передаем только service_id, так как объекты service и master отсоединены от сессии
            await _show_date_page(query, context, service_id, page, portfolio_photos)
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
        # Получаем данные услуги внутри сессии
        service_obj = session.query(Service).filter_by(id=service_id).first()
        if not service_obj:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Получаем значения атрибутов внутри сессии
        service_title = service_obj.title
        
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
            # Передаем только service_id, так как объекты service и master отсоединены от сессии
            await _show_date_page(query, context, service_id, current_page)
            return WAITING_BOOKING_DATE
        
        # Сохраняем выбранную дату
        context.user_data['booking_date'] = selected_date.isoformat()
        
        # Формируем текст и кнопки со временем
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        weekday_name = weekdays[selected_date.weekday()]
        
        text = f"""📋 <b>Выбранная дата: {selected_date.strftime('%d.%m.%Y')} ({weekday_name})</b>

💼 Услуга: {service_title}
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
        # Получаем данные услуги и мастера внутри сессии
        service_obj = session.query(Service).filter_by(id=service_id).first()
        if not service_obj:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        from bot.database.models import MasterAccount
        master_obj = session.query(MasterAccount).filter_by(id=master_id).first()
        if not master_obj:
            await query.message.edit_text("❌ Мастер не найден")
            return ConversationHandler.END
        
        # Получаем значения атрибутов внутри сессии
        service_title = service_obj.title
        master_name = master_obj.name
        master_currency = master_obj.currency if master_obj.currency else 'RUB'
        master_id_for_callback = master_obj.id
        
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
        
        from bot.utils.currency import format_price
        price_formatted = format_price(price, master_currency)
        
        text = f"""📋 <b>Подтверждение записи</b>

👤 Мастер: <b>{master_name}</b>
💼 Услуга: {service_title}
📅 Дата: {selected_date.strftime('%d.%m.%Y')} ({weekdays[selected_date.weekday()]})
⏰ Время: {time_str} - {end_time.strftime('%H:%M')}
💰 Цена: {price_formatted}

Вы можете добавить комментарий (опционально), или нажмите "Подтвердить" для завершения записи."""
        
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
        
        from bot.utils.currency import format_price
        price_formatted = format_price(price, master.currency)
        
        text = f"""📋 <b>Подтверждение записи</b>

👤 Мастер: <b>{master.name}</b>
💼 Услуга: {service.title}
📅 Дата: {selected_date.strftime('%d.%m.%Y')} ({weekdays[selected_date.weekday()]})
⏰ Время: {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}
💰 Цена: {price_formatted}"""
        
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
        
        from bot.utils.currency import format_price
        
        # Получаем валюту мастера
        with get_session() as session:
            from bot.database.models import MasterAccount
            master_obj = session.query(MasterAccount).filter_by(telegram_id=master_telegram_id).first()
            master_currency = master_obj.currency if master_obj else 'RUB'
        
        price_formatted = format_price(price, master_currency)
        
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        
        text = f"""🔔 <b>Новая запись!</b>

👤 Клиент: <b>{client_name}</b>
💼 Услуга: {service_title}
📅 Дата и время: {start_dt.strftime('%d.%m.%Y %H:%M')} ({weekdays[start_dt.weekday()]})
💰 Цена: {price_formatted}"""
        
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
        master_currency = master.currency if master else 'RUB'
        
        # Очищаем данные
        context.user_data.clear()
        
        from bot.utils.currency import format_price
        price_formatted = format_price(price, master_currency)
        
        text = f"""✅ <b>Запись успешно создана!</b>

👤 Мастер: <b>{master_name}</b>
💼 Услуга: {service_title}
📅 Дата и время: {start_dt.strftime('%d.%m.%Y %H:%M')}
💰 Цена: {price_formatted}"""
        
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


async def client_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройки клиента - управление мастерами"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        links = get_client_masters(session, client_user)
        
        if not links:
            text = "⚙️ <b>Настройки</b>\n\n"
            text += "У вас пока нет добавленных мастеров."
            
            keyboard = [
                [InlineKeyboardButton("« Назад", callback_data="client_menu")]
            ]
        else:
            text = "⚙️ <b>Настройки</b>\n\n"
            text += "🗑 <b>Управление мастерами</b>\n\n"
            text += "Выберите мастера для удаления из вашего списка:\n\n"
            
            keyboard = []
            for link in links:
                master = link.master_account
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 {master.name}",
                        callback_data=f"remove_master_{master.id}"
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


def get_client_menu_buttons():
    """Получить кнопки главного меню клиента (для автоматической синхронизации команд)"""
    return [
        [InlineKeyboardButton("👥 Мои мастера", callback_data="client_masters")],
        [InlineKeyboardButton("🔍 Найти мастеров", callback_data="client_search_masters")],
        [InlineKeyboardButton("👤➡️ Пригласить мастера", callback_data="client_invite_master")],
        [InlineKeyboardButton("📋 Мои записи", callback_data="client_bookings")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="client_settings")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="client_help")]
    ]


def get_client_menu_commands():
    """Автоматически генерировать список команд на основе кнопок меню"""
    from telegram import BotCommand
    
    # Маппинг callback_data → (команда, описание)
    callback_to_command = {
        "client_masters": ("masters", "Мои мастера"),
        "client_search_masters": ("search", "Найти мастеров"),
        "client_invite_master": ("invite", "Пригласить мастера"),
        "client_bookings": ("bookings", "Мои записи"),
        "client_settings": ("settings", "Настройки"),
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
    
    text = """ℹ️ <b>Помощь</b>

<b>Как записаться к мастеру?</b>
1. Попросите мастера отправить вам QR-код или ссылку
2. Перейдите по ссылке или отсканируйте QR
3. Мастер автоматически добавится в ваш список
4. Выберите услугу и запишитесь!

<b>Как удалить мастера?</b>
Откройте "⚙️ Настройки" в главном меню и выберите мастера для удаления

<b>Как посмотреть свои записи?</b>
Нажмите "Мои записи" в главном меню

<b>Как связаться с мастером?</b>
Откройте профиль мастера и нажмите "💬 Связаться с мастером" """
    
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


async def client_invite_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пригласить мастера зарегистрироваться в сервисе"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    
    # Получаем username мастер-бота через Bot API
    master_bot_username = None
    try:
        if BOT_TOKEN:
            master_bot = Bot(token=BOT_TOKEN)
            bot_info = await master_bot.get_me()
            master_bot_username = bot_info.username
    except Exception as e:
        logger.warning(f"Не удалось получить username мастер-бота: {e}")
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        
        # Генерируем deep link для приглашения мастера
        if master_bot_username:
            invite_link = f"https://t.me/{master_bot_username}?start=invite_client_{client_user.id}"
        else:
            invite_link = f"Используйте команду /start invite_client_{client_user.id} в мастер-боте"
        
        # Формируем текст, обращенный к мастеру (аналогично master_qr)
        text = f"👤➡️ <b>Пригласить мастера</b>\n\n"
        text += f"Отправьте эту ссылку мастеру:\n\n"
        if master_bot_username:
            text += f"<a href=\"{invite_link}\">{invite_link}</a>\n\n"
        else:
            text += f"<code>{invite_link}</code>\n\n"
        
        keyboard = [
            [InlineKeyboardButton("📋 Копировать ссылку", callback_data=f"client_copy_link_{client_user.id}")],
            [InlineKeyboardButton("« Назад", callback_data="client_menu")]
        ]
        
        # Генерируем QR код
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invite_link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Сохраняем в память
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        bio.seek(0)
        
        if query:
            await query.message.delete()
            await query.message.chat.send_photo(
                photo=bio,
                caption=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_photo(
                photo=bio,
                caption=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def client_copy_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Копировать ссылку для приглашения мастера"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID клиента из callback_data: client_copy_link_1
    client_id = int(query.data.split('_')[3])
    
    user = update.effective_user
    
    # Получаем username мастер-бота через Bot API
    master_bot_username = None
    try:
        if BOT_TOKEN:
            master_bot = Bot(token=BOT_TOKEN)
            bot_info = await master_bot.get_me()
            master_bot_username = bot_info.username
    except Exception as e:
        logger.warning(f"Не удалось получить username мастер-бота: {e}")
    
    with get_session() as session:
        client_user = get_or_create_user(session, user.id)
        
        # Проверяем, что клиент соответствует
        if client_user.id != client_id:
            await query.message.edit_text("❌ Ошибка доступа")
            return
        
        # Генерируем deep link для приглашения мастера
        if master_bot_username:
            invite_link = f"https://t.me/{master_bot_username}?start=invite_client_{client_user.id}"
        else:
            invite_link = f"Используйте команду /start invite_client_{client_user.id} в мастер-боте"
        
        text = f"🔗 <b>Ваша ссылка для приглашения мастера</b>\n\n"
        text += f"Отправьте эту ссылку мастеру:\n\n"
        if master_bot_username:
            text += f"<a href=\"{invite_link}\">{invite_link}</a>"
        else:
            text += f"<code>{invite_link}</code>"
        
        keyboard = [
            [InlineKeyboardButton("📋 QR-код", callback_data="client_invite_master")],
            [InlineKeyboardButton("« Назад", callback_data="client_menu")]
        ]
        
        # Проверяем, есть ли фото в сообщении
        if query.message.photo:
            # Если есть фото, удаляем сообщение и отправляем новое текстовое
            try:
                await query.message.delete()
            except:
                pass
            await query.message.chat.send_message(
                text=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Если нет фото, редактируем текст
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def client_search_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск мастеров по городам"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Сбрасываем состояние поиска при новом запросе
    state = _get_client_search_state(context)
    state.clear()
    
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
        text += "1️⃣ Выберите город\n"
        text += "2️⃣ Уточните категорию и услугу\n"
        text += "3️⃣ Получите список мастеров\n\n"
        text += "Доступные города:\n\n"
        
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
    """Выбор категории после выбора города"""
    query = update.callback_query
    await query.answer()
    
    city_id = int(query.data.split('_')[2])
    state = _get_client_search_state(context)
    state.clear()
    state['city_id'] = city_id
    
    with get_session() as session:
        from bot.database.models import City, MasterAccount
        city = session.query(City).filter_by(id=city_id).first()
        
        if not city:
            await query.message.edit_text(
                "❌ Город не найден",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")
                ]])
            )
            return
        
        state['city_name'] = city.name_ru
        
        category_items = _build_category_items(session, city_id)
        state['categories'] = category_items
        state['selected_category_idx'] = None
        state['selected_service_idx'] = None
        
        total_masters = session.query(MasterAccount).filter_by(city_id=city_id, is_blocked=False).count()
        logger.info(
            f"Client search city {city_id} ({city.name_ru}): "
            f"{len(category_items)} categories, total masters {total_masters}"
        )
        
        if not category_items:
            text = f"🔍 <b>Город: {city.name_ru}</b>\n\n"
            if total_masters == 0:
                text += "❌ В этом городе пока нет мастеров.\n\n"
            else:
                text += "ℹ️ Мастера в этом городе еще не добавили услуги.\n\n"
            text += "Выберите другой город или посмотрите общий список мастеров."
            
            keyboard = [
                [InlineKeyboardButton("📋 Все мастера города", callback_data=f"search_city_all_{city_id}")],
                [InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        text, markup = _compose_categories_markup(city.name_ru, city_id, category_items)
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=markup
        )


async def client_search_categories_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к списку категорий для текущего города"""
    query = update.callback_query
    await query.answer()
    
    state = _get_client_search_state(context)
    city_id = state.get('city_id')
    if city_id is None:
        await query.message.edit_text(
            "ℹ️ Пожалуйста, выберите город заново.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« К городам", callback_data="client_search_masters")]])
        )
        return
    
    # Очищаем временные данные пагинации
    state.pop('current_masters_list', None)
    state.pop('current_display_type', None)
    state.pop('current_category_idx', None)
    state.pop('current_service_idx', None)
    state.pop('selected_service_idx', None)
    state.pop('current_total_master_ids', None)
    state.pop('current_total_city_masters', None)
    state.pop('current_total_category_masters', None)
    state.pop('current_page', None)
    
    categories = state.get('categories')
    city_name = state.get('city_name')
    
    with get_session() as session:
        from bot.database.models import City, MasterAccount
        if categories is None:
            categories = _build_category_items(session, city_id)
            state['categories'] = categories
        if city_name is None:
            city = session.query(City).filter_by(id=city_id).first()
            city_name = city.name_ru if city else "неизвестный город"
            state['city_name'] = city_name
        total_masters = session.query(MasterAccount).filter_by(city_id=city_id, is_blocked=False).count()
    
    if not categories:
        text = f"🔍 <b>Город: {city_name}</b>\n\n"
        if total_masters == 0:
            text += "❌ В этом городе пока нет мастеров.\n\n"
        else:
            text += "ℹ️ Мастера в этом городе еще не добавили услуги.\n\n"
        text += "Выберите другой город или посмотрите общий список мастеров."
        
        keyboard = [
            [InlineKeyboardButton("📋 Все мастера города", callback_data=f"search_city_all_{city_id}")],
            [InlineKeyboardButton("« Назад к городам", callback_data="client_search_masters")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text, markup = _compose_categories_markup(city_name, city_id, categories)
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=markup
    )


async def client_search_category_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор услуги после выбора категории"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    category_idx = int(parts[-1])
    
    try:
        text, markup = _compose_services_response(context, category_idx)
    except ValueError:
        await query.message.edit_text(
            "ℹ️ Данные устарели. Пожалуйста, начните поиск заново.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« К городам", callback_data="client_search_masters")]])
        )
        return
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=markup
    )


async def client_search_services_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к списку услуг выбранной категории"""
    query = update.callback_query
    await query.answer()
    
    state = _get_client_search_state(context)
    # Используем current_category_idx если есть, иначе selected_category_idx
    selected_category_idx = state.get('current_category_idx') or state.get('selected_category_idx')
    if selected_category_idx is None:
        await client_search_categories_back(update, context)
        return
    
    try:
        text, markup = _compose_services_response(context, selected_category_idx)
        # Очищаем временные данные пагинации
        state.pop('current_masters_list', None)
        state.pop('current_display_type', None)
        state.pop('current_category_idx', None)
        state.pop('current_service_idx', None)
        state.pop('current_total_master_ids', None)
        state.pop('current_total_category_masters', None)
        state.pop('current_total_city_masters', None)
        state.pop('current_page', None)
    except ValueError:
        await query.message.edit_text(
            "ℹ️ Данные устарели. Пожалуйста, начните поиск заново.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« К городам", callback_data="client_search_masters")]])
        )
        return
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=markup
    )


async def client_search_category_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать всех мастеров выбранной категории"""
    query = update.callback_query
    await query.answer()
    
    state = _get_client_search_state(context)
    
    # Проверяем, это выбор категории или пагинация
    if query.data.startswith('masters_page_category_'):
        # Пагинация для категории
        page = int(query.data.split('_')[3])
        masters_data = state.get('current_masters_list', [])
        display_type = 'category'
    else:
        # Выбор "Все мастера категории"
        selected_category_idx = state.get('selected_category_idx')
        if selected_category_idx is None:
            await client_search_categories_back(update, context)
            return
        
        categories = state.get('categories') or []
        if selected_category_idx >= len(categories):
            await client_search_categories_back(update, context)
            return
        
        category_item = categories[selected_category_idx]
        city_id = state.get('city_id')
        user = update.effective_user
        page = 0
        
        with get_session() as session:
            masters = _filter_masters_for_client(session, category_item['master_ids'], user.id)
            total_in_category = len(category_item['master_ids'])
            
            # Извлекаем данные мастеров внутри сессии
            masters_data = []
            for master in masters:
                masters_data.append({
                    "id": master.id,
                    "name": master.name,
                    "currency": master.currency or 'RUB'
                })
        
        # Сохраняем список мастеров для пагинации
        state['current_masters_list'] = masters_data
        state['current_display_type'] = 'category'
        state['current_category_idx'] = selected_category_idx
        state['current_total_category_masters'] = total_in_category
        display_type = 'category'
    
    # Формируем текст и клавиатуру
    city_name = state.get('city_name', 'неизвестный город')
    categories = state.get('categories') or []
    selected_category_idx = state.get('current_category_idx') or state.get('selected_category_idx')
    total_in_category = state.get('current_total_category_masters', 0)
    
    if selected_category_idx is not None and selected_category_idx < len(categories):
        category_item = categories[selected_category_idx]
        text = f"🔍 <b>{city_name}</b>\n"
        text += f"Категория: <b>{category_item['title']}</b>\n\n"
    else:
        text = f"🔍 <b>{city_name}</b>\n\n"
    
    state['current_page'] = page
    keyboard = []
    
    if not masters_data:
        if total_in_category == 0:
            text += "❌ Пока нет мастеров в этой категории.\n\n"
        else:
            text += "✅ Все мастера из этой категории уже есть в вашем списке.\n\n"
    else:
        page_text, page_keyboard, total_pages = _format_masters_list_page(masters_data, page, MASTERS_PER_PAGE, display_type)
        text += page_text
        keyboard = page_keyboard
    
    # Кнопка назад - только "Назад к услугам" (если есть услуги) или "Назад к категориям"
    if state.get('services'):
        keyboard.append([InlineKeyboardButton("« Назад к услугам", callback_data="search_services_back")])
    else:
        keyboard.append([InlineKeyboardButton("« Назад к категориям", callback_data="search_categories_back")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def client_search_service_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать мастеров, оказывающих выбранную услугу"""
    query = update.callback_query
    await query.answer()
    
    state = _get_client_search_state(context)
    
    # Проверяем, это выбор услуги или пагинация
    if query.data.startswith('masters_page_service_'):
        # Пагинация для услуги
        page = int(query.data.split('_')[3])
        masters_data = state.get('current_masters_list', [])
        display_type = 'service'
    else:
        # Выбор услуги
        parts = query.data.split('_')
        service_idx = int(parts[-1])
        page = 0
        
        services = state.get('services') or []
        categories = state.get('categories') or []
        selected_category_idx = state.get('selected_category_idx')
        city_id = state.get('city_id')
        user = update.effective_user
        
        if (
            city_id is None
            or selected_category_idx is None
            or selected_category_idx >= len(categories)
            or service_idx >= len(services)
        ):
            await query.message.edit_text(
                "ℹ️ Данные устарели. Пожалуйста, начните поиск заново.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« К городам", callback_data="client_search_masters")]])
            )
            return
        
        category_item = categories[selected_category_idx]
        service_item = services[service_idx]
        state['selected_service_idx'] = service_idx
        
        with get_session() as session:
            masters = _filter_masters_for_client(session, service_item['master_ids'], user.id)
            total_master_ids = len(service_item['master_ids'])
            
            # Загружаем все необходимые данные мастеров внутри сессии
            masters_data = []
            for master in masters:
                service_info = service_item['master_services'].get(master.id)
                master_data = {
                    "id": master.id,
                    "name": master.name,
                    "currency": master.currency or 'RUB',
                    "service_info": service_info
                }
                masters_data.append(master_data)
        
        # Сохраняем список мастеров для пагинации
        state['current_masters_list'] = masters_data
        state['current_display_type'] = 'service'
        state['current_service_idx'] = service_idx
        state['current_category_idx'] = selected_category_idx
        state['current_total_master_ids'] = total_master_ids
        display_type = 'service'
    
    # Формируем текст и клавиатуру
    city_name = state.get('city_name', 'неизвестный город')
    categories = state.get('categories') or []
    services = state.get('services') or []
    selected_category_idx = state.get('current_category_idx') or state.get('selected_category_idx')
    service_idx = state.get('current_service_idx') or state.get('selected_service_idx')
    total_master_ids = state.get('current_total_master_ids', 0)
    
    if selected_category_idx is not None and selected_category_idx < len(categories):
        category_item = categories[selected_category_idx]
        text = f"🔍 <b>{city_name}</b>\n"
        text += f"Категория: <b>{category_item['title']}</b>\n"
        if service_idx is not None and service_idx < len(services):
            service_item = services[service_idx]
            text += f"Услуга: <b>{service_item['title']}</b>\n\n"
        else:
            text += "\n"
    else:
        text = f"🔍 <b>{city_name}</b>\n\n"
    
    state['current_page'] = page
    keyboard = []
    
    if not masters_data:
        if total_master_ids == 0:
            text += "❌ Пока нет мастеров, предлагающих эту услугу.\n\n"
        else:
            text += "✅ Все мастера с этой услугой уже есть в вашем списке.\n\n"
    else:
        page_text, page_keyboard, total_pages = _format_masters_list_page(masters_data, page, MASTERS_PER_PAGE, display_type)
        text += page_text
        keyboard = page_keyboard
    
    # Кнопка назад - только "Назад к услугам"
    keyboard.append([InlineKeyboardButton("« Назад к услугам", callback_data="search_services_back")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def client_search_city_all_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать всех мастеров в городе без фильтров"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, это выбор "Все мастера города" или пагинация
    if query.data.startswith('masters_page_city_'):
        # Пагинация для города
        page = int(query.data.split('_')[3])
        state = _get_client_search_state(context)
        masters_data = state.get('current_masters_list', [])
        city_id = state.get('city_id')
        display_type = state.get('current_display_type', 'city')
        if not masters_data:
            page = 0
            display_type = 'city'
    else:
        # Выбор "Все мастера города"
        city_id = int(query.data.split('_')[3])
        user = update.effective_user
        state = _get_client_search_state(context)
        state['city_id'] = city_id
        state['selected_category_idx'] = None
        state['selected_service_idx'] = None
        page = 0
        
        with get_session() as session:
            from bot.database.models import City
            city = session.query(City).filter_by(id=city_id).first()
            if not city:
                await query.message.edit_text(
                    "❌ Город не найден",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="client_search_masters")]])
                )
                return
            
            masters = (
                session.query(MasterAccount)
                .filter_by(city_id=city_id, is_blocked=False)
                .order_by(MasterAccount.name.asc())
                .all()
            )
            total_in_city = len(masters)
            
            client_user = get_or_create_user(session, user.id)
            existing_ids = set()
            if client_user:
                existing_ids = {
                    link.master_account_id
                    for link in session.query(UserMaster).filter_by(user_id=client_user.id).all()
                }
            
            masters_data = [
                {
                    "id": master.id,
                    "name": master.name,
                    "already_added": master.id in existing_ids,
                    "currency": master.currency or 'RUB'
                }
                for master in masters
            ]
            city_name = city.name_ru
            state['city_name'] = city_name
        
        # Сохраняем список мастеров для пагинации
        state['current_masters_list'] = masters_data
        state['current_display_type'] = 'city'
        state['current_total_city_masters'] = total_in_city
        display_type = 'city'
    total_in_city = state.get('current_total_city_masters', len(masters_data))
    
    # Формируем текст и клавиатуру
    state = _get_client_search_state(context)
    city_name = state.get('city_name', 'неизвестный город')
    text = f"🔍 <b>{city_name}</b>\n\n"
    
    keyboard = []
    
    state['current_page'] = page

    if not masters_data:
        if total_in_city == 0:
            text += "❌ В этом городе пока нет мастеров.\n\n"
        else:
            text += "✅ Все мастера этого города уже есть в вашем списке.\n\n"
    else:
        page_text, page_keyboard, total_pages = _format_masters_list_page(masters_data, page, MASTERS_PER_PAGE, display_type)
        text += page_text
        keyboard = page_keyboard
    
    # Кнопка назад - только "Назад к категориям"
    keyboard.append([InlineKeyboardButton("« Назад к категориям", callback_data=f"search_city_{city_id}")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _update_master_view_message(query, master_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Вспомогательная функция для обновления сообщения с мастером"""
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        # Проверяем, не добавлен ли уже этот мастер
        client_user = get_or_create_user(session, user_id)
        from bot.database.models import UserMaster
        existing_link = session.query(UserMaster).filter_by(
            user_id=client_user.id,
            master_account_id=master_id
        ).first()
        
        # Получаем услуги мастера
        services = get_services_by_master(session, master.id, active_only=True)
        
        # Загружаем город мастера внутри сессии
        city_name = None
        if master.city_id:
            from bot.database.models import City
            city = session.query(City).filter_by(id=master.city_id).first()
            if city:
                city_name = city.name_ru
        
        # Извлекаем все необходимые данные мастера внутри сессии
        master_name = master.name
        master_description = master.description
        master_currency = master.currency or 'RUB'
        master_avatar = master.avatar_url
        master_telegram_id = master.telegram_id
        
        # Извлекаем данные услуг внутри сессии
        services_data = []
        for svc in services:
            services_data.append({
                "title": svc.title,
                "price": svc.price,
                "duration_mins": svc.duration_mins
            })
        
        state = _get_client_search_state(context)
        
        # Проверяем статус добавления для отображения информационного сообщения
        is_master_added = existing_link is not None
        
        # Формируем текст
        text = ""
        if is_master_added:
            text += "✅ <b>Мастер добавлен в ваш список</b>\n\n"
        
        text += f"👤 <b>{master_name}</b>\n\n"
        
        if city_name:
            text += f"📍 Город: {city_name}\n"
        
        if master_description:
            text += f"📝 {master_description}\n\n"
        else:
            text += "📝 <i>Описание не указано</i>\n\n"
        
        text += f"💼 <b>Услуги ({len(services_data)}):</b>\n"
        
        if services_data:
            # Показываем первые 5 услуг
            for svc_data in services_data[:5]:
                price_formatted = format_price(svc_data['price'], master_currency)
                text += f"  • {svc_data['title']} — {price_formatted} ({svc_data['duration_mins']} мин)\n"
            if len(services_data) > 5:
                text += f"  <i>... и еще {len(services_data) - 5}</i>\n"
        else:
            text += "<i>Услуги не добавлены</i>\n"
        
        keyboard = []
        
        if not existing_link:
            # Если мастер еще не добавлен, показываем кнопку добавления
            keyboard.append([
                InlineKeyboardButton("➕ Добавить", callback_data=f"search_add_master_{master_id}")
            ])
        else:
            # Если уже добавлен, показываем кнопку удаления
            keyboard.append([
                InlineKeyboardButton("🗑 Удалить", callback_data=f"search_remove_master_{master_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("📋 Записаться", callback_data=f"book_master_{master_id}")
        ])
        
        # Добавляем кнопку для связи с мастером
        if master_telegram_id:
            keyboard.append([
                InlineKeyboardButton(
                    "💬 Написать мастеру",
                    url=f"tg://user?id={master_telegram_id}"
                )
            ])
        
        # Определяем, откуда вернуться
        back_buttons = []
        display_type = state.get('current_display_type')
        current_page = state.get('current_page', 0)
        if display_type == 'service':
            back_buttons.append(
                InlineKeyboardButton(
                    "« Назад к списку мастеров",
                    callback_data=f"masters_page_service_{current_page}"
                )
            )
        elif display_type == 'category':
            back_buttons.append(
                InlineKeyboardButton(
                    "« Назад к мастерам категории",
                    callback_data=f"masters_page_category_{current_page}"
                )
            )
        elif display_type == 'city':
            back_buttons.append(
                InlineKeyboardButton(
                    "« Назад к мастерам города",
                    callback_data=f"masters_page_city_{current_page}"
                )
            )
        else:
            if state.get('selected_service_idx') is not None and state.get('services'):
                back_buttons.append(
                    InlineKeyboardButton(
                        "« Назад к услугам",
                        callback_data="search_services_back"
                    )
                )
            elif state.get('selected_category_idx') is not None:
                back_buttons.append(
                    InlineKeyboardButton(
                        "« Назад к категориям",
                        callback_data="search_categories_back"
                    )
                )
            else:
                back_buttons.append(
                    InlineKeyboardButton(
                        "« Назад к городам",
                        callback_data="client_search_masters"
                    )
                )
        
        keyboard.extend([[button] for button in back_buttons])
        
        # Определяем, какое фото использовать
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
                # Если не получилось скачать фото профиля, отправляем без фото
                photo_to_send = None
        
        # Отправляем сообщение с фото или без
        try:
            # Проверяем, есть ли фото в текущем сообщении
            has_photo_in_message = query.message.photo is not None and len(query.message.photo) > 0
            
            if photo_to_send:
                # Если есть фото для отправки
                if has_photo_in_message:
                    # Редактируем медиа (фото) с новым текстом
                    from telegram import InputMediaPhoto
                    await query.message.edit_media(
                        media=InputMediaPhoto(
                            media=photo_to_send,
                            caption=photo_caption,
                            parse_mode='HTML'
                        ),
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    # Если в сообщении не было фото, удаляем и отправляем новое с фото
                    # (нельзя изменить текстовое сообщение на фото)
                    try:
                        await query.message.delete()
                    except:
                        pass
                    await query.message.chat.send_photo(
                        photo=photo_to_send,
                        caption=photo_caption,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
            else:
                # Если нет фото, просто редактируем текст
                await query.message.edit_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logger.error(f"Error sending master profile: {e}", exc_info=True)
            # Если произошла ошибка, отправляем без фото
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
    
    # Используем вспомогательную функцию для обновления сообщения
    await _update_master_view_message(query, master_id, user.id, context)


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
        
        # Проверяем, не добавлен ли уже этот мастер
        from bot.database.models import UserMaster
        existing_link = session.query(UserMaster).filter_by(
            user_id=client_user.id,
            master_account_id=master_id
        ).first()
        
        if existing_link:
            # Если мастер уже добавлен, просто показываем сообщение
            await query.answer("✅ Мастер уже добавлен в ваш список!", show_alert=False)
        else:
            # Добавляем связь
            link = add_user_master_link(session, client_user, master)
            logger.info(f"Master {master_id} added to user {user.id} from search")
            await query.answer("✅ Мастер добавлен в ваш список!", show_alert=False)
        
        # После добавления мастера обновляем сообщение, показывая статус добавления
        # Используем вспомогательную функцию для обновления сообщения
        await _update_master_view_message(query, master_id, user.id, context)


async def client_search_remove_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить мастера из поиска"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID мастера из callback_data: search_remove_master_1
    master_id = int(query.data.split('_')[3])
    
    user = update.effective_user
    
    with get_session() as session:
        from bot.database.models import MasterAccount
        master = session.query(MasterAccount).filter_by(id=master_id).first()
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        client_user = get_or_create_user(session, user.id)
        
        # Проверяем, добавлен ли этот мастер
        from bot.database.models import UserMaster
        existing_link = session.query(UserMaster).filter_by(
            user_id=client_user.id,
            master_account_id=master_id
        ).first()
        
        if not existing_link:
            # Если мастер не был добавлен, просто показываем сообщение
            await query.answer("ℹ️ Мастер не был в вашем списке", show_alert=False)
        else:
            # Удаляем связь
            remove_user_master_link(session, client_user, master)
            logger.info(f"Master {master_id} removed from user {user.id} from search")
            await query.answer("✅ Мастер удален из вашего списка!", show_alert=False)
        
        # После удаления мастера обновляем сообщение
        # Используем вспомогательную функцию для обновления сообщения
        await _update_master_view_message(query, master_id, user.id, context)


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

