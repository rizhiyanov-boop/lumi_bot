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
