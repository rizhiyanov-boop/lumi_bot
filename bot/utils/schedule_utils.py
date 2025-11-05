"""Утилиты для работы с расписанием и доступными слотами"""
from datetime import datetime, time, timedelta, date
from typing import List, Tuple, Optional
from bot.database.models import WorkPeriod, Booking, Service
from bot.database.db import get_work_periods, get_bookings_for_master_in_range


def parse_time(time_str: str) -> Optional[time]:
    """Парсинг времени из строки формата HH:MM"""
    try:
        parts = time_str.split(':')
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
        return None
    except (ValueError, IndexError):
        return None


def format_time(t: time) -> str:
    """Форматирование времени в строку HH:MM"""
    return f"{t.hour:02d}:{t.minute:02d}"


def check_time_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """Проверка пересечения двух временных интервалов"""
    t1_start = parse_time(start1)
    t1_end = parse_time(end1)
    t2_start = parse_time(start2)
    t2_end = parse_time(end2)
    
    if not all([t1_start, t1_end, t2_start, t2_end]):
        return False
    
    # Пересечение: начало первого < конца второго И конец первого > начала второго
    return t1_start < t2_end and t1_end > t2_start


def validate_schedule_period(periods: List[WorkPeriod], new_start: str, new_end: str, exclude_id: Optional[int] = None) -> Tuple[bool, str]:
    """Валидация нового периода расписания"""
    # Проверка формата времени
    start_time = parse_time(new_start)
    end_time = parse_time(new_end)
    
    if not start_time or not end_time:
        return False, "❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 09:00)"
    
    # Проверка что начало < конца
    if start_time >= end_time:
        return False, "❌ Время начала должно быть раньше времени окончания"
    
    # Проверка на пересечения с существующими периодами
    for period in periods:
        if exclude_id and period.id == exclude_id:
            continue
        
        if check_time_overlap(new_start, new_end, period.start_time, period.end_time):
            return False, f"❌ Пересечение с существующим периодом: {period.start_time}-{period.end_time}"
    
    return True, "OK"


def get_available_time_slots(
    session,
    master_id: int,
    target_date: date,
    service_duration_mins: int,
    service_cooling_mins: int = 0,
    min_time_from_now: int = 60  # Минимум через сколько минут можно записаться (по умолчанию 1 час)
) -> List[Tuple[time, time]]:
    """Получить доступные временные слоты на конкретную дату"""
    from bot.database.db import get_work_periods
    
    # Определяем день недели (0=понедельник, 6=воскресенье)
    weekday = target_date.weekday()
    
    # Получаем рабочие периоды на этот день недели
    all_periods = get_work_periods(session, master_id)
    work_periods = [p for p in all_periods if p.weekday == weekday]
    
    if not work_periods:
        return []  # Выходной день
    
    # Получаем все бронирования на эту дату
    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)
    bookings = get_bookings_for_master_in_range(session, master_id, start_dt, end_dt)
    
    # Генерируем доступные слоты
    available_slots = []
    now = datetime.now()
    min_start_time = now + timedelta(minutes=min_time_from_now)
    
    # Для каждого рабочего периода
    for period in work_periods:
        period_start = parse_time(period.start_time)
        period_end = parse_time(period.end_time)
        
        if not period_start or not period_end:
            continue
        
        # Начало с шагом 30 минут
        current_time = period_start
        
        while current_time < period_end:
            # Вычисляем время окончания услуги
            slot_start_dt = datetime.combine(target_date, current_time)
            slot_end_dt = slot_start_dt + timedelta(minutes=service_duration_mins)
            slot_end_time = slot_end_dt.time()
            
            # Проверяем что слот помещается в рабочий период
            if slot_end_time > period_end:
                break
            
            # Проверяем что слот не в прошлом
            if slot_start_dt < min_start_time:
                # Пропускаем, но продолжаем
                current_time = add_minutes_to_time(current_time, 30)
                continue
            
            # Проверяем пересечение с существующими бронированиями
            is_available = True
            for booking in bookings:
                booking_start = booking.start_dt.time()
                booking_end = booking.end_dt.time()
                
                # Получаем cooling_period_mins из услуги существующего бронирования
                booking_cooling = booking.service.cooling_period_mins or 0
                
                # Проверяем пересечение (с учетом cooling period существующего бронирования)
                # Если существующее бронирование имеет cooling period, учитываем его
                booking_start_with_cooling = subtract_minutes_from_time(booking_start, booking_cooling)
                booking_end_with_cooling = add_minutes_to_time(booking_end, booking_cooling)
                
                # Также учитываем cooling period новой услуги при проверке конфликта
                # Новое бронирование не должно начинаться слишком близко к существующему
                slot_start_with_cooling = subtract_minutes_from_time(slot_start_dt.time(), service_cooling_mins)
                slot_end_with_cooling = add_minutes_to_time(slot_end_time, service_cooling_mins)
                
                # Проверяем пересечение интервалов с учетом cooling periods обеих услуг
                if check_time_overlap(
                    format_time(slot_start_with_cooling),
                    format_time(slot_end_with_cooling),
                    format_time(booking_start_with_cooling),
                    format_time(booking_end_with_cooling)
                ):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append((current_time, slot_end_time))
            
            # Переходим к следующему слоту (шаг 30 минут + учитываем cooling period)
            step_minutes = max(30, service_cooling_mins)
            current_time = add_minutes_to_time(current_time, step_minutes)
    
    return available_slots


def add_minutes_to_time(t: time, minutes: int) -> time:
    """Добавить минуты к времени"""
    dt = datetime.combine(date.today(), t) + timedelta(minutes=minutes)
    return dt.time()


def subtract_minutes_from_time(t: time, minutes: int) -> time:
    """Вычесть минуты из времени"""
    dt = datetime.combine(date.today(), t) - timedelta(minutes=minutes)
    return dt.time()


def has_available_slots_on_date(
    session,
    master_id: int,
    target_date: date,
    service_duration_mins: int,
    service_cooling_mins: int = 0
) -> bool:
    """Проверить, есть ли доступные слоты на дату"""
    slots = get_available_time_slots(session, master_id, target_date, service_duration_mins, service_cooling_mins)
    return len(slots) > 0

