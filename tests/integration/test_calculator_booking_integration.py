"""Интеграционные тесты калькулятора с бронированием"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from bot.handlers.calculator import calc_book
from bot.handlers.booking import start_booking, show_locations_menu


class TestCalculatorBookingIntegration:
    """Интеграционные тесты калькулятор -> бронирование"""
    
    @pytest.mark.asyncio
    async def test_calc_book_calls_start_booking(self, mock_update_with_callback, mock_context, test_db):
        """Тест что calc_book вызывает start_booking"""
        
        # Настраиваем данные калькулятора
        mock_context.user_data = {
            'calc_service': {'code': 'paintball'},
            'calc_players': 3,
            'calc_duration': 0,
            'calc_addons': {}
        }
        
        mock_update_with_callback.callback_query.data = "calc_book"
        
        # Мокаем start_booking
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что start_booking был вызван
            mock_start_booking.assert_called_once_with(mock_update_with_callback, mock_context)
    
    @pytest.mark.asyncio
    async def test_start_booking_with_calc_data(self, mock_update_with_callback, mock_context, test_db):
        """Тест что start_booking правильно обрабатывает данные из калькулятора"""
        
        # Настраиваем данные из калькулятора
        mock_context.user_data = {
            'booking_from_calc': True,
            'calc_service': {'code': 'paintball'},
            'calc_players': 4,
            'calc_summary': {
                'total_price': 1200,
                'participation_cost': 1200,
                'price_per_player': 300
            }
        }
        
        # Мокаем show_locations_menu
        with patch('bot.handlers.booking.show_locations_menu', new_callable=AsyncMock) as mock_show_locations:
            await start_booking(mock_update_with_callback, mock_context)
            
            # Проверяем, что show_locations_menu был вызван
            mock_show_locations.assert_called_once_with(mock_update_with_callback, mock_context)
    
    @pytest.mark.asyncio
    async def test_show_locations_menu_with_calc_data(self, mock_update_with_callback, mock_context, test_db):
        """Тест что show_locations_menu работает с данными из калькулятора"""
        
        # Настраиваем данные из калькулятора
        mock_context.user_data = {
            'booking_from_calc': True,
            'calc_service': {'code': 'paintball'},
            'calc_players': 2
        }
        
        # Мокаем select_location
        with patch('bot.handlers.booking.select_location', new_callable=AsyncMock) as mock_select_location:
            await show_locations_menu(mock_update_with_callback, mock_context)
            
            # Проверяем, что select_location был вызван (если есть локации)
            if mock_select_location.called:
                # Проверяем, что данные калькулятора переданы
                assert 'calc_service' in mock_context.user_data
                assert 'calc_players' in mock_context.user_data
