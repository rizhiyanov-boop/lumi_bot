"""Обработчики для мастер-бота - модульная структура"""
# Экспортируем все функции из модулей для обратной совместимости

# Общие утилиты и состояния
from .common import (
    get_onboarding_status,
    get_master_menu_commands,
    WAITING_NAME,
    WAITING_DESCRIPTION,
    WAITING_CATEGORY_NAME,
    WAITING_CATEGORY,
    WAITING_TEMPLATE,
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_DURATION,
    WAITING_SERVICE_DESCRIPTION,
    WAITING_SERVICE_COOLING,
    WAITING_SERVICE_ADVANCED,
    WAITING_EDIT_SERVICE_NAME,
    WAITING_EDIT_SERVICE_PRICE,
    WAITING_EDIT_SERVICE_DURATION,
    WAITING_EDIT_SERVICE_COOLING,
    WAITING_SCHEDULE_DAY,
    WAITING_SCHEDULE_START,
    WAITING_SCHEDULE_END,
    WAITING_SCHEDULE_START_MANUAL,
    WAITING_SCHEDULE_END_MANUAL,
    WAITING_CITY_NAME,
    WAITING_CITY_SELECT,
)

# Главное меню и команды
from .menu import (
    start_master,
    master_menu_callback,
    master_settings,
    receive_location,
    start_city_input,
    receive_city_name,
    select_city_from_search,
    retry_city_input,
    cancel_city_input,
)

# QR и приглашения
from .qr import (
    master_qr,
    copy_link,
)

# Записи
from .bookings import (
    master_bookings,
)

# Профиль
from .profile import (
    master_profile,
    edit_name_start,
    edit_description_start,
    receive_name,
    receive_description,
    upload_photo,
    receive_photo,
)

# Услуги
from .services import (
    master_services,
    add_category_start,
    receive_category_name,
    add_service_start,
    service_category_selected,
    service_template_selected,
    receive_service_name,
    receive_service_price,
    service_duration_selected,
    receive_service_duration,
    receive_service_cooling,
    receive_service_description,
    service_skip_description,
    service_change_duration,
    service_advanced_settings,
    service_set_cooling,
    service_save_default,
    service_back_to_name,
    service_back_to_price,
    service_back_to_template,
    service_back_to_advanced,
    create_service_from_data,
    edit_service,
    delete_service_confirm,
    delete_service_execute,
    edit_service_name_start,
    receive_edit_service_name,
    edit_service_price_start,
    receive_edit_service_price,
    edit_service_duration_start,
    receive_edit_service_duration,
    edit_service_cooling_start,
    receive_edit_service_cooling,
)

# Расписание
from .schedule import (
    master_schedule,
    schedule_edit_day,
    schedule_edit_week,
    schedule_add_period_start,
    schedule_start_selected,
    schedule_start_received,
    schedule_end_selected,
    schedule_end_received,
    schedule_delete_period,
    schedule_delete_temp_period,
    schedule_save_changes,
    schedule_cancel_changes,
    schedule_save_week,
    schedule_cancel_week,
)

# Портфолио
from .portfolio import (
    master_portfolio,
    portfolio_add,
    receive_portfolio_photo,
    portfolio_view,
    portfolio_next,
    portfolio_prev,
    portfolio_delete,
    portfolio_delete_confirm,
)

# Премиум
from .premium import (
    master_premium,
    premium_pay,
    premium_check_status,
)

# Команды
from .commands import (
    master_profile_command,
    master_services_command,
    master_schedule_command,
    master_qr_command,
    master_bookings_command,
)

__all__ = [
    # Common
    'get_onboarding_status',
    'get_master_menu_commands',
    'WAITING_NAME',
    'WAITING_DESCRIPTION',
    'WAITING_CATEGORY_NAME',
    'WAITING_CATEGORY',
    'WAITING_TEMPLATE',
    'WAITING_SERVICE_NAME',
    'WAITING_SERVICE_PRICE',
    'WAITING_SERVICE_DURATION',
    'WAITING_SERVICE_DESCRIPTION',
    'WAITING_SERVICE_COOLING',
    'WAITING_SERVICE_ADVANCED',
    'WAITING_EDIT_SERVICE_NAME',
    'WAITING_EDIT_SERVICE_PRICE',
    'WAITING_EDIT_SERVICE_DURATION',
    'WAITING_EDIT_SERVICE_COOLING',
    'WAITING_SCHEDULE_DAY',
    'WAITING_SCHEDULE_START',
    'WAITING_SCHEDULE_END',
    'WAITING_SCHEDULE_START_MANUAL',
    'WAITING_SCHEDULE_END_MANUAL',
    'WAITING_CITY_NAME',
    'WAITING_CITY_SELECT',
    # Menu
    'start_master',
    'master_menu_callback',
    'master_settings',
    'receive_location',
    'start_city_input',
    'receive_city_name',
    'select_city_from_search',
    'retry_city_input',
    'cancel_city_input',
    # QR
    'master_qr',
    'copy_link',
    # Bookings
    'master_bookings',
    # Profile
    'master_profile',
    'edit_name_start',
    'edit_description_start',
    'receive_name',
    'receive_description',
    'upload_photo',
    'receive_photo',
    # Services
    'master_services',
    'add_category_start',
    'receive_category_name',
    'add_service_start',
    'service_category_selected',
    'service_template_selected',
    'receive_service_name',
    'receive_service_price',
    'service_duration_selected',
    'receive_service_duration',
    'receive_service_cooling',
    'receive_service_description',
    'service_skip_description',
    'service_change_duration',
    'service_advanced_settings',
    'service_set_cooling',
    'service_save_default',
    'service_back_to_name',
    'service_back_to_price',
    'service_back_to_template',
    'service_back_to_advanced',
    'create_service_from_data',
    'edit_service',
    'delete_service_confirm',
    'delete_service_execute',
    'edit_service_name_start',
    'receive_edit_service_name',
    'edit_service_price_start',
    'receive_edit_service_price',
    'edit_service_duration_start',
    'receive_edit_service_duration',
    'edit_service_cooling_start',
    'receive_edit_service_cooling',
    # Schedule
    'master_schedule',
    'schedule_edit_day',
    'schedule_edit_week',
    'schedule_add_period_start',
    'schedule_start_selected',
    'schedule_start_received',
    'schedule_end_selected',
    'schedule_end_received',
    'schedule_delete_period',
    'schedule_delete_temp_period',
    'schedule_save_changes',
    'schedule_cancel_changes',
    'schedule_save_week',
    'schedule_cancel_week',
    # Portfolio
    'master_portfolio',
    'portfolio_add',
    'receive_portfolio_photo',
    'portfolio_view',
    'portfolio_next',
    'portfolio_prev',
    'portfolio_delete',
    'portfolio_delete_confirm',
    # Premium
    'master_premium',
    'premium_pay',
    'premium_check_status',
    # Commands
    'master_profile_command',
    'master_services_command',
    'master_schedule_command',
    'master_qr_command',
    'master_bookings_command',
]

