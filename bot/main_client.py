"""Главный файл запуска бота для клиентов"""
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

from bot.config import CLIENT_BOT_TOKEN
from bot.database.db import init_db

# Импорт обработчиков для клиентского бота
from bot.handlers.client import (
    start_client,
    client_masters,
    view_master,
    remove_master_confirm,
    book_master,
    select_service,
    select_date,
    select_time,
    add_comment,
    receive_comment,
    skip_comment,
    confirm_booking,
    cancel_booking,
    client_bookings,
    client_menu_callback,
    client_help,
    WAITING_BOOKING_DATE,
    WAITING_BOOKING_TIME,
    WAITING_BOOKING_COMMENT,
    client_masters_command,
    client_bookings_command,
    client_help_command,
    get_client_menu_commands
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: object) -> None:
    """Обработчик ошибок"""
    logger.error("Exception while handling an update:", exc_info=context.error)


async def post_init(application: Application):
    """Функция, вызываемая после инициализации бота - настройка меню команд"""
    # Автоматически генерируем команды на основе кнопок главного меню
    commands = get_client_menu_commands()
    
    await application.bot.set_my_commands(commands)
    logger.info(f"[INFO] Команды бота установлены автоматически: {[cmd.command for cmd in commands]}")


def main():
    """Запуск бота для клиентов"""
    
    # Проверка токена
    if not CLIENT_BOT_TOKEN:
        logger.error("[ERROR] CLIENT_BOT_TOKEN не установлен! Проверьте файл .env")
        return
    
    # Инициализация базы данных
    logger.info("[INFO] Инициализация базы данных...")
    init_db()
    
    # Создание приложения
    logger.info("[INFO] Запуск клиентского бота...")
    application = Application.builder().token(CLIENT_BOT_TOKEN).post_init(post_init).build()
    
    # ===== Обработчики команд =====
    application.add_handler(CommandHandler("start", start_client))
    application.add_handler(CommandHandler("masters", client_masters_command))
    application.add_handler(CommandHandler("bookings", client_bookings_command))
    application.add_handler(CommandHandler("help", client_help_command))
    
    # ===== ConversationHandler для бронирования =====
    booking_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_service, pattern=r'^select_service_\d+$'),
        ],
        states={
            WAITING_BOOKING_DATE: [
                CallbackQueryHandler(select_date, pattern=r'^(select_date_\d{4}-\d{2}-\d{2}|date_page_\d+)$'),
            ],
            WAITING_BOOKING_TIME: [
                CallbackQueryHandler(select_time, pattern=r'^select_time_\d{2}:\d{2}$'),
            ],
            WAITING_BOOKING_COMMENT: [
                CallbackQueryHandler(add_comment, pattern='^add_comment$'),
                CallbackQueryHandler(skip_comment, pattern='^skip_comment$'),
                CallbackQueryHandler(confirm_booking, pattern='^confirm_booking$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_booking, pattern='^cancel_booking$'),
            # Добавляем select_service в fallbacks, чтобы он мог перезапустить разговор
            CallbackQueryHandler(select_service, pattern=r'^select_service_\d+$'),
        ],
        per_message=False,
        name="booking"
    )
    application.add_handler(booking_conversation)
    
    # ===== Callback обработчики =====
    application.add_handler(CallbackQueryHandler(client_menu_callback, pattern='^client_menu$'))
    application.add_handler(CallbackQueryHandler(client_masters, pattern='^client_masters$'))
    application.add_handler(CallbackQueryHandler(view_master, pattern=r'^view_master_\d+$'))
    application.add_handler(CallbackQueryHandler(remove_master_confirm, pattern=r'^remove_master_\d+$'))
    application.add_handler(CallbackQueryHandler(book_master, pattern=r'^book_master_\d+$'))
    application.add_handler(CallbackQueryHandler(client_bookings, pattern='^client_bookings$'))
    # Обработчики просмотра фото и портфолио
    from bot.handlers.client import (
        client_master_photo,
        client_service_portfolio,
        client_portfolio_next,
        client_portfolio_prev
    )
    application.add_handler(CallbackQueryHandler(client_master_photo, pattern=r'^client_master_photo_\d+$'))
    application.add_handler(CallbackQueryHandler(client_service_portfolio, pattern=r'^client_service_portfolio_\d+$'))
    application.add_handler(CallbackQueryHandler(client_portfolio_next, pattern='^client_portfolio_next$'))
    application.add_handler(CallbackQueryHandler(client_portfolio_prev, pattern='^client_portfolio_prev$'))
    application.add_handler(CallbackQueryHandler(client_help, pattern='^client_help$'))
    # Дополнительные обработчики (confirm_booking, add_comment, skip_comment уже в ConversationHandler)
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    logger.info("[OK] Клиентский бот успешно запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

