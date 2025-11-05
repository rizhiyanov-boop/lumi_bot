"""Обработчики для мастер-бота"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    create_master_account,
    get_services_by_master,
    create_service_category,
    get_categories_by_master,
    get_category_by_id,
    get_or_create_predefined_category,
    create_service,
    get_service_by_id,
    update_service,
    delete_service,
    get_master_clients_count,
    get_work_periods,
    get_work_periods_by_weekday,
    set_work_period,
    delete_work_period,
    delete_all_work_periods_for_day,
    get_bookings_for_master,
    get_bookings_for_master_in_range,
    is_superadmin,
    update_master_subscription,
    create_payment_record,
    update_payment_status,
    get_payment_by_id,
    add_portfolio_photo,
    get_portfolio_photos,
    delete_portfolio_photo,
    get_portfolio_limit
)
from bot.utils.schedule_utils import validate_schedule_period, parse_time, format_time, add_minutes_to_time, check_time_overlap
from bot.utils.impersonation import get_master_telegram_id, is_impersonating, get_impersonation_banner
from bot.data.service_templates import get_predefined_categories_list, get_category_info, get_category_templates
from bot.config import CLIENT_BOT_USERNAME, PREMIUM_PRICE, PREMIUM_DURATION_DAYS
from bot.utils.yookassa_api import create_premium_payment, get_payment_status
from datetime import datetime, timedelta, date
import qrcode
from PIL import Image, ImageDraw, ImageFont
import io
import os

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_NAME, WAITING_DESCRIPTION = range(2)
WAITING_CATEGORY_NAME = 2  # Для добавления категории
WAITING_CATEGORY = 3  # Выбор категории
WAITING_TEMPLATE = 4  # Выбор шаблона или создание с нуля
WAITING_SERVICE_NAME = 5  # Ввод названия (если создание с нуля)
WAITING_SERVICE_PRICE = 6  # Ввод цены
WAITING_SERVICE_DURATION = 7  # Ввод длительности (если создание с нуля)
WAITING_SERVICE_DESCRIPTION = 8  # Ввод описания
WAITING_SERVICE_COOLING = 9  # Ввод времени охлаждения (расширенные настройки)
WAITING_SERVICE_ADVANCED = 10  # Расширенные настройки (опционально)
# Состояния для редактирования услуги
WAITING_EDIT_SERVICE_NAME = 11
WAITING_EDIT_SERVICE_PRICE = 12
WAITING_EDIT_SERVICE_DURATION = 13
WAITING_EDIT_SERVICE_COOLING = 14
# Состояния для расписания
WAITING_SCHEDULE_DAY, WAITING_SCHEDULE_START, WAITING_SCHEDULE_END, WAITING_SCHEDULE_START_MANUAL, WAITING_SCHEDULE_END_MANUAL = range(14, 19)


def get_onboarding_status(session, master_id: int) -> dict:
    """Получить статус онбординга мастера"""
    services = get_services_by_master(session, master_id, active_only=True)
    work_periods = get_work_periods(session, master_id)
    
    has_services = len(services) > 0
    has_schedule = len(work_periods) > 0
    
    return {
        'has_services': has_services,
        'has_schedule': has_schedule,
        'is_complete': has_services and has_schedule
    }


def get_master_menu_commands():
    """Получить команды главного меню для автоматической синхронизации"""
    from telegram import BotCommand
    return [
        BotCommand("start", "Главное меню"),
        BotCommand("bookings", "Ваши записи"),
        BotCommand("qr", "Пригласить клиента"),
        BotCommand("settings", "Настройки")
    ]


async def start_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовая команда для мастера"""
    user = update.effective_user
    
    with get_session() as session:
        master = get_master_by_telegram(session, user.id)
        
        if not master:
            # Создаем нового мастера
            name = user.full_name or user.first_name or "Мастер"
            master = create_master_account(session, user.id, name)
            logger.info(f"Created new master account: {master.id}")
        
        # Проверяем статус онбординга
        onboarding_status = get_onboarding_status(session, master.id)
        
        text = f"👋 Добро пожаловать, <b>{master.name}</b>!\n\n"
        
        if not onboarding_status['is_complete']:
            text += "📋 <b>Начните с настройки:</b>\n\n"
            if not onboarding_status['has_services']:
                text += "1️⃣ Добавьте услуги\n"
            if not onboarding_status['has_schedule']:
                text += "2️⃣ Настройте расписание\n"
        else:
            text += "✅ Настройка завершена!\n\n"
        
        text += get_impersonation_banner(context)
        
        keyboard = [
            [InlineKeyboardButton("💼 Ваши услуги", callback_data="master_services")],
            [InlineKeyboardButton("📅 Расписание", callback_data="master_schedule")],
        ]
        
        if onboarding_status['is_complete']:
            keyboard.append([InlineKeyboardButton("👤➡️ Пригласить клиента", callback_data="master_qr")])
            keyboard.append([InlineKeyboardButton("📋 Записи", callback_data="master_bookings")])
        
        keyboard.append([InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")])
        
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


async def master_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Профиль мастера"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        text = f"👤 <b>Профиль</b>\n\n"
        text += f"📌 Имя: <b>{master.name}</b>\n"
        if master.description:
            text += f"📝 Описание: {master.description}\n"
        text += f"🆔 ID: <code>{master.id}</code>\n\n"
        text += get_impersonation_banner(context)
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить имя", callback_data="edit_name")],
            [InlineKeyboardButton("✏️ Изменить описание", callback_data="edit_description")],
            [InlineKeyboardButton("🖼 Загрузить фото", callback_data="upload_photo")],
            [InlineKeyboardButton("📸 Портфолио", callback_data="master_portfolio")],
            [InlineKeyboardButton("« Назад", callback_data="master_menu")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ===== Команды для обработчиков =====

async def master_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile - показать профиль"""
    if update.message:
        # Создаем фиктивный callback_query для использования существующего обработчика
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_profile"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_profile(update, context)
    else:
        await master_profile(update, context)


async def master_services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /services - показать услуги"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_services"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_services(update, context)
    else:
        await master_services(update, context)


async def master_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /schedule - показать расписание"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_schedule"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_schedule(update, context)
    else:
        await master_schedule(update, context)


async def master_qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /qr - показать QR код"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_qr"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_qr(update, context)
    else:
        await master_qr(update, context)


async def master_bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /bookings - показать записи"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_bookings"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_bookings(update, context)
    else:
        await master_bookings(update, context)


# ===== Основные обработчики меню =====

async def master_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список услуг мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        # Получаем услуги и категории
        services = get_services_by_master(session, master.id, active_only=False)
        categories = get_categories_by_master(session, master.id)
        
        # Группируем услуги по категориям
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
            
            status_icon = "✅" if svc.active else "❌"
            services_by_category[category_key].append({
                'id': svc.id,
                'title': svc.title,
                'price': svc.price,
                'duration': svc.duration_mins,
                'active': svc.active,
                'status_icon': status_icon
            })
        
        # Формируем текст
        total_services = sum(len(svcs) for svcs in services_by_category.values())
        text = f"💼 <b>Ваши услуги</b> ({total_services})\n\n"
        
        if services_by_category:
            for category_key, svcs in services_by_category.items():
                text += f"<b>{category_key}:</b>\n"
                for svc in svcs:
                    text += f"  {svc['status_icon']} {svc['title']} — {svc['price']}₽ ({svc['duration']} мин)\n"
                text += "\n"
        else:
            text += "<i>У вас пока нет услуг. Добавьте первую услугу!</i>\n"
        
        text += get_impersonation_banner(context)
        
        # Формируем клавиатуру
        keyboard = []
        
        # Кнопки для каждой услуги
        for category_key, svcs in services_by_category.items():
            for svc in svcs:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{svc['status_icon']} {svc['title']}",
                        callback_data=f"edit_service_{svc['id']}"
                    )
                ])
        
        # Кнопки управления
        keyboard.append([InlineKeyboardButton("➕ Добавить услугу", callback_data="add_service")])
        keyboard.append([InlineKeyboardButton("📁 Добавить категорию", callback_data="add_category")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_menu")])
        
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


async def master_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать расписание мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    text = "📅 <b>Расписание</b>\n\nЭта функция в разработке..."
    text += get_impersonation_banner(context)
    
    keyboard = [
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


async def master_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать QR код и ссылку для приглашения клиентов"""
    query = update.callback_query
    if query:
        await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        # Генерируем deep link
        if CLIENT_BOT_USERNAME:
            deep_link = f"https://t.me/{CLIENT_BOT_USERNAME}?start=m_{master.id}"
        else:
            deep_link = f"Используйте команду /start m_{master.id} в клиентском боте"
        
        text = f"👤➡️ <b>Пригласить клиента</b>\n\n"
        text += f"Отправьте эту ссылку клиенту:\n\n"
        text += f"<code>{deep_link}</code>\n\n"
        text += get_impersonation_banner(context)
        
        keyboard = [
            [InlineKeyboardButton("📋 Копировать ссылку", callback_data=f"copy_link_{master.id}")],
            [InlineKeyboardButton("« Назад", callback_data="master_menu")]
        ]
        
        # Генерируем QR код
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(deep_link)
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
        elif update.message:
            await update.message.reply_photo(
                photo=bio,
                caption=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def master_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать записи мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        bookings = get_bookings_for_master(session, master.id)
        
        text = f"📋 <b>Ваши записи</b> ({len(bookings)})\n\n"
        
        if bookings:
            # Показываем только будущие записи
            now = datetime.now()
            upcoming = [b for b in bookings if b.start_dt > now]
            
            if upcoming:
                for booking in upcoming[:10]:  # Показываем первые 10
                    service = booking.service
                    user = booking.user
                    date_str = booking.start_dt.strftime("%d.%m.%Y %H:%M")
                    text += f"📅 {date_str}\n"
                    text += f"   👤 Клиент: {user.telegram_id}\n"
                    text += f"   💼 {service.title}\n"
                    text += f"   💰 {booking.price}₽\n\n"
            else:
                text += "<i>Нет предстоящих записей</i>\n"
        else:
            text += "<i>У вас пока нет записей</i>\n"
        
        text += get_impersonation_banner(context)
        
        keyboard = [
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


# ===== Заглушки для остальных функций =====
# Эти функции нужно будет реализовать позже, но пока создаем заглушки для запуска

async def master_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Премиум подписка"""
    query = update.callback_query
    if query:
        await query.answer()
    
    text = "💎 <b>Премиум подписка</b>\n\nЭта функция в разработке..."
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="master_settings")]]
    
    if query:
        await query.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.message:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def premium_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата премиума"""
    pass


async def premium_check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса оплаты"""
    pass


async def edit_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование имени"""
    query = update.callback_query
    await query.answer()
    
    text = "✏️ <b>Изменение имени</b>\n\nВведите новое имя:"
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_profile")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_NAME


async def edit_description_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование описания"""
    query = update.callback_query
    await query.answer()
    
    text = "✏️ <b>Изменение описания</b>\n\nВведите новое описание:"
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_profile")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_DESCRIPTION


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое имя"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Имя слишком короткое. Минимум 2 символа.")
        return WAITING_NAME
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if master:
            from bot.database.models import MasterAccount
            master = session.query(MasterAccount).filter_by(id=master.id).first()
            master.name = text
            session.commit()
            
            await update.message.reply_text(f"✅ Имя изменено на: <b>{text}</b>", parse_mode='HTML')
            await master_profile(update, context)
    
    return ConversationHandler.END


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое описание"""
    text = update.message.text.strip()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if master:
            from bot.database.models import MasterAccount
            master = session.query(MasterAccount).filter_by(id=master.id).first()
            master.description = text
            session.commit()
            
            await update.message.reply_text("✅ Описание обновлено", parse_mode='HTML')
            await master_profile(update, context)
    
    return ConversationHandler.END


async def add_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление категории"""
    query = update.callback_query
    await query.answer()
    
    text = "📁 <b>Добавление категории</b>\n\nВведите название категории:"
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_services")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_CATEGORY_NAME


async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить название категории"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Название слишком короткое.")
        return WAITING_CATEGORY_NAME
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if master:
            # Извлекаем эмодзи из начала строки, если есть
            import re
            emoji_match = re.match(r'^([^\w\s]+)', text)
            emoji = emoji_match.group(1) if emoji_match else None
            
            if emoji:
                title = text[len(emoji):].strip()
            else:
                title = text
                emoji = "📁"
            
            category = create_service_category(session, master.id, title, emoji=emoji)
            await update.message.reply_text(f"✅ Категория <b>{emoji} {title}</b> добавлена!", parse_mode='HTML')
            await master_services(update, context)
    
    return ConversationHandler.END


# ===== Функции добавления услуги =====

async def add_service_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление услуги"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем данные предыдущего создания услуги
    service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
    for key in service_keys:
        del context.user_data[key]
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return ConversationHandler.END
        
        # Получаем предустановленные категории
        predefined_categories = get_predefined_categories_list()
        
        # Получаем пользовательские категории
        user_categories = get_categories_by_master(session, master.id)
        
        text = "💼 <b>Добавление услуги</b>\n\nВыберите категорию:"
        
        keyboard = []
        
        # Предустановленные категории
        for key, emoji, name in predefined_categories:
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {name}",
                    callback_data=f"service_category_predef_{key}"
                )
            ])
        
        # Пользовательские категории (сначала новые, потом старые)
        sorted_categories = sorted(user_categories, key=lambda x: x.id, reverse=True)
        for cat in sorted_categories:
            emoji = cat.emoji if cat.emoji else "📁"
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {cat.title}",
                    callback_data=f"service_category_{cat.id}"
                )
            ])
        
        # Кнопки "Другое" и "Отмена"
        keyboard.append([InlineKeyboardButton("➕ Другое", callback_data="service_category_custom")])
        keyboard.append([InlineKeyboardButton("« Отмена", callback_data="master_services")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_CATEGORY


async def service_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории при добавлении услуги"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return ConversationHandler.END
        
        # Определяем тип категории
        if data.startswith('service_category_predef_'):
            # Предустановленная категория
            category_key = data.replace('service_category_predef_', '')
            cat_info = get_category_info(category_key)
            
            if cat_info:
                # Получаем или создаем предустановленную категорию
                category = get_or_create_predefined_category(session, master.id, category_key)
                if category:
                    context.user_data['service_category_id'] = category.id
                    context.user_data['service_category_name'] = category.title
                else:
                    await query.message.edit_text("❌ Ошибка создания категории")
                    return ConversationHandler.END
            else:
                await query.message.edit_text("❌ Категория не найдена")
                return ConversationHandler.END
        elif data.startswith('service_category_') and data != 'service_category_custom':
            # Пользовательская категория
            try:
                category_id = int(data.replace('service_category_', ''))
                category = get_category_by_id(session, category_id)
                if category and category.master_account_id == master.id:
                    context.user_data['service_category_id'] = category.id
                    context.user_data['service_category_name'] = category.title
                else:
                    await query.message.edit_text("❌ Категория не найдена")
                    return ConversationHandler.END
            except ValueError:
                await query.message.edit_text("❌ Ошибка обработки категории")
                return ConversationHandler.END
        elif data == 'service_category_custom':
            # Создание новой категории
            context.user_data['service_creating_category'] = True
            await query.message.edit_text(
                "📁 Введите название новой категории:\n\n"
                "<i>Рекомендуем использовать эмодзи в названии для лучшей визуализации (например: 💅 Маникюр)</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Отмена", callback_data="master_services")
                ]])
            )
            return WAITING_CATEGORY_NAME
        
        # Получаем шаблоны для категории
        category_key = data.replace('service_category_predef_', '').replace('service_category_', '')
        if category_key and category_key != 'custom':
            templates = get_category_templates(category_key)
        else:
            templates = []
        
        category_name = context.user_data.get('service_category_name', '')
        text = f"💼 <b>Добавление услуги</b>\n\n"
        text += f"Категория: <b>{category_name}</b>\n\n"
        
        if templates:
            text += "Выберите шаблон или создайте с нуля:"
            keyboard = []
            
            for template in templates:
                keyboard.append([
                    InlineKeyboardButton(
                        template['name'],
                        callback_data=f"service_template_{template['name']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("➕ Создать с нуля", callback_data="service_template_none")])
            keyboard.append([InlineKeyboardButton("« Назад", callback_data="add_service")])
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING_TEMPLATE
        else:
            text += "Введите название услуги:"
            keyboard = [[InlineKeyboardButton("« Назад", callback_data="add_service")]]
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING_SERVICE_NAME


async def service_template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора шаблона"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    template_name = data.replace('service_template_', '')
    
    if template_name == 'none':
        # Пользователь выбрал "создать с нуля"
        text = "💼 <b>Добавление услуги</b>\n\nВведите название услуги:"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="add_service")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_NAME
    else:
        # Используем шаблон (пока просто сохраняем название)
        context.user_data['service_name'] = template_name
        text = f"💰 Введите цену услуги (в рублях, только число):"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_template")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_PRICE


async def receive_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить название услуги"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Минимум 2 символа.")
        return WAITING_SERVICE_NAME
    
    if len(text) > 100:
        await update.message.reply_text("❌ Название слишком длинное. Максимум 100 символов.")
        return WAITING_SERVICE_NAME
    
    context.user_data['service_name'] = text
    
    reply_text = "💰 Введите цену услуги (в рублях, только число):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]]
    
    await update.message.reply_text(
        reply_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_PRICE


async def receive_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить цену услуги"""
    try:
        price = float(update.message.text.strip().replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text("❌ Цена должна быть больше 0. Попробуйте снова:")
            return WAITING_SERVICE_PRICE
        
        if price > 1000000:
            await update.message.reply_text("❌ Цена слишком большая. Попробуйте снова:")
            return WAITING_SERVICE_PRICE
        
        context.user_data['service_price'] = price
        
        # Предлагаем выбрать длительность
        text = "⏱ Выберите длительность услуги (в минутах):"
        keyboard = [
            [InlineKeyboardButton("30 мин", callback_data="service_duration_30")],
            [InlineKeyboardButton("60 мин", callback_data="service_duration_60")],
            [InlineKeyboardButton("90 мин", callback_data="service_duration_90")],
            [InlineKeyboardButton("120 мин", callback_data="service_duration_120")],
            [InlineKeyboardButton("Другое (ввести вручную)", callback_data="service_duration_manual")],
            [InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_DURATION
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_SERVICE_PRICE


async def service_duration_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора длительности"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    duration_str = data.replace('service_duration_', '')
    
    if duration_str == 'manual':
        text = "⏱ Введите длительность услуги (в минутах, только число):"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_price")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_DURATION
    else:
        try:
            duration = int(duration_str)
            context.user_data['service_duration'] = duration
            return await service_advanced_settings(update, context)
        except ValueError:
            await query.message.edit_text("❌ Ошибка обработки длительности")
            return WAITING_SERVICE_DURATION


async def receive_service_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить длительность услуги"""
    try:
        duration = int(update.message.text.strip())
        
        if duration <= 0:
            await update.message.reply_text("❌ Длительность должна быть больше 0. Попробуйте снова:")
            return WAITING_SERVICE_DURATION
        
        if duration > 1440:
            await update.message.reply_text("❌ Длительность слишком большая (максимум 1440 минут). Попробуйте снова:")
            return WAITING_SERVICE_DURATION
        
        context.user_data['service_duration'] = duration
        return await service_advanced_settings(update, context)
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_SERVICE_DURATION


async def service_advanced_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать расширенные настройки"""
    query = update.callback_query if hasattr(update, 'callback_query') and update.callback_query else None
    
    duration = context.user_data.get('service_duration', 60)
    cooling = context.user_data.get('service_cooling', 0)
    
    text = f"⚙️ <b>Расширенные настройки</b>\n\n"
    text += f"Длительность: <b>{duration} мин</b>\n"
    text += f"Время охлаждения: <b>{cooling} мин</b>\n\n"
    text += "Выберите действие:"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить длительность", callback_data="service_change_duration")],
        [InlineKeyboardButton("🔄 Настроить время охлаждения", callback_data="service_set_cooling")],
        [InlineKeyboardButton("✅ Сохранить с настройками по умолчанию", callback_data="service_save_default")],
        [InlineKeyboardButton("« Назад", callback_data="service_back_to_price")]
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
    
    return WAITING_SERVICE_ADVANCED


async def service_change_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить длительность"""
    query = update.callback_query
    await query.answer()
    
    text = "⏱ Выберите длительность услуги (в минутах):"
    keyboard = [
        [InlineKeyboardButton("30 мин", callback_data="service_duration_30")],
        [InlineKeyboardButton("60 мин", callback_data="service_duration_60")],
        [InlineKeyboardButton("90 мин", callback_data="service_duration_90")],
        [InlineKeyboardButton("120 мин", callback_data="service_duration_120")],
        [InlineKeyboardButton("Другое (ввести вручную)", callback_data="service_duration_manual")],
        [InlineKeyboardButton("« Назад", callback_data="service_back_to_advanced")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_DURATION


async def receive_service_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время охлаждения"""
    try:
        cooling = int(update.message.text.strip())
        
        if cooling < 0:
            await update.message.reply_text("❌ Время охлаждения не может быть отрицательным. Попробуйте снова:")
            return WAITING_SERVICE_COOLING
        
        if cooling > 1440:
            await update.message.reply_text("❌ Время охлаждения слишком большое. Попробуйте снова:")
            return WAITING_SERVICE_COOLING
        
        context.user_data['service_cooling'] = cooling
        return await create_service_from_data(update, context)
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_SERVICE_COOLING


async def service_set_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настроить время охлаждения"""
    query = update.callback_query
    await query.answer()
    
    text = "🔄 Введите время охлаждения между записями (в минутах, только число, по умолчанию 0):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_advanced")]]
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_COOLING


async def service_save_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить услугу с настройками по умолчанию"""
    query = update.callback_query
    await query.answer()
    
    # Устанавливаем значения по умолчанию
    if 'service_cooling' not in context.user_data:
        context.user_data['service_cooling'] = 0
    
    return await create_service_from_data(update, context)


async def create_service_from_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать услугу из собранных данных"""
    query = update.callback_query if hasattr(update, 'callback_query') and update.callback_query else None
    
    # Получаем данные
    name = context.user_data.get('service_name')
    price = context.user_data.get('service_price')
    duration = context.user_data.get('service_duration')
    cooling = context.user_data.get('service_cooling', 0)
    category_id = context.user_data.get('service_category_id')
    description = context.user_data.get('service_description', '')
    
    if not name or not price or not duration:
        error_text = "❌ Ошибка: не все данные заполнены"
        if query:
            await query.message.edit_text(error_text)
        else:
            await update.message.reply_text(error_text)
        return ConversationHandler.END
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            error_text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return ConversationHandler.END
        
        # Создаем услугу
        service = create_service(
            session=session,
            master_id=master.id,
            title=name,
            price=price,
            duration=duration,
            cooling=cooling,
            category_id=category_id,
            description=description
        )
        
        # Очищаем данные
        service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
        for key in service_keys:
            del context.user_data[key]
        
        success_text = f"✅ Услуга <b>{name}</b> успешно добавлена!"
        keyboard = [
            [InlineKeyboardButton("💼 Мои услуги", callback_data="master_services")],
            [InlineKeyboardButton("➕ Добавить еще", callback_data="add_service")]
        ]
        
        if query:
            await query.message.edit_text(
                success_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                success_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    return ConversationHandler.END


async def receive_service_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить описание услуги"""
    description = update.message.text.strip()
    context.user_data['service_description'] = description
    return await create_service_from_data(update, context)


async def service_skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить описание"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['service_description'] = ''
    return await create_service_from_data(update, context)


# Функции навигации назад
async def service_back_to_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к вводу названия"""
    query = update.callback_query
    await query.answer()
    
    text = "💼 <b>Добавление услуги</b>\n\nВведите название услуги:"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="add_service")]]
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_NAME


async def service_back_to_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к вводу цены"""
    query = update.callback_query
    await query.answer()
    
    text = "💰 Введите цену услуги (в рублях, только число):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]]
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_PRICE


async def service_back_to_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к выбору шаблона"""
    query = update.callback_query
    await query.answer()
    
    # Перезапускаем выбор категории
    return await add_service_start(update, context)


async def service_back_to_advanced(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к расширенным настройкам"""
    return await service_advanced_settings(update, context)


# ===== Функции редактирования и удаления услуги =====
# Эти функции будут реализованы в следующем шаге
async def edit_service(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def delete_service_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def delete_service_execute(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def edit_service_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def receive_edit_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def edit_service_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def receive_edit_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def edit_service_duration_start(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def receive_edit_service_duration(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def edit_service_cooling_start(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def receive_edit_service_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_edit_day(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_edit_week(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_add_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_start_selected(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_start_received(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_end_selected(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_end_received(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_delete_period(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_delete_temp_period(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_save_changes(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_cancel_changes(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_save_week(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def schedule_cancel_week(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def master_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def portfolio_add(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def receive_portfolio_photo(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def portfolio_view(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def portfolio_next(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def portfolio_prev(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def portfolio_delete(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def portfolio_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def copy_link(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
