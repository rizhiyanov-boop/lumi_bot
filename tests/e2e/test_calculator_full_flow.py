"""Полный E2E тест калькулятора с реальной навигацией"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from bot.handlers.calculator import (
    calc_start,
    calc_select_service,
    calc_players_inc,
    calc_to_addons,
    calc_book
)
from bot.handlers.booking import start_booking


class TestCalculatorFullFlow:
    """Полный тест навигации калькулятора с реальными вызовами"""
    
    @pytest.mark.asyncio
    async def test_complete_calculator_to_booking_flow(self, mock_update_with_callback, mock_context, test_db):
        """Полный тест: калькулятор -> выбор игроков -> допы -> бронирование"""
        
        # Настраиваем моки для реальной работы
        mock_context.user_data = {}
        
        # Шаг 1: Начинаем калькулятор
        mock_update_with_callback.callback_query.data = "calc_start"
        await calc_start(mock_update_with_callback, mock_context)
        
        # Проверяем, что показано меню выбора услуги
        assert mock_update_with_callback.callback_query.message.edit_text.called
        
        # Шаг 2: Выбираем пейнтбол
        mock_update_with_callback.callback_query.data = "calc_service_paintball"
        await calc_select_service(mock_update_with_callback, mock_context)
        
        # Проверяем, что данные сохранились
        assert 'calc_service' in mock_context.user_data
        assert mock_context.user_data['calc_service']['code'] == 'paintball'
        assert mock_context.user_data['calc_players'] == 1
        
        # Шаг 3: Увеличиваем количество игроков
        mock_update_with_callback.callback_query.data = "calc_players_inc"
        await calc_players_inc(mock_update_with_callback, mock_context)
        
        # Проверяем, что количество игроков увеличилось
        assert mock_context.user_data['calc_players'] == 2
        
        # Шаг 4: Переходим к выбору доп. услуг
        mock_update_with_callback.callback_query.data = "calc_to_addons"
        await calc_to_addons(mock_update_with_callback, mock_context)
        
        # Проверяем, что перешли к выбору доп. услуг
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Выберите доп. услуги" in call_args[0][0]
        assert "Игроков: 2" in call_args[0][0]
        
        # Проверяем, что есть кнопка "Забронировать"
        keyboard = call_args[1]['reply_markup']
        button_texts = []
        for row in keyboard.inline_keyboard:
            for button in row:
                button_texts.append(button.text)
        
        assert "🎯 Забронировать" in button_texts
        
        # Шаг 5: Нажимаем "Забронировать"
        mock_update_with_callback.callback_query.data = "calc_book"
        
        # Мокаем start_booking чтобы проверить, что он вызывается
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что start_booking был вызван
            mock_start_booking.assert_called_once_with(mock_update_with_callback, mock_context)
            
            # Проверяем, что данные для бронирования сохранены
            assert 'calc_summary' in mock_context.user_data
            assert 'booking_from_calc' in mock_context.user_data
            assert mock_context.user_data['booking_from_calc'] == True
    
    @pytest.mark.asyncio
    async def test_calc_book_saves_correct_data(self, mock_update_with_callback, mock_context, test_db):
        """Тест сохранения данных в calc_book"""
        
        # Настраиваем данные калькулятора
        mock_context.user_data = {
            'calc_service': {'code': 'paintball'},
            'calc_players': 5,
            'calc_duration': 0,
            'calc_addons': {1: {'qty': 2, 'unit_price': 500}}
        }
        
        mock_update_with_callback.callback_query.data = "calc_book"
        
        # Мокаем start_booking
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что данные сохранены правильно
            assert 'calc_summary' in mock_context.user_data
            assert 'booking_from_calc' in mock_context.user_data
            assert mock_context.user_data['booking_from_calc'] == True
            
            # Проверяем, что summary содержит правильные данные
            summary = mock_context.user_data['calc_summary']
            assert 'total_price' in summary
            assert 'participation_cost' in summary
            assert 'price_per_player' in summary
            
            # Проверяем, что start_booking был вызван
            mock_start_booking.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_calc_book_with_lasertag(self, mock_update_with_callback, mock_context, test_db):
        """Тест calc_book для лазертага с длительностью"""
        
        # Настраиваем данные для лазертага
        mock_context.user_data = {
            'calc_service': {'code': 'lasertag'},
            'calc_players': 3,
            'calc_duration': 2,
            'calc_addons': {}
        }
        
        mock_update_with_callback.callback_query.data = "calc_book"
        
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что для лазертага сохранена длительность
            assert 'calc_duration_hours' in mock_context.user_data
            assert mock_context.user_data['calc_duration_hours'] == 2
            
            # Проверяем, что start_booking был вызван
            mock_start_booking.assert_called_once()
