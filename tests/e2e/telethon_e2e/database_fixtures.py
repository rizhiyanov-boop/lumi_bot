"""Фикстуры для настройки тестовой базы данных"""
import pytest
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Загружаем переменные окружения из .env.test (если файл существует)
load_dotenv(dotenv_path=project_root / ".env.test")


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Настраивает тестовую базу данных для E2E тестов.
    Переопределяет DATABASE_URL в bot.config для использования тестовой БД.
    """
    # Получаем путь к тестовой БД из переменных окружения
    test_db_url = os.getenv('TEST_DATABASE_URL', 'sqlite:///test_database_e2e.db')
    
    # Если используется SQLite, создаем файл в временной директории или в корне проекта
    if test_db_url.startswith('sqlite:///'):
        # Извлекаем путь к файлу
        db_path = test_db_url.replace('sqlite:///', '')
        # Создаем абсолютный путь
        if not os.path.isabs(db_path):
            db_path = str(project_root / db_path)
        test_db_url = f'sqlite:///{db_path}'
    
    # Переопределяем DATABASE_URL в bot.config
    import bot.config
    original_db_url = bot.config.DATABASE_URL
    bot.config.DATABASE_URL = test_db_url
    
    # Переопределяем engine и SessionLocal в bot.database.db
    import bot.database.db
    bot.database.db.engine = create_engine(test_db_url, echo=False)
    bot.database.db.SessionLocal = sessionmaker(bind=bot.database.db.engine)
    
    # Инициализируем БД
    from bot.database.db import init_db
    init_db()
    
    yield
    
    # Восстанавливаем оригинальные значения
    bot.config.DATABASE_URL = original_db_url
    # Пересоздаем engine для основной БД
    bot.database.db.engine = create_engine(original_db_url, echo=False)
    bot.database.db.SessionLocal = sessionmaker(bind=bot.database.db.engine)


@pytest.fixture(autouse=True)
def clean_test_database(setup_test_database):
    """
    Автоматически очищает тестовую базу данных перед каждым тестом.
    Использует autouse=True, чтобы применяться ко всем тестам автоматически.
    """
    from bot.database.db import get_session
    from bot.database.models import (
        MasterAccount, User, Service, ServiceCategory, 
        WorkPeriod, Booking, UserMaster, Portfolio, Payment,
        City, CountryCurrency
    )
    from sqlalchemy import delete, text
    
    # Очистка перед тестом
    with get_session() as session:
        # Удаляем все тестовые данные в правильном порядке (из-за foreign keys)
        # Важно: сначала удаляем записи с foreign keys, потом родительские
        session.execute(delete(Booking))
        session.execute(delete(UserMaster))
        session.execute(delete(Portfolio))
        session.execute(delete(WorkPeriod))
        session.execute(delete(Service))
        session.execute(delete(ServiceCategory))
        session.execute(delete(Payment))
        session.execute(delete(User))
        # Удаляем мастеров (но оставляем справочные данные - города и валюты)
        session.execute(delete(MasterAccount))
        session.commit()
    
    yield
    
    # Опционально: очистка после теста
    # Можно оставить данные для отладки, раскомментировав следующее:
    # with get_session() as session:
    #     session.execute(delete(Booking))
    #     session.execute(delete(UserMaster))
    #     session.execute(delete(Portfolio))
    #     session.execute(delete(WorkPeriod))
    #     session.execute(delete(Service))
    #     session.execute(delete(ServiceCategory))
    #     session.execute(delete(Payment))
    #     session.execute(delete(User))
    #     session.execute(delete(MasterAccount))
    #     session.commit()


@pytest.fixture(scope="session")
def test_database_file():
    """
    Возвращает путь к файлу тестовой базы данных.
    После завершения всех тестов можно удалить файл (опционально).
    """
    test_db_url = os.getenv('TEST_DATABASE_URL', 'sqlite:///test_database_e2e.db')
    
    if test_db_url.startswith('sqlite:///'):
        db_path = test_db_url.replace('sqlite:///', '')
        if not os.path.isabs(db_path):
            db_path = str(project_root / db_path)
        yield db_path
        
        # Опционально: удаляем файл БД после тестов
        # Раскомментируйте, если хотите удалять БД после тестов:
        # if os.path.exists(db_path):
        #     os.remove(db_path)
    else:
        yield None

