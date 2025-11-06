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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: object) -> None:
    """Обработчик ошибок"""
    from telegram.error import Conflict
    
    error = context.error
    
    # Обработка конфликта getUpdates - другой экземпляр бота уже запущен
    if isinstance(error, Conflict) and "getUpdates" in str(error):
        logger.error(f"[ERROR] Conflict: Другой экземпляр бота уже запущен. Остановите все другие процессы бота.")
        logger.error(f"[ERROR] Ошибка: {error}")
        return
    
    logger.error("Exception while handling an update:", exc_info=error)


async def post_init(application: Application):
    """Функция, вызываемая после инициализации бота - настройка меню команд"""
    # Очистка webhook (на случай если был установлен webhook)
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("[INFO] Webhook очищен (если был установлен)")
    except Exception as e:
        logger.warning(f"[WARNING] Не удалось очистить webhook: {e}")
    
    # Автоматически генерируем команды на основе кнопок главного меню
    commands = get_master_menu_commands()
    
    await application.bot.set_my_commands(commands)
    logger.info(f"[INFO] Команды бота установлены автоматически: {[cmd.command for cmd in commands]}")


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
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # ===== Обработчики команд =====
    application.add_handler(CommandHandler("start", start_master))
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
            WAITING_SERVICE_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_service_description),
                CallbackQueryHandler(service_skip_description, pattern='^service_skip_description$')
            ],
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
            CallbackQueryHandler(schedule_start_selected, pattern=r'^schedule_start_\d+'),
            # Убираем schedule_end_selected из entry_points, так как он должен вызываться только после выбора времени начала
        ],
        states={
            WAITING_SCHEDULE_START: [
                CallbackQueryHandler(schedule_start_selected, pattern=r'^schedule_start_\d+'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_start_received)
            ],
            WAITING_SCHEDULE_START_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_start_received)
            ],
            WAITING_SCHEDULE_END: [
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
            CallbackQueryHandler(schedule_add_period_start, pattern=r'^schedule_add_period_\d+$')
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
    # Обработчики загрузки фото и портфолио
    from bot.handlers.master import (
        upload_photo,
        receive_photo,
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
    # Обработчик получения фото (общий для фото профиля и портфолио)
    application.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    # Обработчик копирования ссылки
    from bot.handlers.master import copy_link
    application.add_handler(CallbackQueryHandler(copy_link, pattern=r'^copy_link_\d+$'))
    # Обработчики расписания
    application.add_handler(CallbackQueryHandler(schedule_edit_day, pattern=r'^edit_day_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_edit_week, pattern='^edit_week$'))
    application.add_handler(CallbackQueryHandler(schedule_delete_period, pattern=r'^schedule_delete_period_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_delete_temp_period, pattern=r'^schedule_delete_temp_\d+_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_save_changes, pattern=r'^schedule_save_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_cancel_changes, pattern=r'^schedule_cancel_\d+$'))
    application.add_handler(CallbackQueryHandler(schedule_save_week, pattern='^schedule_save_week$'))
    application.add_handler(CallbackQueryHandler(schedule_cancel_week, pattern='^schedule_cancel_week$'))
    
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
    
    # Запуск бота
    logger.info("[OK] Мастер-бот успешно запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

