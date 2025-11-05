"""Тест с реальными объектами Telegram API"""
import asyncio
from unittest.mock import Mock, AsyncMock
from telegram import CallbackQuery, Update, User, Chat, Message

async def test_with_real_telegram_objects():
    """Тест с реальными объектами Telegram API"""
    
    print("=== ТЕСТ С РЕАЛЬНЫМИ ОБЪЕКТАМИ TELEGRAM ===")
    
    # Создаем РЕАЛЬНЫЕ объекты Telegram API
    mock_user = Mock(spec=User)
    mock_user.id = 123
    
    mock_chat = Mock(spec=Chat)
    mock_chat.id = 456
    
    mock_message = Mock(spec=Message)
    mock_message.edit_text = AsyncMock()
    
    # Создаем РЕАЛЬНЫЙ CallbackQuery
    mock_query = Mock(spec=CallbackQuery)
    mock_query.answer = AsyncMock()
    mock_query.message = mock_message
    mock_query.data = "calc_book"  # Начальное значение
    
    # Создаем РЕАЛЬНЫЙ Update
    mock_update = Mock(spec=Update)
    mock_update.callback_query = mock_query
    mock_update.effective_user = mock_user
    mock_update.effective_chat = mock_chat
    
    mock_context = Mock()
    mock_context.user_data = {
        'calc_service': {'code': 'paintball'},
        'calc_players': 3,
        'calc_duration': 0,
        'calc_addons': {}
    }
    
    print("1. Тестируем calc_book с реальными объектами...")
    
    try:
        from bot.handlers.calculator import calc_book
        
        # НЕ мокаем start_booking - используем реальную функцию
        await calc_book(mock_update, mock_context)
        
        print("   calc_book выполнен успешно")
        
    except Exception as e:
        print(f"   ОШИБКА в calc_book: {e}")
        print(f"   Тип ошибки: {type(e).__name__}")
        
        # Проверяем, была ли попытка изменить query.data
        if "can't be set" in str(e) and "data" in str(e):
            print("   ✅ НАЙДЕНА ОШИБКА: Попытка изменить read-only атрибут query.data")
        else:
            print("   ❌ Другая ошибка")
        
        import traceback
        traceback.print_exc()
        return
    
    print("\n=== ТЕСТ ЗАВЕРШЕН ===")

if __name__ == "__main__":
    asyncio.run(test_with_real_telegram_objects())
