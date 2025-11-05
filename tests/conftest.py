"""Pytest configuration and fixtures"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from telegram import Update, User, Chat, CallbackQuery, Message
from telegram.ext import ContextTypes

from bot.database.db import get_session, init_db
from bot.database.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db():
    """Create a test database"""
    # In-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    # Initialize with test data
    # Note: init_db() creates its own session, so we'll create test data manually
    from bot.database.models import Club, Service, ServiceAddon, ParticipationPricing
    
    # Create test club
    test_club = Club(slug="test-club", name="Test Club", description="Test club for testing")
    session.add(test_club)
    session.commit()
    
    # Create test service
    test_service = Service(
        club_id=test_club.id,
        name="Пейнтбол",
        description="Test paintball service",
        price=1000.0,
        duration_hours=3,
        booking_type=Service.BookingType.TIME_WINDOW,
        time_window_hours=3,
        active=True
    )
    session.add(test_service)
    session.commit()
    
    # Create test addons
    addon1 = ServiceAddon(
        club_id=test_club.id,
        service_id=test_service.id,
        name="Пакет шаров",
        unit_price=500.0,
        unit_shots=500,
        unit_label="пакет",
        active=True
    )
    addon2 = ServiceAddon(
        club_id=test_club.id,
        service_id=test_service.id,
        name="Коробка шаров",
        unit_price=2000.0,
        unit_shots=2000,
        unit_label="коробка",
        active=True
    )
    session.add_all([addon1, addon2])
    session.commit()
    
    # Create participation pricing
    pricing1 = ParticipationPricing(
        club_id=test_club.id,
        service_code='paintball',
        base_price=300.0,
        max_players=100,
        active=True
    )
    pricing2 = ParticipationPricing(
        club_id=test_club.id,
        service_code='lasertag',
        base_price=300.0,
        additional_hour_price=200.0,
        max_players=100,
        active=True
    )
    session.add_all([pricing1, pricing2])
    session.commit()
    
    yield session
    session.close()


@pytest.fixture
def mock_update():
    """Create a mock Update object"""
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 12345
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.effective_user.username = "testuser"
    
    update.effective_chat = Mock(spec=Chat)
    update.effective_chat.id = 12345
    update.effective_chat.type = "private"
    
    update.message = Mock(spec=Message)
    update.message.chat = update.effective_chat
    update.message.from_user = update.effective_user
    
    return update


@pytest.fixture
def mock_callback_query():
    """Create a mock CallbackQuery object"""
    query = Mock(spec=CallbackQuery)
    query.data = "test_callback"
    query.from_user = Mock(spec=User)
    query.from_user.id = 12345
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = Mock(spec=Message)
    query.message.edit_text = AsyncMock()
    
    return query


@pytest.fixture
def mock_context():
    """Create a mock Context object"""
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    context.bot = Mock()
    context.bot.send_message = AsyncMock()
    context.bot.send_chat_action = AsyncMock()
    
    return context


@pytest.fixture
def mock_update_with_callback(mock_update, mock_callback_query):
    """Create a mock Update with CallbackQuery"""
    mock_update.callback_query = mock_callback_query
    return mock_update


@pytest.fixture
def sample_service_data():
    """Sample service data for testing"""
    return {
        'name': 'Test Paintball',
        'description': 'Test paintball service',
        'price': 1000.0,
        'duration_hours': 3,
        'booking_type': 'TIME_WINDOW',
        'max_players': 20,
        'active': True
    }


@pytest.fixture
def sample_addon_data():
    """Sample addon data for testing"""
    return {
        'name': 'Test Paintballs',
        'unit_price': 500.0,
        'unit_shots': 500,
        'unit_label': 'пакет',
        'active': True
    }
