"""QR код и приглашение клиентов"""
import logging
import qrcode
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_master_by_telegram
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from bot.config import CLIENT_BOT_USERNAME

logger = logging.getLogger(__name__)


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

