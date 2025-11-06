"""Главное меню и команды мастер-бота"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_master_by_telegram, create_master_account
from bot.utils.impersonation import get_impersonation_banner
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
            master = create_master_account(session, user.id, name)
            logger.info(f"Created new master account: {master.id}")
        
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

