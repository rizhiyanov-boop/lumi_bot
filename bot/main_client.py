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
    client_search_masters,
    client_search_city_masters,
    client_search_view_master,
    client_search_add_master,
    client_invite_master,
    client_settings,
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
    # Автоматически генерируем команды на основе кнопок главного меню
    # Используем большой таймаут для медленных подключений
    try:
        commands = get_client_menu_commands()
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
    
    # Патч для принудительного использования IPv4
    # Это необходимо, так как на некоторых серверах IPv6 вызывает проблемы с TLS
    import socket
    import asyncio
    
    original_getaddrinfo = socket.getaddrinfo
    
    def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        """Переопределяем getaddrinfo для использования только IPv4"""
        # Принудительно используем IPv4 вместо AF_UNSPEC (0) или AF_INET6
        if family == socket.AF_UNSPEC or family == 0:
            family = socket.AF_INET
        elif family == socket.AF_INET6:
            family = socket.AF_INET  # Заменяем IPv6 на IPv4
        return original_getaddrinfo(host, port, family, type, proto, flags)
    
    # Применяем патч для socket.getaddrinfo
    socket.getaddrinfo = getaddrinfo_ipv4_only
    
    # Патч для asyncio.getaddrinfo (если доступен)
    if hasattr(asyncio, 'getaddrinfo'):
        original_asyncio_getaddrinfo = asyncio.getaddrinfo
        
        async def asyncio_getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
            """Асинхронная версия getaddrinfo для использования только IPv4"""
            # Принудительно используем IPv4 вместо AF_UNSPEC (0) или AF_INET6
            if family == socket.AF_UNSPEC or family == 0:
                family = socket.AF_INET
            elif family == socket.AF_INET6:
                family = socket.AF_INET  # Заменяем IPv6 на IPv4
            return await original_asyncio_getaddrinfo(host, port, family, type, proto, flags)
        
        asyncio.getaddrinfo = asyncio_getaddrinfo_ipv4_only
        logger.info("[INFO] Настроен принудительный IPv4 для подключений (socket и asyncio)")
    else:
        logger.info("[INFO] Настроен принудительный IPv4 для подключений (socket)")
    
    # Настраиваем HTTP-клиент с увеличенными таймаутами для медленных соединений
    from telegram.request import HTTPXRequest
    
    # Используем HTTPXRequest с увеличенными таймаутами
    # HTTP/1.1 вместо HTTP/2 для лучшей совместимости
    request = HTTPXRequest(
        connect_timeout=60.0,  # Увеличен для медленных соединений
        read_timeout=90.0,     # Увеличен для long polling
        write_timeout=60.0,
        http_version="1.1"     # Используем HTTP/1.1 для стабильности
    )
    
    application = (
        Application.builder()
        .token(CLIENT_BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )
    
    # ===== Обработчики команд =====
    application.add_handler(CommandHandler("start", start_client))
    application.add_handler(CommandHandler("masters", client_masters_command))
    application.add_handler(CommandHandler("search", client_search_masters))
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
    application.add_handler(CallbackQueryHandler(client_search_masters, pattern='^client_search_masters$'))
    application.add_handler(CallbackQueryHandler(client_invite_master, pattern='^client_invite_master$'))
    application.add_handler(CallbackQueryHandler(client_search_city_masters, pattern=r'^search_city_\d+$'))
    application.add_handler(CallbackQueryHandler(client_search_view_master, pattern=r'^search_view_master_\d+$'))
    application.add_handler(CallbackQueryHandler(client_search_add_master, pattern=r'^search_add_master_\d+$'))
    application.add_handler(CallbackQueryHandler(view_master, pattern=r'^view_master_\d+$'))
    application.add_handler(CallbackQueryHandler(remove_master_confirm, pattern=r'^remove_master_\d+$'))
    application.add_handler(CallbackQueryHandler(book_master, pattern=r'^book_master_\d+$'))
    application.add_handler(CallbackQueryHandler(client_bookings, pattern='^client_bookings$'))
    application.add_handler(CallbackQueryHandler(client_settings, pattern='^client_settings$'))
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
    
    # Запуск бота с настройками polling
    logger.info("[OK] Клиентский бот успешно запущен!")
    # Используем стандартный run_polling - он автоматически обрабатывает ошибки
    # При таймаутах при очистке webhook бот продолжит работу
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1.0,  # Интервал между запросами (в секундах)
            timeout=30,         # Timeout для get_updates (в секундах)
            drop_pending_updates=True  # Очищаем pending updates при старте
        )
    except KeyboardInterrupt:
        logger.info("[INFO] Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"[ERROR] Критическая ошибка при запуске бота: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()

