"""
Утилиты для работы с бронированиями
"""
from datetime import date, time, timedelta
from typing import List
from bot.utils.validators import get_available_times
from bot.utils.sun_info import get_sun_info_kaluga


def check_fully_booked_dates(
    field_id: int,
    is_outdoor: bool,
    start_date: date,
    days_count: int,
    get_bookings_func
) -> List[date]:
    """
    Проверить какие дни полностью заняты
    
    Args:
        field_id: ID площадки
        is_outdoor: Открытая ли площадка
        start_date: Начальная дата проверки
        days_count: Количество дней для проверки
        get_bookings_func: Функция для получения бронирований (session, field_id, date)
        
    Returns:
        List[date]: Список полностью занятых дат
    """
    fully_booked = []
    
    for i in range(days_count):
        check_date = start_date + timedelta(days=i)
        
        # Получаем бронирования на эту дату
        bookings = get_bookings_func(field_id, check_date)
        booked_times = get_available_times(bookings, check_date)
        
        # Получаем информацию о закате для открытых площадок
        sunset_time = None
        if is_outdoor:
            sun_info = get_sun_info_kaluga(check_date)
            if sun_info:
                sunset_time = sun_info['sunset'].time()
        
        # Проверяем каждый час рабочего дня
        work_hours = list(range(9, 21))
        has_available_slot = False
        
        for hour in work_hours:
            start_time = time(hour, 0)
            end_hour = min(hour + 6, 23)
            end_time = time(end_hour, 0)
            
            # Для открытых площадок проверяем время заката
            if is_outdoor and sunset_time:
                if end_time > sunset_time:
                    continue
            
            # Проверяем занятость
            is_available = True
            for booked_start, booked_end in booked_times:
                if (start_time < booked_end and end_time > booked_start):
                    is_available = False
                    break
            
            if is_available:
                has_available_slot = True
                break
        
        if not has_available_slot:
            fully_booked.append(check_date)
    
    return fully_booked

