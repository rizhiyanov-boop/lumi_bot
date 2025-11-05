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
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        work_periods = get_work_periods(session, master.id)
        
        # Группируем периоды по дням недели
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        periods_by_day = {i: [] for i in range(7)}
        
        for period in work_periods:
            periods_by_day[period.weekday].append(period)
        
        text = "📅 <b>Ваше расписание</b>\n\n"
        
        has_schedule = False
        for weekday in range(7):
            periods = sorted(periods_by_day[weekday], key=lambda p: p.start_time)
            if periods:
                has_schedule = True
                text += f"<b>{weekdays[weekday]}:</b>\n"
                for period in periods:
                    text += f"  {period.start_time} - {period.end_time}\n"
                text += "\n"
        
        if not has_schedule:
            text += "<i>Расписание не настроено. Добавьте рабочие периоды!</i>\n"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        # Кнопки для редактирования каждого дня
        for weekday in range(7):
            weekday_name = weekdays[weekday]
            periods_count = len(periods_by_day[weekday])
            if periods_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {weekday_name} ({periods_count})",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        f"➕ {weekday_name}",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("📅 Редактировать всю неделю", callback_data="edit_week")])
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
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        # Проверяем текущую подписку
        from datetime import datetime
        now = datetime.utcnow()
        is_premium = master.subscription_level == 'premium'
        is_expired = master.subscription_expires_at and master.subscription_expires_at < now
        
        text = "💎 <b>Премиум подписка</b>\n\n"
        
        if is_premium and not is_expired:
            expires_str = master.subscription_expires_at.strftime("%d.%m.%Y %H:%M") if master.subscription_expires_at else "Не указано"
            text += f"✅ У вас активна премиум подписка\n"
            text += f"📅 Истекает: {expires_str}\n\n"
            text += "<b>Преимущества премиум:</b>\n"
            text += "• До 50 фото в портфолио\n"
            text += "• Приоритетная поддержка\n"
            text += "• Расширенные возможности\n"
        elif is_premium and is_expired:
            text += "❌ Ваша премиум подписка истекла\n\n"
            text += f"<b>Премиум подписка на {PREMIUM_DURATION_DAYS} дней</b>\n"
            text += f"💰 Цена: {PREMIUM_PRICE}₽\n\n"
            text += "<b>Включает:</b>\n"
            text += "• До 50 фото в портфолио\n"
            text += "• Приоритетная поддержка\n"
            text += "• Расширенные возможности\n"
        else:
            text += f"<b>Премиум подписка на {PREMIUM_DURATION_DAYS} дней</b>\n"
            text += f"💰 Цена: {PREMIUM_PRICE}₽\n\n"
            text += "<b>Включает:</b>\n"
            text += "• До 50 фото в портфолио\n"
            text += "• Приоритетная поддержка\n"
            text += "• Расширенные возможности\n"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        if not is_premium or is_expired:
            keyboard.append([InlineKeyboardButton("💳 Оплатить премиум", callback_data="premium_pay")])
        
        # Проверяем наличие активных платежей
        from bot.database.models import Payment
        active_payments = session.query(Payment).filter_by(
            master_account_id=master.id,
            status='pending'
        ).all()
        
        if active_payments:
            keyboard.append([InlineKeyboardButton("🔄 Проверить статус оплаты", callback_data="premium_check_status")])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_settings")])
        
        if query:
            await query.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        elif update.message:
            await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def premium_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата премиума"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Проверяем, не активна ли уже подписка
        from datetime import datetime
        now = datetime.utcnow()
        if master.subscription_level == 'premium' and master.subscription_expires_at and master.subscription_expires_at > now:
            await query.message.edit_text(
                "✅ У вас уже активна премиум подписка!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        # Создаем платеж
        return_url = f"https://t.me/{CLIENT_BOT_USERNAME}"  # URL для возврата после оплаты
        payment_data = create_premium_payment(master.id, return_url)
        
        if not payment_data:
            await query.message.edit_text(
                "❌ Ошибка при создании платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        payment_id = payment_data.get('id')
        confirmation_url = payment_data.get('confirmation', {}).get('confirmation_url')
        
        if not confirmation_url:
            await query.message.edit_text(
                "❌ Ошибка получения ссылки на оплату. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        # Сохраняем платеж в базе
        payment_record = create_payment_record(
            session,
            master.id,
            payment_id,
            PREMIUM_PRICE,
            'premium'
        )
        
        if payment_record:
            text = f"💳 <b>Оплата премиум подписки</b>\n\n"
            text += f"💰 Сумма: {PREMIUM_PRICE}₽\n"
            text += f"📅 Срок: {PREMIUM_DURATION_DAYS} дней\n\n"
            text += "Нажмите на кнопку ниже, чтобы перейти к оплате:\n\n"
            text += "После оплаты вернитесь и нажмите «Проверить статус оплаты»"
            
            keyboard = [
                [InlineKeyboardButton("💳 Оплатить", url=confirmation_url)],
                [InlineKeyboardButton("🔄 Проверить статус оплаты", callback_data="premium_check_status")],
                [InlineKeyboardButton("« Назад", callback_data="master_premium")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.message.edit_text(
                "❌ Ошибка при сохранении платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )


async def premium_check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса оплаты"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем последний платеж
        from bot.database.models import Payment
        payment = session.query(Payment).filter_by(
            master_account_id=master.id,
            status='pending'
        ).order_by(Payment.created_at.desc()).first()
        
        if not payment:
            await query.message.edit_text(
                "❌ Активных платежей не найдено",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        # Проверяем статус платежа в ЮKassa
        payment_status = get_payment_status(payment.payment_id)
        
        if not payment_status:
            await query.message.edit_text(
                "❌ Ошибка при проверке статуса платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="premium_check_status"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        status = payment_status.get('status', 'unknown')
        
        if status == 'succeeded':
            # Платеж успешен - активируем подписку
            from datetime import datetime, timedelta
            expires_at = datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)
            
            # Обновляем статус платежа
            update_payment_status(session, payment.id, 'completed')
            
            # Обновляем подписку мастера
            update_master_subscription(
                session,
                master.id,
                'premium',
                expires_at
            )
            
            await query.message.edit_text(
                f"✅ <b>Платеж успешно обработан!</b>\n\n"
                f"💎 Премиум подписка активирована на {PREMIUM_DURATION_DAYS} дней.\n"
                f"📅 Истекает: {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Теперь вам доступны все премиум возможности!",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
        elif status == 'pending':
            await query.message.edit_text(
                "⏳ <b>Оплата в обработке</b>\n\n"
                "Платеж еще не обработан. Подождите несколько минут и проверьте снова.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="premium_check_status"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
        elif status == 'canceled':
            update_payment_status(session, payment.id, 'cancelled')
            await query.message.edit_text(
                "❌ <b>Платеж отменен</b>\n\n"
                "Платеж был отменен. Вы можете создать новый платеж.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Оплатить премиум", callback_data="premium_pay"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
        else:
            await query.message.edit_text(
                f"❌ <b>Неизвестный статус платежа</b>\n\n"
                f"Статус: {status}\n\n"
                f"Попробуйте проверить снова позже.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="premium_check_status"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )


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

async def edit_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню редактирования услуги"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: edit_service_123
    service_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        # Формируем информацию об услуге
        category_name = service.category.title if service.category else "Без категории"
        status_icon = "✅" if service.active else "❌"
        
        text = f"✏️ <b>Редактирование услуги</b>\n\n"
        text += f"{status_icon} <b>{service.title}</b>\n"
        text += f"📁 Категория: {category_name}\n"
        text += f"💰 Цена: {service.price}₽\n"
        text += f"⏱ Длительность: {service.duration_mins} мин\n"
        text += f"🔄 Время охлаждения: {service.cooling_period_mins} мин\n"
        if service.description:
            text += f"📝 Описание: {service.description}\n"
        text += f"\n{get_impersonation_banner(context)}"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить название", callback_data=f"edit_service_name_{service_id}")],
            [InlineKeyboardButton("💰 Изменить цену", callback_data=f"edit_service_price_{service_id}")],
            [InlineKeyboardButton("⏱ Изменить длительность", callback_data=f"edit_service_duration_{service_id}")],
            [InlineKeyboardButton("🔄 Изменить время охлаждения", callback_data=f"edit_service_cooling_{service_id}")],
            [InlineKeyboardButton("🗑 Удалить услугу", callback_data=f"delete_service_confirm_{service_id}")],
            [InlineKeyboardButton("« Назад", callback_data="master_services")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def edit_service_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование названия услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'name'
        
        text = f"✏️ <b>Изменение названия услуги</b>\n\n"
        text += f"Текущее название: <b>{service.title}</b>\n\n"
        text += "Введите новое название:"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_NAME


async def receive_edit_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое название услуги"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Минимум 2 символа.")
        return WAITING_EDIT_SERVICE_NAME
    
    if len(text) > 100:
        await update.message.reply_text("❌ Название слишком длинное. Максимум 100 символов.")
        return WAITING_EDIT_SERVICE_NAME
    
    service_id = context.user_data.get('edit_service_id')
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await update.message.reply_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Обновляем название
        update_service(session, service_id, title=text)
        
        await update.message.reply_text(f"✅ Название изменено на: <b>{text}</b>", parse_mode='HTML')
        
        # Очищаем контекст
        context.user_data.pop('edit_service_id', None)
        context.user_data.pop('edit_service_field', None)
        
        # Возвращаемся к меню редактирования
        query = update.callback_query
        if not query:
            # Создаем фиктивный callback_query
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
        
        await edit_service(update, context)
    
    return ConversationHandler.END


async def edit_service_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование цены услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'price'
        
        text = f"💰 <b>Изменение цены услуги</b>\n\n"
        text += f"Текущая цена: <b>{service.price}₽</b>\n\n"
        text += "Введите новую цену (в рублях, только число):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_PRICE


async def receive_edit_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новую цену услуги"""
    try:
        price = float(update.message.text.strip().replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text("❌ Цена должна быть больше 0. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_PRICE
        
        if price > 1000000:
            await update.message.reply_text("❌ Цена слишком большая. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_PRICE
        
        service_id = context.user_data.get('edit_service_id')
        
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            service = get_service_by_id(session, service_id)
            
            if not service or service.master_account_id != master.id:
                await update.message.reply_text("❌ Услуга не найдена")
                return ConversationHandler.END
            
            # Обновляем цену
            update_service(session, service_id, price=price)
            
            await update.message.reply_text(f"✅ Цена изменена на: <b>{price}₽</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
            await edit_service(update, context)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_PRICE


async def edit_service_duration_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование длительности услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'duration'
        
        text = f"⏱ <b>Изменение длительности услуги</b>\n\n"
        text += f"Текущая длительность: <b>{service.duration_mins} мин</b>\n\n"
        text += "Введите новую длительность (в минутах, только число):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_DURATION


async def receive_edit_service_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новую длительность услуги"""
    try:
        duration = int(update.message.text.strip())
        
        if duration <= 0:
            await update.message.reply_text("❌ Длительность должна быть больше 0. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_DURATION
        
        if duration > 1440:
            await update.message.reply_text("❌ Длительность слишком большая (максимум 1440 минут). Попробуйте снова:")
            return WAITING_EDIT_SERVICE_DURATION
        
        service_id = context.user_data.get('edit_service_id')
        
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            service = get_service_by_id(session, service_id)
            
            if not service or service.master_account_id != master.id:
                await update.message.reply_text("❌ Услуга не найдена")
                return ConversationHandler.END
            
            # Обновляем длительность
            update_service(session, service_id, duration_mins=duration)
            
            await update.message.reply_text(f"✅ Длительность изменена на: <b>{duration} мин</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
            await edit_service(update, context)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_DURATION


async def edit_service_cooling_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование времени охлаждения услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'cooling'
        
        text = f"🔄 <b>Изменение времени охлаждения</b>\n\n"
        text += f"Текущее время охлаждения: <b>{service.cooling_period_mins} мин</b>\n\n"
        text += "Введите новое время охлаждения (в минутах, только число, по умолчанию 0):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_COOLING


async def receive_edit_service_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое время охлаждения услуги"""
    try:
        cooling = int(update.message.text.strip())
        
        if cooling < 0:
            await update.message.reply_text("❌ Время охлаждения не может быть отрицательным. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_COOLING
        
        if cooling > 1440:
            await update.message.reply_text("❌ Время охлаждения слишком большое. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_COOLING
        
        service_id = context.user_data.get('edit_service_id')
        
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            service = get_service_by_id(session, service_id)
            
            if not service or service.master_account_id != master.id:
                await update.message.reply_text("❌ Услуга не найдена")
                return ConversationHandler.END
            
            # Обновляем время охлаждения
            update_service(session, service_id, cooling_period_mins=cooling)
            
            await update.message.reply_text(f"✅ Время охлаждения изменено на: <b>{cooling} мин</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
            await edit_service(update, context)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_COOLING


async def delete_service_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        text = f"🗑 <b>Удаление услуги</b>\n\n"
        text += f"Вы уверены, что хотите удалить услугу <b>{service.title}</b>?\n\n"
        text += "⚠️ Это действие нельзя отменить!"
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_service_execute_{service_id}")],
            [InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def delete_service_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить удаление услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        service_title = service.title
        
        # Удаляем услугу
        if delete_service(session, service_id):
            text = f"✅ Услуга <b>{service_title}</b> успешно удалена!"
            keyboard = [[InlineKeyboardButton("💼 Мои услуги", callback_data="master_services")]]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.message.edit_text("❌ Ошибка при удалении услуги")


# ===== Функции расписания =====

async def schedule_edit_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование расписания для конкретного дня недели"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[2])
    
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    weekday_name = weekdays[weekday]
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем существующие периоды для этого дня
        existing_periods = get_work_periods_by_weekday(session, master.id, weekday)
        existing_periods = sorted(existing_periods, key=lambda p: p.start_time)
        
        # Получаем временные периоды из контекста (если редактируем)
        temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
        
        text = f"📅 <b>Редактирование расписания</b>\n\n"
        text += f"День: <b>{weekday_name}</b>\n\n"
        
        if existing_periods or temp_periods:
            text += "<b>Текущие периоды:</b>\n"
            for i, period in enumerate(existing_periods):
                text += f"  {i+1}. {period.start_time} - {period.end_time}\n"
            for i, period in enumerate(temp_periods):
                text += f"  {len(existing_periods)+i+1}. {period['start']} - {period['end']} (новый)\n"
        else:
            text += "<i>Нет рабочих периодов для этого дня</i>\n"
        
        text += f"\n{get_impersonation_banner(context)}"
        
        keyboard = []
        
        # Кнопки для существующих периодов
        for period in existing_periods:
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {period.start_time}-{period.end_time}",
                    callback_data=f"schedule_delete_period_{period.id}"
                )
            ])
        
        # Кнопки для временных периодов
        for i, period in enumerate(temp_periods):
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {period['start']}-{period['end']} (удалить новый)",
                    callback_data=f"schedule_delete_temp_{weekday}_{i}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить период", callback_data=f"schedule_add_period_{weekday}")])
        keyboard.append([InlineKeyboardButton("💾 Сохранить изменения", callback_data=f"schedule_save_{weekday}")])
        keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data=f"schedule_cancel_{weekday}")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_schedule")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def schedule_add_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление рабочего периода"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[3])
    context.user_data['schedule_weekday'] = weekday
    
    # Генерируем кнопки для выбора времени начала
    text = "🕐 Выберите время начала работы:"
    
    keyboard = []
    # Часы с интервалом в 1 час
    for hour in range(8, 22):
        time_str = f"{hour:02d}:00"
        keyboard.append([
            InlineKeyboardButton(
                time_str,
                callback_data=f"schedule_start_{hour:02d}00"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("✏️ Ввести вручную", callback_data="schedule_start_manual")])
    keyboard.append([InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{weekday}")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SCHEDULE_START


async def schedule_start_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени начала"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "schedule_start_manual":
        text = "🕐 Введите время начала работы (формат ЧЧ:ММ, например 09:00):"
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{context.user_data.get('schedule_weekday', 0)}")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SCHEDULE_START_MANUAL
    else:
        # Извлекаем время из callback_data: schedule_start_0900
        time_str = data.replace('schedule_start_', '')
        if len(time_str) == 4:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            start_time = f"{hour:02d}:{minute:02d}"
            context.user_data['schedule_start'] = start_time
            return await _show_end_time_selection(query, context)


async def schedule_start_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время начала вручную"""
    time_str = update.message.text.strip()
    
    # Проверяем формат
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
        
        start_time = f"{hour:02d}:{minute:02d}"
        context.user_data['schedule_start'] = start_time
        
        # Показываем выбор времени окончания
        query = update.callback_query
        if not query:
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = "schedule_start_received"
                async def answer(self):
                    pass
            update.callback_query = FakeCallbackQuery(update.message)
        
        return await _show_end_time_selection(update.callback_query, context)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 09:00). Попробуйте снова:")
        return WAITING_SCHEDULE_START_MANUAL


async def _show_end_time_selection(query, context):
    """Показать выбор времени окончания"""
    start_time = context.user_data.get('schedule_start')
    
    text = f"🕐 Выберите время окончания работы:\n\nНачало: <b>{start_time}</b>"
    
    keyboard = []
    
    # Парсим время начала
    start_hour, start_minute = map(int, start_time.split(':'))
    start_total_minutes = start_hour * 60 + start_minute
    
    # Генерируем варианты времени окончания (минимум через 1 час от начала)
    for hour in range(8, 23):
        end_total_minutes = hour * 60
        if end_total_minutes > start_total_minutes:
            time_str = f"{hour:02d}:00"
            keyboard.append([
                InlineKeyboardButton(
                    time_str,
                    callback_data=f"schedule_end_{hour:02d}00"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("✏️ Ввести вручную", callback_data="schedule_end_manual")])
    keyboard.append([InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{context.user_data.get('schedule_weekday', 0)}")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SCHEDULE_END


async def schedule_end_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени окончания"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "schedule_end_manual":
        text = "🕐 Введите время окончания работы (формат ЧЧ:ММ, например 18:00):"
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{context.user_data.get('schedule_weekday', 0)}")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SCHEDULE_END_MANUAL
    else:
        # Извлекаем время из callback_data: schedule_end_1800
        time_str = data.replace('schedule_end_', '')
        if len(time_str) == 4:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            end_time = f"{hour:02d}:{minute:02d}"
            context.user_data['schedule_end'] = end_time
            return await _save_period_to_context(query, context)


async def schedule_end_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время окончания вручную"""
    time_str = update.message.text.strip()
    
    # Проверяем формат
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
        
        end_time = f"{hour:02d}:{minute:02d}"
        
        # Проверяем что окончание после начала
        start_time = context.user_data.get('schedule_start')
        start_hour, start_minute = map(int, start_time.split(':'))
        end_hour, end_minute = map(int, end_time.split(':'))
        
        if end_hour * 60 + end_minute <= start_hour * 60 + start_minute:
            await update.message.reply_text("❌ Время окончания должно быть позже времени начала. Попробуйте снова:")
            return WAITING_SCHEDULE_END_MANUAL
        
        context.user_data['schedule_end'] = end_time
        
        # Сохраняем период
        query = update.callback_query
        if not query:
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = "schedule_end_received"
                async def answer(self):
                    pass
            update.callback_query = FakeCallbackQuery(update.message)
        
        return await _save_period_to_context(update.callback_query, context)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 18:00). Попробуйте снова:")
        return WAITING_SCHEDULE_END_MANUAL


async def _save_period_to_context(query, context):
    """Сохранить период в контекст (временный период)"""
    weekday = context.user_data.get('schedule_weekday')
    start_time = context.user_data.get('schedule_start')
    end_time = context.user_data.get('schedule_end')
    
    if not weekday or not start_time or not end_time:
        await query.message.edit_text("❌ Ошибка: не все данные заполнены")
        return ConversationHandler.END
    
    # Валидация периода
    with get_session() as session:
        # Создаем фиктивный update для получения telegram_id
        class FakeUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.callback_query = query
        fake_update = FakeUpdate(query)
        master = get_master_by_telegram(session, get_master_telegram_id(fake_update, context))
        if master:
            existing_periods = get_work_periods_by_weekday(session, master.id, weekday)
            is_valid, error_msg = validate_schedule_period(existing_periods, start_time, end_time)
            
            if not is_valid:
                await query.message.edit_text(
                    error_msg + "\n\nПопробуйте снова:",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{weekday}")
                    ]])
                )
                return ConversationHandler.END
    
    # Сохраняем временный период
    if f'schedule_temp_periods_{weekday}' not in context.user_data:
        context.user_data[f'schedule_temp_periods_{weekday}'] = []
    
    context.user_data[f'schedule_temp_periods_{weekday}'].append({
        'start': start_time,
        'end': end_time
    })
    
    # Очищаем временные данные
    context.user_data.pop('schedule_start', None)
    context.user_data.pop('schedule_end', None)
    
    # Возвращаемся к редактированию дня
    await schedule_edit_day(query, context)
    
    return ConversationHandler.END


async def schedule_delete_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить существующий период расписания"""
    query = update.callback_query
    await query.answer()
    
    period_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем период для определения weekday
        from bot.database.models import WorkPeriod
        period = session.query(WorkPeriod).filter_by(id=period_id).first()
        
        if not period or period.master_account_id != master.id:
            await query.message.edit_text("❌ Период не найден")
            return
        
        weekday = period.weekday
        
        # Удаляем период
        if delete_work_period(session, period_id):
            await query.message.edit_text("✅ Период удален")
            # Обновляем отображение дня
            query.data = f"edit_day_{weekday}"
            await schedule_edit_day(update, context)
        else:
            await query.message.edit_text("❌ Ошибка при удалении периода")


async def schedule_delete_temp_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить временный период (еще не сохраненный)"""
    query = update.callback_query
    await query.answer()
    
    # Формат: schedule_delete_temp_{weekday}_{index}
    parts = query.data.split('_')
    weekday = int(parts[3])
    index = int(parts[4])
    
    temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
    if 0 <= index < len(temp_periods):
        temp_periods.pop(index)
        context.user_data[f'schedule_temp_periods_{weekday}'] = temp_periods
    
    await schedule_edit_day(update, context)


async def schedule_save_changes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить изменения расписания для дня"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем временные периоды
        temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
        
        # Сохраняем каждый временный период
        for period in temp_periods:
            set_work_period(
                session,
                master.id,
                weekday,
                period['start'],
                period['end']
            )
        
        # Очищаем временные данные
        context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
        
        await query.message.edit_text(f"✅ Расписание для {['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'][weekday]} сохранено!")
        
        # Возвращаемся к расписанию
        query.data = "master_schedule"
        await master_schedule(update, context)


async def schedule_cancel_changes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить изменения расписания для дня"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[2])
    
    # Очищаем временные данные
    context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
    context.user_data.pop('schedule_weekday', None)
    context.user_data.pop('schedule_start', None)
    context.user_data.pop('schedule_end', None)
    
    await query.message.edit_text("❌ Изменения отменены")
    
    # Возвращаемся к расписанию
    query.data = "master_schedule"
    await master_schedule(update, context)


async def schedule_edit_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование расписания на всю неделю"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        work_periods = get_work_periods(session, master.id)
        
        # Группируем периоды по дням недели
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        periods_by_day = {i: [] for i in range(7)}
        
        for period in work_periods:
            periods_by_day[period.weekday].append(period)
        
        text = "📅 <b>Редактирование расписания на неделю</b>\n\n"
        text += "Выберите день для редактирования:\n\n"
        
        # Показываем краткую информацию о каждом дне
        for weekday in range(7):
            periods = sorted(periods_by_day[weekday], key=lambda p: p.start_time)
            periods_count = len(periods)
            
            if periods_count > 0:
                periods_text = ", ".join([f"{p.start_time}-{p.end_time}" for p in periods[:2]])
                if periods_count > 2:
                    periods_text += f" (+{periods_count - 2})"
                text += f"{weekdays[weekday]}: {periods_text}\n"
            else:
                text += f"{weekdays[weekday]}: <i>нет периодов</i>\n"
        
        text += f"\n{get_impersonation_banner(context)}"
        
        keyboard = []
        
        # Кнопки для редактирования каждого дня
        for weekday in range(7):
            weekday_name = weekdays[weekday]
            periods_count = len(periods_by_day[weekday])
            if periods_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {weekday_name} ({periods_count})",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        f"➕ {weekday_name}",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("💾 Сохранить все изменения", callback_data="schedule_save_week")])
        keyboard.append([InlineKeyboardButton("❌ Отменить все", callback_data="schedule_cancel_week")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_schedule")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def schedule_save_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить изменения расписания на всю неделю"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Сохраняем временные периоды для всех дней недели
        saved_count = 0
        for weekday in range(7):
            temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
            
            # Сохраняем каждый временный период
            for period in temp_periods:
                set_work_period(
                    session,
                    master.id,
                    weekday,
                    period['start'],
                    period['end']
                )
                saved_count += 1
            
            # Очищаем временные данные для этого дня
            context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
        
        # Очищаем общие временные данные
        context.user_data.pop('schedule_weekday', None)
        context.user_data.pop('schedule_start', None)
        context.user_data.pop('schedule_end', None)
        
        if saved_count > 0:
            await query.message.edit_text(f"✅ Расписание сохранено! Добавлено {saved_count} период(ов).")
        else:
            await query.message.edit_text("✅ Расписание сохранено!")
        
        # Возвращаемся к расписанию
        query.data = "master_schedule"
        await master_schedule(update, context)


async def schedule_cancel_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить изменения расписания на всю неделю"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем временные данные для всех дней недели
    for weekday in range(7):
        context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
    
    # Очищаем общие временные данные
    context.user_data.pop('schedule_weekday', None)
    context.user_data.pop('schedule_start', None)
    context.user_data.pop('schedule_end', None)
    
    await query.message.edit_text("❌ Все изменения отменены")
    
    # Возвращаемся к расписанию
    query.data = "master_schedule"
    await master_schedule(update, context)


# ===== Функции портфолио и фото =====

async def upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать загрузку фото профиля"""
    query = update.callback_query
    await query.answer()
    
    text = "🖼 <b>Загрузка фото профиля</b>\n\nОтправьте фото, которое будет отображаться в вашем профиле."
    text += get_impersonation_banner(context)
    
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_profile")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['uploading_photo_type'] = 'avatar'


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения фото (для профиля или портфолио)"""
    photo_type = context.user_data.get('uploading_photo_type')
    
    if not photo_type:
        return
    
    # Получаем самое большое фото
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await update.message.reply_text("❌ Аккаунт не найден")
            return
        
        if photo_type == 'avatar':
            # Сохраняем фото профиля
            from bot.database.models import MasterAccount
            master = session.query(MasterAccount).filter_by(id=master.id).first()
            master.avatar_url = file_id
            session.commit()
            
            await update.message.reply_text("✅ Фото профиля успешно загружено!")
            
            # Возвращаемся к профилю
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = "master_profile"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message)
            await master_profile(update, context)
            
        elif photo_type == 'portfolio':
            # Добавляем фото в портфолио
            current_count, max_photos = get_portfolio_limit(session, master.id)
            
            if current_count >= max_photos:
                await update.message.reply_text(
                    f"❌ Достигнут лимит портфолио ({max_photos} фото).\n\n"
                    f"Текущий тариф: {master.subscription_level}\n"
                    f"Для увеличения лимита перейдите на более высокий тариф."
                )
                context.user_data.pop('uploading_photo_type', None)
                return
            
            # Получаем подпись к фото (если есть текст в сообщении)
            caption = update.message.caption if update.message.caption else None
            
            portfolio_photo = add_portfolio_photo(session, master.id, file_id, caption)
            
            if portfolio_photo:
                await update.message.reply_text(
                    f"✅ Фото добавлено в портфолио!\n\n"
                    f"Фото в портфолио: {current_count + 1}/{max_photos}"
                )
                
                # Возвращаемся к портфолио
                class FakeCallbackQuery:
                    def __init__(self, message):
                        self.message = message
                        self.data = "master_portfolio"
                    async def answer(self):
                        pass
                
                update.callback_query = FakeCallbackQuery(update.message)
                await master_portfolio(update, context)
            else:
                await update.message.reply_text("❌ Ошибка при добавлении фото в портфолио")
        
        context.user_data.pop('uploading_photo_type', None)


async def master_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать портфолио мастера"""
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
        
        portfolio_photos = get_portfolio_photos(session, master.id)
        current_count, max_photos = get_portfolio_limit(session, master.id)
        
        text = f"📸 <b>Мое портфолио</b>\n\n"
        text += f"Фото: {current_count}/{max_photos}\n\n"
        
        if portfolio_photos:
            text += f"У вас <b>{len(portfolio_photos)}</b> фото в портфолио.\n\n"
            text += "Выберите действие:"
        else:
            text += "<i>Портфолио пусто. Добавьте свои работы!</i>"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        if portfolio_photos:
            keyboard.append([InlineKeyboardButton("👁 Просмотреть портфолио", callback_data="portfolio_view")])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить фото", callback_data="portfolio_add")])
        
        if portfolio_photos:
            keyboard.append([InlineKeyboardButton("🗑 Удалить фото", callback_data="portfolio_delete")])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_profile")])
        
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


async def portfolio_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление фото в портфолио"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        current_count, max_photos = get_portfolio_limit(session, master.id)
        
        if current_count >= max_photos:
            await query.message.edit_text(
                f"❌ Достигнут лимит портфолио ({max_photos} фото).\n\n"
                f"Текущий тариф: {master.subscription_level}\n"
                f"Для увеличения лимита перейдите на более высокий тариф.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_portfolio")
                ]])
            )
            return
        
        text = f"📸 <b>Добавление фото в портфолио</b>\n\n"
        text += f"Отправьте фото для добавления в портфолио.\n\n"
        text += f"Фото в портфолио: {current_count}/{max_photos}\n"
        text += f"Вы можете добавить еще {max_photos - current_count} фото."
        text += get_impersonation_banner(context)
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_portfolio")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['uploading_photo_type'] = 'portfolio'


async def receive_portfolio_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить фото для портфолио (альтернативное название для receive_photo)"""
    return await receive_photo(update, context)


async def portfolio_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр портфолио с навигацией"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        portfolio_photos = get_portfolio_photos(session, master.id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                "📸 <b>Портфолио пусто</b>\n\nДобавьте фото в портфолио!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_portfolio")
                ]])
            )
            return
        
        # Сохраняем данные для навигации
        context.user_data['portfolio_index'] = 0
        context.user_data['portfolio_photos'] = [p.id for p in portfolio_photos]
        
        # Отправляем первое фото
        first_photo = portfolio_photos[0]
        caption = f"📸 <b>Мое портфолио</b>\n\n(1/{len(portfolio_photos)})"
        if first_photo.caption:
            caption += f"\n\n{first_photo.caption}"
        
        keyboard = []
        if len(portfolio_photos) > 1:
            keyboard.append([
                InlineKeyboardButton("▶️ Следующее", callback_data="portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"portfolio_delete_confirm_{first_photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="master_portfolio")
        ])
        
        await query.message.delete()
        await query.message.chat.send_photo(
            photo=first_photo.file_id,
            caption=caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Следующее фото в портфолио"""
    query = update.callback_query
    await query.answer()
    
    photo_ids = context.user_data.get('portfolio_photos', [])
    
    if not photo_ids:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('portfolio_index', 0)
    current_index = (current_index + 1) % len(photo_ids)
    context.user_data['portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Мое портфолио</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data="portfolio_prev"),
                InlineKeyboardButton("▶️ Следующее", callback_data="portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"portfolio_delete_confirm_{photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="master_portfolio")
        ])
        
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предыдущее фото в портфолио"""
    query = update.callback_query
    await query.answer()
    
    photo_ids = context.user_data.get('portfolio_photos', [])
    
    if not photo_ids:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('portfolio_index', 0)
    current_index = (current_index - 1) % len(photo_ids)
    context.user_data['portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Мое портфолио</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data="portfolio_prev"),
                InlineKeyboardButton("▶️ Следующее", callback_data="portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"portfolio_delete_confirm_{photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="master_portfolio")
        ])
        
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать удаление фото из портфолио (показать список)"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        portfolio_photos = get_portfolio_photos(session, master.id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                "📸 <b>Портфолио пусто</b>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_portfolio")
                ]])
            )
            return
        
        text = "🗑 <b>Удаление фото</b>\n\nВыберите фото для удаления:"
        
        keyboard = []
        for i, photo in enumerate(portfolio_photos):
            caption_text = photo.caption[:30] + "..." if photo.caption and len(photo.caption) > 30 else (photo.caption or f"Фото {i+1}")
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {caption_text}",
                    callback_data=f"portfolio_delete_confirm_{photo.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_portfolio")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления фото из портфолио"""
    query = update.callback_query
    await query.answer()
    
    photo_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_id, master_account_id=master.id).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        # Удаляем фото
        if delete_portfolio_photo(session, photo_id):
            await query.message.edit_text("✅ Фото удалено из портфолио")
            
            # Возвращаемся к портфолио
            query.data = "master_portfolio"
            await master_portfolio(update, context)
        else:
            await query.message.edit_text("❌ Ошибка при удалении фото")


async def copy_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Копировать ссылку для приглашения клиентов"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Генерируем deep link
        deep_link = f"https://t.me/{CLIENT_BOT_USERNAME}?start=m_{master.telegram_id}"
        
        text = f"🔗 <b>Ваша ссылка для приглашения</b>\n\n"
        text += f"Отправьте эту ссылку клиентам, чтобы они могли записаться к вам:\n\n"
        text += f"<code>{deep_link}</code>"
        text += get_impersonation_banner(context)
        
        keyboard = [
            [InlineKeyboardButton("📋 QR-код", callback_data="master_qr")],
            [InlineKeyboardButton("« Назад", callback_data="master_menu")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
