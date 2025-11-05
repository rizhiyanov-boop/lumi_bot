"""Симуляция старой ошибки с query.data"""
import asyncio
from unittest.mock import Mock, AsyncMock
from telegram import CallbackQuery, Update, User, Chat, Message

async def test_simulate_old_error():
    """Симуляция старой ошибки"""
    
    print("=== СИМУЛЯЦИЯ СТАРОЙ ОШИБКИ ===")
    
    # Создаем РЕАЛЬНЫЙ CallbackQuery
    mock_query = Mock(spec=CallbackQuery)
    mock_query.answer = AsyncMock()
    mock_query.data = "some_data"
    
    print("1. Тестируем изменение query.data...")
    
    try:
        # Пытаемся изменить query.data (как в старой версии)
        mock_query.data = "new_data"
        print("   OK query.data изменен успешно (в моках это работает)")
        
    except Exception as e:
        print(f"   FAIL Ошибка при изменении query.data: {e}")
    
    print("\n2. Тестируем с реальным CallbackQuery...")
    
    try:
        # Создаем реальный CallbackQuery
        real_query = CallbackQuery(
            id="test_id",
            from_user=Mock(spec=User),
            chat_instance="test_chat",
            data="some_data"
        )
        
        # Пытаемся изменить data
        real_query.data = "new_data"
        print("   OK query.data изменен успешно")
        
    except Exception as e:
        print(f"   FAIL Ошибка при изменении query.data: {e}")
        print(f"   Тип ошибки: {type(e).__name__}")
        
        if "can't be set" in str(e):
            print("   FOUND НАЙДЕНА ОШИБКА: AttributeError при изменении query.data")
    
    print("\n=== СИМУЛЯЦИЯ ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    asyncio.run(test_simulate_old_error())
