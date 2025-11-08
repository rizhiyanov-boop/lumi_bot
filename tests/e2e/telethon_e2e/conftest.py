"""Конфигурация pytest для E2E тестов с Telethon"""
import pytest
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env.test
env_test_path = Path(__file__).parent.parent.parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path)
    print(f"Загружены переменные окружения из {env_test_path}")
else:
    print(f"Внимание: файл .env.test не найден по пути {env_test_path}")

# Маркер для E2E тестов с Telethon
# Загружаем фикстуры в правильном порядке:
# 1. database_fixtures - настройка тестовой БД (должна загружаться первой)
# 2. fixtures - Telethon клиенты и боты
pytest_plugins = [
    "tests.e2e.telethon_e2e.database_fixtures",
    "tests.e2e.telethon_e2e.fixtures"
]


def pytest_configure(config):
    """Регистрация маркеров pytest"""
    config.addinivalue_line(
        "markers", "e2e_telethon: mark test as E2E test with Telethon (requires Telegram API)"
    )


def pytest_collection_modifyitems(config, items):
    """Автоматически пропускать E2E тесты, если не установлены необходимые переменные окружения"""
    skip_e2e = pytest.mark.skip(reason="E2E тесты требуют TELEGRAM_API_ID, TELEGRAM_API_HASH и TELETHON_TEST_SESSION")
    
    telegram_api_id = os.getenv('TELEGRAM_API_ID')
    telegram_api_hash = os.getenv('TELEGRAM_API_HASH')
    telethon_test_session = os.getenv('TELETHON_TEST_SESSION')
    
    # Если переменные окружения не установлены, пропускаем все E2E тесты
    if not telegram_api_id or not telegram_api_hash or not telethon_test_session:
        for item in items:
            if "e2e_telethon" in item.keywords:
                item.add_marker(skip_e2e)
    
    # Выводим информацию о тестовой БД
    test_db_url = os.getenv('TEST_DATABASE_URL', 'sqlite:///test_database_e2e.db')
    e2e_tests_count = sum(1 for item in items if "e2e_telethon" in item.keywords)
    if e2e_tests_count > 0:
        print(f"\nНайдено {e2e_tests_count} E2E тестов")
        print(f"Тесты будут использовать тестовую БД: {test_db_url}")
        print("Важно: убедитесь, что тестовые боты используют ту же БД!")
        print(f"   Установите DATABASE_URL={test_db_url} при запуске тестовых ботов")
        print("   Или используйте скрипт: python run_test_bots.py\n")
