"""Записи мастера"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_master_by_telegram, get_bookings_for_master
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner

logger = logging.getLogger(__name__)


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

