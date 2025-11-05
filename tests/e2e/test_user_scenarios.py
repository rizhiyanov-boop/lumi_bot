"""Автоматические тесты всех пользовательских сценариев"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from bot.handlers.calculator import (
    calc_start, calc_select_service, calc_players_inc, 
    calc_duration_inc, calc_to_addons, calc_add, calc_book
)


class TestUserScenarios:
    """Тесты всех пользовательских сценариев"""
    
    @pytest.mark.asyncio
    async def test_scenario_1_paintball_booking(self, mock_update_with_callback, mock_context, test_db):
        """Сценарий 1: Пейнтбол -> 5 игроков -> бронирование"""
        
        # Шаг 1: Начинаем калькулятор
        mock_update_with_callback.callback_query.data = "calc_start"
        await calc_start(mock_update_with_callback, mock_context)
        
        # Шаг 2: Выбираем пейнтбол
        mock_update_with_callback.callback_query.data = "calc_service_paintball"
        mock_context.user_data = {}
        await calc_select_service(mock_update_with_callback, mock_context)
        
        # Проверяем данные
        assert mock_context.user_data['calc_service']['code'] == 'paintball'
        assert mock_context.user_data['calc_players'] == 1
        
        # Шаг 3: Увеличиваем игроков до 5
        for _ in range(4):
            mock_update_with_callback.callback_query.data = "calc_players_inc"
            await calc_players_inc(mock_update_with_callback, mock_context)
        
        assert mock_context.user_data['calc_players'] == 5
        
        # Шаг 4: Переходим к доп. услугам
        mock_update_with_callback.callback_query.data = "calc_to_addons"
        await calc_to_addons(mock_update_with_callback, mock_context)
        
        # Проверяем, что показаны доп. услуги
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Выберите доп. услуги" in call_args[0][0]
        assert "Игроков: 5" in call_args[0][0]
        
        # Шаг 5: Бронируем
        mock_update_with_callback.callback_query.data = "calc_book"
        
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что бронирование началось
            mock_start_booking.assert_called_once()
            assert mock_context.user_data['booking_from_calc'] == True
            assert 'calc_summary' in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_scenario_2_lasertag_booking(self, mock_update_with_callback, mock_context, test_db):
        """Сценарий 2: Лазертаг -> 3 игрока -> 2 часа -> бронирование"""
        
        # Шаг 1: Выбираем лазертаг
        mock_update_with_callback.callback_query.data = "calc_service_lasertag"
        mock_context.user_data = {}
        await calc_select_service(mock_update_with_callback, mock_context)
        
        # Проверяем данные
        assert mock_context.user_data['calc_service']['code'] == 'lasertag'
        assert mock_context.user_data['calc_duration'] == 1
        
        # Шаг 2: Увеличиваем игроков до 3
        for _ in range(2):
            mock_update_with_callback.callback_query.data = "calc_players_inc"
            await calc_players_inc(mock_update_with_callback, mock_context)
        
        assert mock_context.user_data['calc_players'] == 3
        
        # Шаг 3: Увеличиваем длительность до 2 часов
        mock_update_with_callback.callback_query.data = "calc_duration_inc"
        await calc_duration_inc(mock_update_with_callback, mock_context)
        
        assert mock_context.user_data['calc_duration'] == 2
        
        # Шаг 4: Переходим к доп. услугам
        mock_update_with_callback.callback_query.data = "calc_to_addons"
        await calc_to_addons(mock_update_with_callback, mock_context)
        
        # Проверяем, что показана длительность
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Длительность: 2 часа" in call_args[0][0]
        
        # Шаг 5: Бронируем
        mock_update_with_callback.callback_query.data = "calc_book"
        
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что бронирование началось с правильными данными
            mock_start_booking.assert_called_once()
            assert mock_context.user_data['booking_from_calc'] == True
            assert mock_context.user_data['calc_duration_hours'] == 2
    
    @pytest.mark.asyncio
    async def test_scenario_3_paintball_with_addons(self, mock_update_with_callback, mock_context, test_db):
        """Сценарий 3: Пейнтбол -> 4 игрока -> добавляем допы -> бронирование"""
        
        # Настраиваем данные
        mock_context.user_data = {
            'calc_service': {'code': 'paintball'},
            'calc_players': 4,
            'calc_addons': {}
        }
        
        # Переходим к доп. услугам
        mock_update_with_callback.callback_query.data = "calc_to_addons"
        await calc_to_addons(mock_update_with_callback, mock_context)
        
        # Проверяем, что показаны доп. услуги
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Выберите доп. услуги" in call_args[0][0]
        
        # Проверяем, что есть кнопки для добавления допов
        keyboard = call_args[1]['reply_markup']
        button_texts = []
        for row in keyboard.inline_keyboard:
            for button in row:
                button_texts.append(button.text)
        
        # Должны быть кнопки с допами и кнопка "Забронировать"
        assert "🎯 Забронировать" in button_texts
        
        # Бронируем
        mock_update_with_callback.callback_query.data = "calc_book"
        
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что бронирование началось
            mock_start_booking.assert_called_once()
            assert mock_context.user_data['booking_from_calc'] == True
    
    @pytest.mark.asyncio
    async def test_scenario_4_error_handling(self, mock_update_with_callback, mock_context, test_db):
        """Сценарий 4: Обработка ошибок"""
        
        # Тест с пустыми данными
        mock_context.user_data = {}
        mock_update_with_callback.callback_query.data = "calc_book"
        
        # Должен работать с дефолтными значениями
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update_with_callback, mock_context)
            
            # Проверяем, что бронирование началось с дефолтными данными
            mock_start_booking.assert_called_once()
            assert mock_context.user_data['booking_from_calc'] == True
            assert mock_context.user_data['calc_service']['code'] == 'paintball'  # дефолт
            assert mock_context.user_data['calc_players'] == 1  # дефолт
