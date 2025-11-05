"""Общие утилиты и состояния для мастер-бота"""
import logging
from bot.database.db import (
    get_session,
    get_services_by_master,
    get_work_periods,
)

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

