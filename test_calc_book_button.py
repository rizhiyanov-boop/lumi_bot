"""Тест кнопки Забронировать в калькуляторе"""
import asyncio
from unittest.mock import Mock, AsyncMock

from bot.handlers.calculator import calc_book
from bot.handlers.booking import start_booking, show_locations_menu, select_field

async def test_calc_book_button():
    """Тест что кнопка Забронировать работает"""
    
    # Создаем моки
    mock_query = AsyncMock()
    mock_query.answer = AsyncMock()
    mock_query.message = Mock()
    mock_query.message.edit_text = AsyncMock()
    
    mock_update = Mock()
    mock_update.callback_query = mock_query
    mock_update.effective_user = Mock()
    mock_update.effective_user.id = 123
    
    mock_context = Mock()
    mock_context.user_data = {
        'calc_service': {'code': 'paintball'},
        'calc_players': 3,
        'calc_duration': 0,
        'calc_addons': {}
    }
    
    # Мокаем функции бронирования
    import bot.handlers.calculator
    import bot.handlers.booking
    
    original_start_booking = bot.handlers.booking.start_booking
    original_show_locations_menu = bot.handlers.booking.show_locations_menu
    original_select_field = bot.handlers.booking.select_field
    
    bot.handlers.booking.start_booking = AsyncMock()
    bot.handlers.booking.show_locations_menu = AsyncMock()
    bot.handlers.booking.select_field = AsyncMock()
    
    try:
        # Тестируем calc_book
        await calc_book(mock_update, mock_context)
        
        # Проверяем, что start_booking был вызван
        bot.handlers.booking.start_booking.assert_called_once_with(mock_update, mock_context)
        
        # Проверяем, что данные сохранены
        assert mock_context.user_data['booking_from_calc'] == True
        assert 'calc_summary' in mock_context.user_data
        
        print("OK calc_book работает правильно!")
        
    finally:
        # Восстанавливаем оригинальные функции
        bot.handlers.booking.start_booking = original_start_booking
        bot.handlers.booking.show_locations_menu = original_show_locations_menu
        bot.handlers.booking.select_field = original_select_field

if __name__ == "__main__":
    asyncio.run(test_calc_book_button())
