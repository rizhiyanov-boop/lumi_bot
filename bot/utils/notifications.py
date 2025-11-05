"""Система уведомлений для админов"""
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from typing import List

from bot.database.models import Booking, Admin


async def notify_admins_new_booking(bot: Bot, booking: Booking, admins: List[Admin], with_assign_button: bool = False):
    """
    Отправить уведомление админам о новом бронировании
    
    Args:
        bot: Telegram Bot instance
        booking: Объект бронирования
        admins: Список админов для уведомления
        with_assign_button: Добавить кнопку "Назначить инструктора" (для владельцев/старших инструкторов)
    """
    
    # Формируем сообщение
    location_name = booking.field.location.name
    field_name = booking.field.name
    date_str = booking.date.strftime("%d.%m.%Y")
    start_time = booking.start_time.strftime("%H:%M")
    
    username_str = f"@{booking.username}" if booking.username else "—"
    
    # Проверяем, назначен ли уже инструктор
    referee_status = ""
    if booking.referee_id:
        referee_status = "\n👨‍⚖️ <b>Судья:</b> Назначен ✅"
    else:
        referee_status = "\n⚠️ <b>Судья не назначен</b>"
    
    message = f"""
🎯 <b>Новое бронирование!</b>

📍 <b>Локация:</b> {location_name}
🎮 <b>Площадка:</b> {field_name}
📅 <b>Дата:</b> {date_str}
🕐 <b>Время:</b> {start_time}

👤 <b>Telegram:</b> {username_str}{referee_status}
"""
    
    if booking.notes:
        message += f"\n📝 <b>Контакты:</b>\n{booking.notes}"
    
    # Формируем клавиатуру с кнопкой назначения
    keyboard = None
    if with_assign_button and not booking.referee_id:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "👨‍⚖️ Назначить инструктора",
                callback_data=f"assign_referee_{booking.id}"
            )]
        ])
    
    # Отправляем уведомления всем админам с включенными уведомлениями
    for admin in admins:
        try:
            await bot.send_message(
                chat_id=admin.user_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"[WARNING] Не удалось отправить уведомление админу {admin.user_id}: {e}")


async def notify_admins_cancellation(bot: Bot, booking: Booking, admins: List[Admin], cancelled_by: str):
    """Отправить уведомление админам об отмене бронирования"""
    
    location_name = booking.field.location.name
    field_name = booking.field.name
    date_str = booking.date.strftime("%d.%m.%Y")
    start_time = booking.start_time.strftime("%H:%M")
    
    message = f"""
❌ <b>Бронирование отменено</b>

📍 <b>Локация:</b> {location_name}
🎮 <b>Площадка:</b> {field_name}
📅 <b>Дата:</b> {date_str}
🕐 <b>Время:</b> {start_time}

🗑 <b>Отменено:</b> {cancelled_by}
"""
    
    for admin in admins:
        try:
            await bot.send_message(
                chat_id=admin.user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"[WARNING] Не удалось отправить уведомление админу {admin.user_id}: {e}")

