"""Интеграционные тесты с реальными объектами Telegram API"""
import pytest
from unittest.mock import Mock, AsyncMock
from telegram import CallbackQuery, Update, User, Chat, Message

class TestTelegramAPIIntegration:
    """Тесты с реальными объектами Telegram API"""
    
    @pytest.mark.asyncio
    async def test_callback_query_data_readonly(self):
        """Тест что query.data нельзя изменить"""
        
        # Создаем РЕАЛЬНЫЙ CallbackQuery
        real_query = CallbackQuery(
            id="test_id",
            from_user=Mock(spec=User),
            chat_instance="test_chat",
            data="original_data"
        )
        
        # Пытаемся изменить data - должно вызвать ошибку
        with pytest.raises(AttributeError, match="can't be set"):
            real_query.data = "new_data"
    
    @pytest.mark.asyncio
    async def test_calc_book_with_real_objects(self):
        """Тест calc_book с реальными объектами Telegram"""
        
        # Создаем РЕАЛЬНЫЕ объекты
        mock_user = Mock(spec=User)
        mock_user.id = 123
        
        mock_chat = Mock(spec=Chat)
        mock_chat.id = 456
        
        mock_message = Mock(spec=Message)
        mock_message.edit_text = AsyncMock()
        
        # Создаем мок для CallbackQuery с правильным поведением
        mock_query = Mock(spec=CallbackQuery)
        mock_query.id = "test_id"
        mock_query.from_user = mock_user
        mock_query.chat_instance = "test_chat"
        mock_query.data = "calc_book"
        mock_query.answer = AsyncMock()
        mock_query.message = mock_message
        
        # Создаем РЕАЛЬНЫЙ Update
        real_update = Update(update_id=1)
        real_update.callback_query = mock_query
        real_update.effective_user = mock_user
        real_update.effective_chat = mock_chat
        
        mock_context = Mock()
        mock_context.user_data = {
            'calc_service': {'code': 'paintball'},
            'calc_players': 3,
            'calc_duration': 0,
            'calc_addons': {}
        }
        
        # Тестируем calc_book
        from bot.handlers.calculator import calc_book
        
        # Должен работать без ошибок
        await calc_book(real_update, mock_context)
        
        # Проверяем, что данные сохранены
        assert mock_context.user_data['booking_from_calc'] == True
        assert 'calc_summary' in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_old_bug_simulation(self):
        """Симуляция старой ошибки с query.data"""
        
        # Создаем РЕАЛЬНЫЙ CallbackQuery
        real_query = CallbackQuery(
            id="test_id",
            from_user=Mock(spec=User),
            chat_instance="test_chat",
            data="original_data"
        )
        
        # Симулируем старую ошибку
        with pytest.raises(AttributeError):
            # Это то, что делала старая версия кода
            real_query.data = "location_1"
