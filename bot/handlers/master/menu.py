"""Главное меню и команды мастер-бота"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_master_by_telegram, create_master_account
from bot.utils.impersonation import get_impersonation_banner
from .common import get_onboarding_status

logger = logging.getLogger(__name__)


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

