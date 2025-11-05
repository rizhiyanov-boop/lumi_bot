"""Реалистичные E2E тесты для калькулятора"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from bot.handlers.calculator import (
    calc_start,
    calc_select_service,
    calc_players_inc,
    calc_to_addons
)


class TestCalculatorRealFlow:
    """Реалистичные тесты навигации калькулятора"""
    
    @pytest.mark.asyncio
    async def test_calculator_navigation_flow(self, mock_update_with_callback, mock_context, test_db):
        """Тест реальной навигации по калькулятору"""
        
        # Шаг 1: Начинаем калькулятор
        mock_update_with_callback.callback_query.data = "calc_start"
        await calc_start(mock_update_with_callback, mock_context)
        
        # Проверяем, что показано меню выбора услуги
        mock_update_with_callback.callback_query.message.edit_text.assert_called()
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Выберите услугу" in call_args[0][0] or "Пейнтбол" in call_args[0][0]
        
        # Шаг 2: Выбираем пейнтбол
        mock_update_with_callback.callback_query.data = "calc_service_paintball"
        mock_context.user_data = {}  # Сбрасываем данные
        await calc_select_service(mock_update_with_callback, mock_context)
        
        # Проверяем, что перешли к выбору игроков
        assert 'calc_service' in mock_context.user_data
        assert mock_context.user_data['calc_service']['code'] == 'paintball'
        assert mock_context.user_data['calc_players'] == 1
        
        # Проверяем, что показано меню выбора игроков
        mock_update_with_callback.callback_query.message.edit_text.assert_called()
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Игроков:" in call_args[0][0]
        assert "Далее" in call_args[0][0]
        
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
        
        assert "Забронировать" in button_texts or "🎯 Забронировать" in button_texts
    
    @pytest.mark.asyncio
    async def test_calculator_lasertag_flow(self, mock_update_with_callback, mock_context, test_db):
        """Тест навигации для лазертага"""
        
        # Шаг 1: Выбираем лазертаг
        mock_update_with_callback.callback_query.data = "calc_service_lasertag"
        mock_context.user_data = {}
        await calc_select_service(mock_update_with_callback, mock_context)
        
        # Проверяем, что перешли к выбору игроков и длительности
        assert mock_context.user_data['calc_service']['code'] == 'lasertag'
        assert mock_context.user_data['calc_duration'] == 1
        
        # Шаг 2: Переходим к доп. услугам
        mock_update_with_callback.callback_query.data = "calc_to_addons"
        await calc_to_addons(mock_update_with_callback, mock_context)
        
        # Проверяем, что показана информация о длительности
        call_args = mock_update_with_callback.callback_query.message.edit_text.call_args
        assert "Длительность:" in call_args[0][0]
        assert "час" in call_args[0][0]
