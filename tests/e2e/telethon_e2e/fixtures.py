"""Фикстуры для E2E-тестирования с Telethon"""
import pytest
import pytest_asyncio
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from typing import Optional
import logging

# Загружаем переменные окружения из .env.test
env_test_path = Path(__file__).parent.parent.parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path)

logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELETHON_TEST_SESSION = os.getenv('TELETHON_TEST_SESSION')
TEST_MASTER_BOT_USERNAME = os.getenv('TEST_MASTER_BOT_USERNAME', 'lumi_test_master_bot')
TEST_CLIENT_BOT_USERNAME = os.getenv('TEST_CLIENT_BOT_USERNAME', 'lumi_test_client_bot')


@pytest.fixture(scope="session")
def telethon_session_string():
    """Создает сессию Telethon для тестов из сохраненной строки"""
    if not TELETHON_TEST_SESSION:
        pytest.skip("TELETHON_TEST_SESSION не установлена в .env.test. Запусти generate_session.py для создания сессии.")
    
    # Создаем сессию из сохраненной строки
    return StringSession(TELETHON_TEST_SESSION)


@pytest_asyncio.fixture(scope="session")
async def telethon_client(telethon_session_string):
    """Создает Telethon клиент для тестирования"""
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        pytest.skip("TELEGRAM_API_ID и TELEGRAM_API_HASH не установлены. Пропускаем E2E тесты.")
    
    if not TELETHON_TEST_SESSION:
        pytest.skip("TELETHON_TEST_SESSION не установлена. Запусти generate_session.py для создания сессии.")
    
    api_id = int(TELEGRAM_API_ID)
    api_hash = TELEGRAM_API_HASH
    
    client = TelegramClient(
        telethon_session_string,
        api_id,
        api_hash,
        device_model="Lumi E2E Tests",
        system_version="1.0",
        app_version="1.0"
    )
    
    try:
        await client.connect()
        
        # Проверяем, авторизован ли клиент
        if not await client.is_user_authorized():
            pytest.skip("Telethon клиент не авторизован. Проверьте TELETHON_TEST_SESSION в .env.test")
        
        logger.info("Telethon client connected and authorized for E2E tests")
    except Exception as e:
        await client.disconnect()
        pytest.skip(f"Не удалось подключиться к Telegram: {e}")
    
    yield client
    
    await client.disconnect()
    logger.info("Telethon client disconnected")


@pytest_asyncio.fixture(scope="session")
async def test_master_bot(telethon_client):
    """Получает Entity тестового мастер-бота"""
    try:
        entity = await telethon_client.get_entity(TEST_MASTER_BOT_USERNAME)
        return entity
    except Exception as e:
        pytest.skip(f"Не удалось найти тестового мастер-бота {TEST_MASTER_BOT_USERNAME}: {e}")


@pytest_asyncio.fixture(scope="session")
async def test_client_bot(telethon_client):
    """Получает Entity тестового клиент-бота"""
    try:
        entity = await telethon_client.get_entity(TEST_CLIENT_BOT_USERNAME)
        return entity
    except Exception as e:
        pytest.skip(f"Не удалось найти тестового клиент-бота {TEST_CLIENT_BOT_USERNAME}: {e}")


# Фикстура clean_test_database перенесена в database_fixtures.py
# Она теперь автоматически применяется ко всем тестам через autouse=True


@pytest_asyncio.fixture
async def wait_for_bot_response():
    """Вспомогательная фикстура для ожидания ответа от бота"""
    async def _wait(timeout: float = 5.0):
        """Ждет ответа от бота"""
        await asyncio.sleep(timeout)
    return _wait


@pytest_asyncio.fixture(scope="session")
async def registered_master_session(telethon_client, test_master_bot):
    """
    Создает и регистрирует мастера один раз для всей сессии тестов.
    Переиспользуется между тестами для экономии API запросов.
    
    ВАЖНО: База данных очищается перед каждым тестом (autouse fixture),
    поэтому эта фикстура возвращает данные для регистрации, а не сам объект мастера.
    """
    from tests.e2e.telethon_e2e.helpers import send_message_and_wait, click_button_by_text
    
    logger.info("=== Создание session-wide мастера для переиспользования ===")
    
    # Получаем информацию о тестовом пользователе
    me = await telethon_client.get_me()
    
    # Данные для регистрации (будут переиспользоваться)
    master_data = {
        'telegram_id': me.id,
        'telegram_username': me.username,
        'name': f"Test Master {me.id}",
        'test_city': "тестовый123123123129543"  # Специальный тестовый город
    }
    
    logger.info(f"Session master data prepared: {master_data}")
    
    return master_data


@pytest_asyncio.fixture
async def registered_master(telethon_client, test_master_bot, registered_master_session, clean_test_database):
    """
    Быстро регистрирует мастера используя данные из session fixture.
    Вызывается для каждого теста после очистки БД.
    
    Использует:
    - registered_master_session: данные для регистрации (scope=session)
    - clean_test_database: очистка БД перед тестом (autouse)
    """
    from tests.e2e.telethon_e2e.helpers import send_message_and_wait, click_button_by_text
    
    master_data = registered_master_session
    
    logger.info(f"=== Быстрая регистрация мастера для теста ===")
    
    # Отправляем /start
    await send_message_and_wait(telethon_client, test_master_bot, "/start")
    await asyncio.sleep(2)
    
    # Используем имя из Telegram
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    if messages:
        await click_button_by_text(telethon_client, messages[0], "Использовать")
        await asyncio.sleep(2)
    
    # Пропускаем описание
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    if messages and "описание" in messages[0].message.lower():
        await click_button_by_text(telethon_client, messages[0], "Пропустить")
        await asyncio.sleep(2)
    
    # Пропускаем фото
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    if messages and "фото" in messages[0].message.lower():
        await click_button_by_text(telethon_client, messages[0], "Пропустить")
        await asyncio.sleep(2)
    
    # Вводим тестовый город
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    if messages and "город" in messages[0].message.lower():
        await send_message_and_wait(telethon_client, test_master_bot, master_data['test_city'])
        await asyncio.sleep(3)
        
        # Проверяем, что город установлен, если нет - отправляем /start для перехода в меню
        messages = await telethon_client.get_messages(test_master_bot, limit=1)
        if messages and ("не найден" in messages[0].message.lower() or "попробовать" in messages[0].message.lower()):
            logger.warning("Test city not recognized, sending /start to proceed")
            await send_message_and_wait(telethon_client, test_master_bot, "/start")
            await asyncio.sleep(2)
    
    logger.info("=== Мастер зарегистрирован ===")
    
    # Возвращаем данные мастера
    from bot.database.db import get_session, get_master_by_telegram
    
    with get_session() as session:
        master = get_master_by_telegram(session, master_data['telegram_id'])
        if master:
            return {
                'id': master.id,
                'telegram_id': master.telegram_id,
                'name': master.name,
                'city_id': master.city_id
            }
    
    return None

