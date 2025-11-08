"""Главный файл запуска бота для мастеров"""
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from bot.config import BOT_TOKEN
from bot.database.db import init_db

# Импорт обработчиков для мастер-бота
from bot.handlers.admin import (
    admin_panel,
    admin_masters_list,
    admin_master_detail,
    admin_block_master,
    admin_unblock_master,
    admin_delete_confirm,
    admin_delete_execute,
    admin_change_subscription,
    admin_set_subscription,
    admin_blocked_masters,
    admin_search_master_start,
    admin_search_master_result,
    admin_impersonate_master,
    admin_stop_impersonation,
    admin_block_reason_received,
    create_admin_conversation_handler,
    WAITING_BLOCK_REASON,
    WAITING_SEARCH_QUERY,
)
from bot.handlers.master import (
    start_master,
    master_profile,
    master_services,
    master_schedule,
    master_qr,
    master_bookings,
    master_menu_callback,
    master_settings,
    master_premium,
    master_portfolio,
    premium_pay,
    premium_check_status,
    edit_name_start,
    edit_description_start,
    receive_name,
    receive_description,
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
    edit_service_description_start,
    edit_service_generate_description,
    edit_service_save_generated_description,
    edit_service_enter_description_manual,
    receive_edit_service_description,
    edit_service_delete_description,
    new_service_generate_description,
    service_created_next,
    schedule_edit_day,
    schedule_add_period_start,
    schedule_start_selected,
    schedule_start_received,
    schedule_end_selected,
    schedule_end_received,
    schedule_delete_period,
    schedule_delete_temp_period,
    schedule_save_changes,
    schedule_cancel_changes,
    schedule_toggle_day,
    schedule_confirm_days,
    schedule_finish_setup,
    schedule_add_period_start_multi,
    WAITING_NAME,
    WAITING_DESCRIPTION,
    WAITING_CATEGORY_NAME,
    WAITING_CATEGORY,
    WAITING_TEMPLATE,
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_DURATION,
    WAITING_SERVICE_DESCRIPTION,
    WAITING_SERVICE_ADVANCED,
    WAITING_SERVICE_COOLING,
    WAITING_EDIT_SERVICE_NAME,
    WAITING_EDIT_SERVICE_PRICE,
    WAITING_EDIT_SERVICE_DURATION,
    WAITING_EDIT_SERVICE_COOLING,
    WAITING_EDIT_SERVICE_DESCRIPTION,
    WAITING_SCHEDULE_START,
    WAITING_SCHEDULE_END,
    WAITING_SCHEDULE_START_MANUAL,
    WAITING_SCHEDULE_END_MANUAL,
    master_profile_command,
    master_services_command,
    master_schedule_command,
    master_qr_command,
    master_bookings_command,
    get_master_menu_commands
)

# Импортируем функции регистрации напрямую из menu.py
from bot.handlers.master.menu import (
    start_registration,
    use_telegram_name,
    enter_custom_name,
    back_to_name_choice,
    receive_registration_name,
    start_registration_description,
    enter_description,
    skip_description,
    receive_registration_description,
    start_registration_photo,
    upload_registration_photo,
    skip_photo,
    receive_registration_photo,
)
from bot.handlers.master.common import (
    WAITING_REGISTRATION_NAME,
    WAITING_REGISTRATION_DESCRIPTION,
    WAITING_REGISTRATION_PHOTO,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: object) -> None:
    """Обработчик ошибок"""
    from telegram.error import Conflict, TimedOut, NetworkError
    
    error = context.error
    
    # Обработка конфликта getUpdates - другой экземпляр бота уже запущен
    if isinstance(error, Conflict) and "getUpdates" in str(error):
        logger.error(f"[ERROR] Conflict: Другой экземпляр бота уже запущен. Остановите все другие процессы бота.")
        logger.error(f"[ERROR] Ошибка: {error}")
        return
    
    # Игнорируем таймауты и сетевые ошибки - библиотека автоматически переподключится
    if isinstance(error, (TimedOut, NetworkError)):
        logger.warning(f"[WARNING] Таймаут или сетевая ошибка при получении обновлений: {error}. Переподключение...")
        return
    
    logger.error("Exception while handling an update:", exc_info=error)


async def post_init(application: Application):
    """Функция, вызываемая после инициализации бота - настройка меню команд"""
    # Примечание: webhook автоматически очищается в run_polling, поэтому здесь не нужно
    # Автоматически генерируем команды на основе кнопок главного меню
    # Используем большой таймаут для медленных подключений
    try:
        commands = get_master_menu_commands()
        await asyncio.wait_for(
            application.bot.set_my_commands(commands),
            timeout=60.0  # Увеличен до 60 секунд для медленных подключений
        )
        logger.info(f"[INFO] Команды бота установлены автоматически: {[cmd.command for cmd in commands]}")
    except asyncio.TimeoutError:
        logger.warning("[WARNING] Таймаут при установке команд (бот продолжит работу без команд в меню)")
    except Exception as e:
        logger.warning(f"[WARNING] Не удалось установить команды: {e} (бот продолжит работу)")


def main():
    """Запуск бота для мастеров"""
    
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("[ERROR] BOT_TOKEN не установлен! Проверьте файл .env")
        return
    
    # Инициализация базы данных
    logger.info("[INFO] Инициализация базы данных...")
    init_db()
    
    # Создание приложения
    logger.info("[INFO] Запуск мастер-бота...")
    # Используем стандартные настройки с увеличенными таймаутами только для чтения
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,     # Увеличенный таймаут для long polling
        write_timeout=30.0
    )
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )
    
    # ===== ConversationHandler для регистрации профиля (первый вход) =====
    # Важно: должен быть ДО других обработчиков, чтобы перехватывать /start для новых пользователей
    async def start_command_with_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка перед началом регистрации"""
        from bot.database.db import get_session, get_master_by_telegram
        user = update.effective_user
        with get_session() as session:
            master = get_master_by_telegram(session, user.id)
            if not master:
                # Мастера нет - начинаем регистрацию
                return await start_registration(update, context)
            else:
                # Мастер есть - вызываем обычный start_master и завершаем ConversationHandler
                await start_master(update, context)
                return ConversationHandler.END
    
    registration_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command_with_check),
        ],
        states={
            WAITING_REGISTRATION_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_registration_name),
                CallbackQueryHandler(use_telegram_name, pattern='^use_telegram_name$'),
                CallbackQueryHandler(enter_custom_name, pattern='^enter_custom_name$'),
                CallbackQueryHandler(back_to_name_choice, pattern='^back_to_name_choice$'),
            ],
            WAITING_REGISTRATION_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_registration_description),
                CallbackQueryHandler(skip_description, pattern='^skip_description$'),
                CallbackQueryHandler(enter_description, pattern='^enter_description$'),
            ],
            WAITING_REGISTRATION_PHOTO: [
                MessageHandler(filters.PHOTO, receive_registration_photo),
                CallbackQueryHandler(skip_photo, pattern='^skip_photo$'),
                CallbackQueryHandler(upload_registration_photo, pattern='^upload_registration_photo$'),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_registration),
            CommandHandler("cancel", start_registration),
        ],
        per_message=False,
        name="registration"
    )
    application.add_handler(registration_conversation)
    
    # ===== Обработчики команд =====
    # Обратите внимание: CommandHandler("start") уже обработан выше в registration_conversation
    application.add_handler(CommandHandler("profile", master_profile_command))
    application.add_handler(CommandHandler("services", master_services_command))
    application.add_handler(CommandHandler("schedule", master_schedule_command))
    application.add_handler(CommandHandler("qr", master_qr_command))
    application.add_handler(CommandHandler("bookings", master_bookings_command))
    # Админ-панель
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("stop_impersonation", admin_stop_impersonation))
    # Обработчик кнопки выхода из имперсонации
    application.add_handler(CallbackQueryHandler(admin_stop_impersonation, pattern='^stop_impersonation$'))
    
    # ===== ConversationHandler для редактирования имени =====
    edit_name_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_name_start, pattern='^edit_name$')],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)]
        },
        fallbacks=[CallbackQueryHandler(master_profile, pattern='^master_profile$')],
        per_message=False,
        name="edit_name"
    )
    application.add_handler(edit_name_conversation)
    
    # ===== ConversationHandler для редактирования описания =====
    edit_description_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_description_start, pattern='^edit_description$')],
        states={
            WAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)]
        },
        fallbacks=[CallbackQueryHandler(master_profile, pattern='^master_profile$')],
        per_message=False,
        name="edit_description"
    )
    application.add_handler(edit_description_conversation)
    
    # ===== Обработчики кнопок "назад" (регистрируем ДО ConversationHandler'ов) =====
    # Это гарантирует, что кнопки "назад" будут обрабатываться даже если активен ConversationHandler
    application.add_handler(CallbackQueryHandler(master_menu_callback, pattern='^master_menu$'))
    application.add_handler(CallbackQueryHandler(master_settings, pattern='^master_settings$'))
    application.add_handler(CallbackQueryHandler(master_profile, pattern='^master_profile$'))
    application.add_handler(CallbackQueryHandler(master_services, pattern='^master_services$'))
    application.add_handler(CallbackQueryHandler(master_schedule, pattern='^master_schedule$'))
    application.add_handler(CallbackQueryHandler(master_portfolio, pattern='^master_portfolio$'))
    application.add_handler(CallbackQueryHandler(master_premium, pattern='^master_premium$'))
    
    # Обработчики для новых функций после создания услуги
    application.add_handler(CallbackQueryHandler(new_service_generate_description, pattern=r'^new_service_generate_description_\d+$'))
    application.add_handler(CallbackQueryHandler(service_created_next, pattern=r'^service_created_next_\d+$'))
    
    # ===== ConversationHandler для добавления категории =====
    add_category_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_category_start, pattern='^add_category$')],
        states={
            WAITING_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name)]
        },
        fallbacks=[CallbackQueryHandler(master_services, pattern='^master_services$')],
        per_message=False,
        name="add_category"
    )
    application.add_handler(add_category_conversation)
    
    # ===== ConversationHandler для ввода города вручную =====
    # Должен быть ДО add_service_conversation, чтобы иметь приоритет при обработке текста
    # когда установлен флаг waiting_city_name
    from bot.handlers.master import (
        start_city_input,
        receive_city_name,
        select_city_from_search,
        retry_city_input,
        cancel_city_input,
        WAITING_CITY_NAME,
        WAITING_CITY_SELECT,
    )
    
    # Entry point для прямого ввода города (когда пользователь просто вводит название)
    async def city_input_entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point для активации ввода города при прямом вводе названия"""
        # Проверяем, что это текстовое сообщение
        if not update.message or not update.message.text:
            return None
        
        text = update.message.text.strip()
        
        # ПРИОРИТЕТНАЯ ПРОВЕРКА #1: если в тексте только цифры или числа с запятыми/точками/пробелами,
        # скорее всего это цена, а не город - НИКОГДА не активируем ввод города
        try:
            # Пытаемся преобразовать в число (убираем пробелы, заменяем запятую на точку)
            cleaned_text = text.replace(',', '.').replace(' ', '').replace('\xa0', '')  # \xa0 - неразрывный пробел
            float(cleaned_text)
            # Если получилось - это точно число (цена), а не город
            logger.debug(f"City input entry point: text '{text}' is a number (price?), ignoring")
            return None
        except (ValueError, AttributeError):
            # Не число - может быть город, продолжаем проверки
            pass
        
        # ПРИОРИТЕТНАЯ ПРОВЕРКА #2: если пользователь создает услугу, НИКОГДА не активируем ввод города
        # Проверяем все возможные состояния создания услуги
        if ('service_name' in context.user_data or 
            'service_price' in context.user_data or 
            'service_category_id' in context.user_data or
            'service_duration' in context.user_data or
            'service_cooling' in context.user_data or
            'service_template' in context.user_data):
            logger.debug(f"City input entry point: user is creating service, ignoring. Text: {text}")
            return None
        
        # Проверяем, что ожидается ввод города
        if not context.user_data.get('waiting_city_name'):
            return None
        
        # Если все проверки пройдены, вызываем receive_city_name напрямую
        # и возвращаем результат, чтобы активировать ConversationHandler
        logger.info(f"City input entry point activated for text: {text}")
        result = await receive_city_name(update, context)
        return result if result is not None else WAITING_CITY_NAME
    
    city_input_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & filters.Regex(r'^✏️ Ввести город вручную$'), start_city_input),
            CallbackQueryHandler(retry_city_input, pattern='^retry_city_input$'),
            # НЕ добавляем общий MessageHandler в entry_points - используем отдельный обработчик ниже
        ],
        states={
            WAITING_CITY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^✏️ Ввести город вручную$'), receive_city_name)
            ],
            WAITING_CITY_SELECT: [
                CallbackQueryHandler(select_city_from_search, pattern=r'^select_city_\d+$'),
                CallbackQueryHandler(retry_city_input, pattern='^retry_city_input$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_city_input, pattern='^cancel_city_input$'),
            CommandHandler("start", cancel_city_input),
            CommandHandler("cancel", cancel_city_input),
            # Геолокация обрабатывается отдельным handler, но если она пришла во время ConversationHandler, завершаем его
            MessageHandler(filters.LOCATION, cancel_city_input),
        ],
        per_message=False,
        name="city_input"
    )
    # Регистрируем ПЕРЕД add_service_conversation
    application.add_handler(city_input_conversation)
    
    # ===== ConversationHandler для добавления услуги =====
    add_service_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_service_start, pattern='^add_service$'),
            # Добавляем entry point для прямых вызовов категорий (если ConversationHandler не активен)
            CallbackQueryHandler(service_category_selected, pattern=r'^service_category_(predef_\w+|custom|\d+)$'),
        ],
        states={
            WAITING_CATEGORY: [
                CallbackQueryHandler(service_category_selected, pattern=r'^service_category_(predef_\w+|custom|\d+)$'),
                # Также добавляем обработчик для "Отмена"
                CallbackQueryHandler(master_services, pattern='^master_services$')
            ],
            WAITING_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name)
            ],
            WAITING_TEMPLATE: [
                CallbackQueryHandler(service_template_selected, pattern=r'^service_template_.+$'),
                # Добавляем обработчик для кнопки "Назад" при выборе шаблона
                CallbackQueryHandler(add_service_start, pattern='^add_service$')
            ],
            WAITING_SERVICE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_service_name),
                # Обработчики для возврата назад
                CallbackQueryHandler(service_back_to_template, pattern='^service_back_to_template$'),
                CallbackQueryHandler(service_category_selected, pattern=r'^service_category_(predef_\w+|custom|\d+)$')
            ],
            WAITING_SERVICE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_service_price),
                # Обработчики для возврата назад
                CallbackQueryHandler(service_back_to_name, pattern='^service_back_to_name$')
            ],
            WAITING_SERVICE_DURATION: [
                CallbackQueryHandler(service_duration_selected, pattern=r'^service_duration_(\d+|manual)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_service_duration),
                # Обработчики для возврата назад
                CallbackQueryHandler(service_back_to_name, pattern='^service_back_to_name$'),
                CallbackQueryHandler(service_back_to_advanced, pattern='^service_back_to_advanced$')
            ],
            WAITING_SERVICE_ADVANCED: [
                CallbackQueryHandler(service_change_duration, pattern='^service_change_duration$'),
                CallbackQueryHandler(service_advanced_settings, pattern='^service_advanced_settings$'),
                CallbackQueryHandler(service_set_cooling, pattern='^service_set_cooling$'),
                CallbackQueryHandler(service_save_default, pattern='^service_save_default$'),
                # Обработчик выбора длительности (изменение через кнопки)
                CallbackQueryHandler(service_duration_selected, pattern=r'^service_duration_(\d+|manual)$'),
                # Обработчики для возврата назад
                CallbackQueryHandler(service_back_to_price, pattern='^service_back_to_price$')
            ],
            WAITING_SERVICE_COOLING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_service_cooling),
                CallbackQueryHandler(service_save_default, pattern='^service_save_default$'),
                # Обработчики для возврата назад
                CallbackQueryHandler(service_back_to_advanced, pattern='^service_back_to_advanced$')
            ],
            # Убираем WAITING_SERVICE_DESCRIPTION из процесса создания - описание добавляется через редактирование
        },
        fallbacks=[
            CallbackQueryHandler(master_services, pattern='^master_services$'),
            CallbackQueryHandler(add_service_start, pattern='^add_service$')
        ],
        per_message=False,
        name="add_service"
    )
    application.add_handler(add_service_conversation)
    
    # ===== ConversationHandler для редактирования услуги =====
    edit_service_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_service_name_start, pattern=r'^edit_service_name_\d+$'),
            CallbackQueryHandler(edit_service_price_start, pattern=r'^edit_service_price_\d+$'),
            CallbackQueryHandler(edit_service_duration_start, pattern=r'^edit_service_duration_\d+$'),
            CallbackQueryHandler(edit_service_cooling_start, pattern=r'^edit_service_cooling_\d+$'),
            CallbackQueryHandler(edit_service_description_start, pattern=r'^edit_service_description_\d+$'),
        ],
        states={
            WAITING_EDIT_SERVICE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_service_name)
            ],
            WAITING_EDIT_SERVICE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_service_price)
            ],
            WAITING_EDIT_SERVICE_DURATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_service_duration)
            ],
            WAITING_EDIT_SERVICE_COOLING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_service_cooling)
            ],
            WAITING_EDIT_SERVICE_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_service_description),
                CallbackQueryHandler(edit_service_generate_description, pattern=r'^edit_service_generate_description_\d+$'),
                CallbackQueryHandler(edit_service_save_generated_description, pattern=r'^edit_service_save_generated_description_\d+$'),
                CallbackQueryHandler(edit_service_enter_description_manual, pattern=r'^edit_service_enter_description_manual_\d+$'),
                CallbackQueryHandler(edit_service_delete_description, pattern=r'^edit_service_delete_description_\d+$'),
                CallbackQueryHandler(edit_service_description_start, pattern=r'^edit_service_description_\d+$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(master_services, pattern='^master_services$'),
            CallbackQueryHandler(edit_service, pattern=r'^edit_service_\d+$')
        ],
        per_message=False,
        name="edit_service"
    )
    application.add_handler(edit_service_conversation)
    
    # ===== ConversationHandler для расписания =====
    schedule_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(schedule_add_period_start, pattern=r'^schedule_add_period_\d+$'),
            CallbackQueryHandler(schedule_confirm_days, pattern='^schedule_confirm_days$'),
            CallbackQueryHandler(schedule_start_selected, pattern=r'^schedule_start(_multi)?_\d+'),
            CallbackQueryHandler(schedule_start_selected, pattern=r'^schedule_start(_multi)?_manual$'),
            # Убираем schedule_end_selected из entry_points, так как он должен вызываться только после выбора времени начала
        ],
        states={
            WAITING_SCHEDULE_START: [
                CallbackQueryHandler(schedule_start_selected, pattern=r'^schedule_start(_multi)?_\d+'),
                CallbackQueryHandler(schedule_start_selected, pattern=r'^schedule_start(_multi)?_manual$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_start_received)
            ],
            WAITING_SCHEDULE_START_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_start_received)
            ],
            WAITING_SCHEDULE_END: [
                CallbackQueryHandler(schedule_end_selected, pattern=r'^schedule_end_multi_.*$'),
                CallbackQueryHandler(schedule_end_selected, pattern=r'^schedule_end_(\d+_\d+_\d+|manual_\d+_\d+|\d+)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_end_received)
            ],
            WAITING_SCHEDULE_END_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_end_received)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(master_schedule, pattern='^master_schedule$'),
            CallbackQueryHandler(schedule_edit_day, pattern=r'^edit_day_\d+$'),
            # Добавляем fallback для повторного добавления периода после завершения
            CallbackQueryHandler(schedule_add_period_start, pattern=r'^schedule_add_period_\d+$'),
        ],
        per_message=False,
        name="schedule"
    )
    application.add_handler(schedule_conversation)
    
    # ===== Callback обработчики =====
    application.add_handler(CallbackQueryHandler(master_menu_callback, pattern='^master_menu$'))
    application.add_handler(CallbackQueryHandler(master_settings, pattern='^master_settings$'))
    application.add_handler(CallbackQueryHandler(master_profile, pattern='^master_profile$'))
    # Обработчики анбординга
    from bot.handlers.master.onboarding import (
        onboarding_profile,
        onboarding_services,
        onboarding_schedule,
        show_onboarding
    )
    application.add_handler(CallbackQueryHandler(onboarding_profile, pattern='^onboarding_profile$'))
    application.add_handler(CallbackQueryHandler(onboarding_services, pattern='^onboarding_services$'))
    application.add_handler(CallbackQueryHandler(onboarding_schedule, pattern='^onboarding_schedule$'))
    # Обработчики кнопок "Далее"
    from bot.handlers.master.onboarding import (
        onboarding_next_services,
        onboarding_next_schedule
    )
    application.add_handler(CallbackQueryHandler(onboarding_next_services, pattern='^onboarding_next_services$'))
    application.add_handler(CallbackQueryHandler(onboarding_next_schedule, pattern='^onboarding_next_schedule$'))
    application.add_handler(CallbackQueryHandler(master_services, pattern='^master_services$'))
    application.add_handler(CallbackQueryHandler(master_premium, pattern='^master_premium$'))
    application.add_handler(CallbackQueryHandler(premium_pay, pattern='^premium_pay$'))
    application.add_handler(CallbackQueryHandler(premium_check_status, pattern=r'^premium_check_[\w-]+$'))
    # Обработчик для выбора категории услуги (вне ConversationHandler, ПЕРЕД ним, чтобы перезапустить разговор)
    # Это позволяет перезапустить ConversationHandler даже если он активен
    application.add_handler(CallbackQueryHandler(service_category_selected, pattern=r'^service_category_(predef_\w+|custom|\d+)$'))
    application.add_handler(CallbackQueryHandler(master_schedule, pattern='^master_schedule$'))
    # Обработчик для добавления периода (вне ConversationHandler, чтобы работал после завершения)
    application.add_handler(CallbackQueryHandler(schedule_add_period_start, pattern=r'^schedule_add_period_\d+$'))
    application.add_handler(CallbackQueryHandler(master_qr, pattern='^master_qr$'))
    application.add_handler(CallbackQueryHandler(master_bookings, pattern='^master_bookings$'))
    # Обработчики для редактирования и удаления услуг
    application.add_handler(CallbackQueryHandler(edit_service, pattern=r'^edit_service_\d+$'))
    application.add_handler(CallbackQueryHandler(delete_service_confirm, pattern=r'^delete_service_confirm_\d+$'))
    application.add_handler(CallbackQueryHandler(delete_service_execute, pattern=r'^delete_service_execute_\d+$'))
    # Обработчики портфолио услуги
    from bot.handlers.master.services_portfolio import (
        service_portfolio,
        service_portfolio_add,
        service_portfolio_view,
        service_portfolio_next,
        service_portfolio_prev,
        service_portfolio_delete,
        service_portfolio_delete_confirm,
    )
    application.add_handler(CallbackQueryHandler(service_portfolio, pattern=r'^service_portfolio_\d+$'))
    application.add_handler(CallbackQueryHandler(service_portfolio_add, pattern=r'^service_portfolio_add_\d+$'))
    application.add_handler(CallbackQueryHandler(service_portfolio_view, pattern=r'^service_portfolio_view_\d+$'))
    application.add_handler(CallbackQueryHandler(service_portfolio_next, pattern=r'^service_portfolio_next_\d+$'))
    application.add_handler(CallbackQueryHandler(service_portfolio_prev, pattern=r'^service_portfolio_prev_\d+$'))
    application.add_handler(CallbackQueryHandler(service_portfolio_delete, pattern=r'^service_portfolio_delete_\d+$'))
    application.add_handler(CallbackQueryHandler(service_portfolio_delete_confirm, pattern=r'^service_portfolio_delete_confirm_\d+$'))
    # Обработчики загрузки фото и портфолио
    from bot.handlers.master import (
        upload_photo,
        receive_photo,
        receive_location,
        portfolio_add,
        receive_portfolio_photo,
        portfolio_view,
        portfolio_next,
        portfolio_prev,
        portfolio_delete,
        portfolio_delete_confirm
    )
    application.add_handler(CallbackQueryHandler(upload_photo, pattern='^upload_photo$'))
    application.add_handler(CallbackQueryHandler(master_portfolio, pattern='^master_portfolio$'))
    application.add_handler(CallbackQueryHandler(portfolio_add, pattern='^portfolio_add$'))
    application.add_handler(CallbackQueryHandler(portfolio_view, pattern='^portfolio_view$'))
    application.add_handler(CallbackQueryHandler(portfolio_next, pattern='^portfolio_next$'))
    application.add_handler(CallbackQueryHandler(portfolio_prev, pattern='^portfolio_prev$'))
    application.add_handler(CallbackQueryHandler(portfolio_delete, pattern='^portfolio_delete$'))
    application.add_handler(CallbackQueryHandler(portfolio_delete_confirm, pattern=r'^portfolio_delete_confirm_\d+$'))
    # Примечание: city_input_conversation уже зарегистрирован выше, перед add_service_conversation
    
    # Обработчик получения фото (общий для фото профиля и портфолио)
    application.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    # Обработчик получения геолокации для определения города
    application.add_handler(MessageHandler(filters.LOCATION, receive_location))
    
    # Отдельный обработчик для прямого ввода города (регистрируется ПОСЛЕ всех ConversationHandler'ов)
    # с низким приоритетом, чтобы не мешать созданию услуг
    async def handle_direct_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик прямого ввода города (когда пользователь просто вводит название)"""
        # Проверяем, что это текстовое сообщение
        if not update.message or not update.message.text:
            return
        
        text = update.message.text.strip()
        
        # ПРИОРИТЕТНАЯ ПРОВЕРКА #1: если в тексте только цифры - это цена, не город
        try:
            cleaned_text = text.replace(',', '.').replace(' ', '').replace('\xa0', '')
            float(cleaned_text)
            logger.debug(f"handle_direct_city_input: text '{text}' is a number, ignoring")
            return
        except (ValueError, AttributeError):
            pass
        
        # ПРИОРИТЕТНАЯ ПРОВЕРКА #2: если пользователь создает услугу - не обрабатываем
        if ('service_name' in context.user_data or 
            'service_price' in context.user_data or 
            'service_category_id' in context.user_data or
            'service_duration' in context.user_data or
            'service_cooling' in context.user_data or
            'service_template' in context.user_data):
            logger.debug(f"handle_direct_city_input: user is creating service, ignoring")
            return
        
        # Проверяем, что ожидается ввод города
        if not context.user_data.get('waiting_city_name'):
            return
        
        # Активируем ConversationHandler, вызывая receive_city_name
        logger.info(f"handle_direct_city_input: activating city input for text: {text}")
        # Проверяем, активен ли уже city_input_conversation
        # Если нет - активируем его через receive_city_name
        await receive_city_name(update, context)
    
    # Регистрируем ПОСЛЕ всех ConversationHandler'ов с низким приоритетом
    # group=-1 означает, что этот обработчик будет проверяться последним
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_direct_city_input), group=-1)
    # Обработчик копирования ссылки
    from bot.handlers.master import copy_link
    application.add_handler(CallbackQueryHandler(copy_link, pattern=r'^copy_link_\d+$'))
    # Обработчики расписания
    application.add_handler(CallbackQueryHandler(schedule_edit_day, pattern=r'^edit_day_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_toggle_day, pattern=r'^schedule_toggle_day_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_finish_setup, pattern='^schedule_finish_setup$'))
    application.add_handler(CallbackQueryHandler(schedule_delete_period, pattern=r'^schedule_delete_period_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_delete_temp_period, pattern=r'^schedule_delete_temp_\d+_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_save_changes, pattern=r'^schedule_save_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_cancel_changes, pattern=r'^schedule_cancel_\d+$'))
    
    # ===== Админ-панель =====
    # Важно: сначала регистрируем конкретные обработчики, потом ConversationHandler
    application.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    application.add_handler(CallbackQueryHandler(admin_masters_list, pattern=r'^admin_masters_list_\d+$'))
    application.add_handler(CallbackQueryHandler(admin_master_detail, pattern=r'^admin_master_detail_\d+$'))
    application.add_handler(CallbackQueryHandler(admin_unblock_master, pattern=r'^admin_unblock_\d+$'))
    application.add_handler(CallbackQueryHandler(admin_delete_confirm, pattern=r'^admin_delete_confirm_\d+$'))
    application.add_handler(CallbackQueryHandler(admin_delete_execute, pattern=r'^admin_delete_execute_\d+$'))
    application.add_handler(CallbackQueryHandler(admin_change_subscription, pattern=r'^admin_change_sub_\d+$'))
    application.add_handler(CallbackQueryHandler(admin_set_subscription, pattern=r'^admin_set_sub_\d+_(free|basic|premium)$'))
    application.add_handler(CallbackQueryHandler(admin_blocked_masters, pattern='^admin_blocked_masters$'))
    application.add_handler(CallbackQueryHandler(admin_impersonate_master, pattern=r'^admin_impersonate_\d+$'))
    # ConversationHandler должен быть последним, чтобы не перехватывать callback'и
    application.add_handler(create_admin_conversation_handler())
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота с настройками polling
    logger.info("[OK] Мастер-бот успешно запущен!")
    # Используем стандартные настройки polling с увеличенным timeout
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        poll_interval=1.0,  # Интервал между запросами (в секундах)
        timeout=30          # Timeout для get_updates (в секундах)
    )


if __name__ == '__main__':
    main()

