"""Валидаторы и вспомогательные функции"""
from datetime import time, date, datetime, timedelta
from typing import List, Tuple, Optional

from bot.database.models import Booking, Field
from bot.config import WORK_START, WORK_END


def parse_work_time(time_str: str) -> time:
    """Парсинг времени из строки"""
    hour, minute = map(int, time_str.split(':'))
    return time(hour, minute)


def get_work_hours() -> Tuple[time, time]:
    """Получить рабочие часы"""
    return parse_work_time(WORK_START), parse_work_time(WORK_END)


def is_time_slot_available(
    bookings: List[Booking],
    start_time: time,
    end_time: time
) -> bool:
    """Проверить, доступен ли временной слот"""
    for booking in bookings:
        # Проверяем пересечение временных интервалов
        if not (end_time <= booking.start_time or start_time >= booking.end_time):
            return False
    return True


def get_available_times(
    bookings: List[Booking],
    booking_date: date
) -> List[Tuple[time, time]]:
    """Получить список доступных временных слотов"""
    booked_slots = [(b.start_time, b.end_time) for b in bookings]
    return booked_slots


def calculate_max_duration(
    bookings: List[Booking],
    start_hour: int
) -> int:
    """Вычислить максимальную продолжительность от заданного времени"""
    start_time = time(start_hour, 0)
    work_start, work_end = get_work_hours()
    
    max_duration = work_end.hour - start_hour
    
    # Проверяем бронирования
    for booking in bookings:
        if booking.start_time > start_time:
            # Ближайшее бронирование после start_time
            hours_until_booking = booking.start_time.hour - start_hour
            max_duration = min(max_duration, hours_until_booking)
    
    return min(max_duration, 4)  # Максимум 4 часа


def calculate_price(
    field: Field,
    booking_date: date,
    start_hour: int,
    duration: int,
    players_count: int
) -> float:
    """Рассчитать стоимость бронирования"""
    from bot.config import (
        WEEKEND_MULTIPLIER,
        EVENING_MULTIPLIER,
        EVENING_START_HOUR,
        PLAYER_DISCOUNTS
    )
    
    base_price = field.price_per_hour * duration
    
    # Множитель для выходных (суббота=5, воскресенье=6)
    if booking_date.weekday() in [5, 6]:
        base_price *= WEEKEND_MULTIPLIER
    
    # Множитель для вечернего времени
    if start_hour >= EVENING_START_HOUR:
        base_price *= EVENING_MULTIPLIER
    
    # Скидка за количество игроков
    discount = 0
    for player_threshold, discount_percent in sorted(PLAYER_DISCOUNTS.items(), reverse=True):
        if players_count >= player_threshold:
            discount = discount_percent
            break
    
    if discount > 0:
        base_price *= (1 - discount / 100)
    
    return round(base_price, 2)


def format_booking_info(booking: Booking) -> str:
    """Форматировать информацию о бронировании"""
    location = booking.field.location
    field = booking.field
    
    date_str = booking.date.strftime("%d.%m.%Y")
    weekday = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][booking.date.weekday()]
    start_time = booking.start_time.strftime("%H:%M")
    
    status_text = {
        "pending": "⏳ Ожидает подтверждения",
        "confirmed": "✅ Подтверждено",
        "cancelled": "❌ Отменено"
    }
    
    info = f"""
📍 <b>Локация:</b> {location.name}
📌 <b>Адрес:</b> {location.address}

🎮 <b>Площадка:</b> {field.name}
📅 <b>Дата:</b> {date_str} ({weekday})
🕐 <b>Время:</b> {start_time}

📊 <b>Статус:</b> {status_text.get(booking.status.value, booking.status.value)}
"""
    
    if booking.notes:
        info += f"\n📝 <b>Контакты:</b>\n{booking.notes}"
    
    return info


def can_cancel_booking(booking: Booking) -> Tuple[bool, str]:
    """Проверить, можно ли отменить бронирование"""
    if booking.status.value == "cancelled":
        return False, "Бронирование уже отменено"
    
    # Проверяем, что до игры осталось более 24 часов
    booking_datetime = datetime.combine(booking.date, booking.start_time)
    time_until_booking = booking_datetime - datetime.now()
    
    if time_until_booking < timedelta(hours=24):
        return False, "Бронирование можно отменить не позднее чем за 24 часа до начала"
    
    return True, ""

