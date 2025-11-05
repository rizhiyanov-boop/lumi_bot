"""Тест calc_book с реальной базой данных"""
import asyncio
from unittest.mock import Mock, AsyncMock

async def test_real_calc_book():
    """Тест calc_book с реальной БД"""
    
    print("=== ТЕСТ С РЕАЛЬНОЙ БД ===")
    
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
    
    print("1. Тестируем calc_book с реальной БД...")
    
    try:
        from bot.handlers.calculator import calc_book
        
        # НЕ мокаем start_booking - используем реальную функцию
        await calc_book(mock_update, mock_context)
        
        print("   calc_book выполнен успешно")
        print(f"   booking_from_calc: {mock_context.user_data.get('booking_from_calc')}")
        print(f"   calc_summary: {mock_context.user_data.get('calc_summary')}")
        
        # Проверяем, что сообщение было обновлено
        if mock_query.message.edit_text.called:
            print("   Сообщение было обновлено")
            call_args = mock_query.message.edit_text.call_args
            text = call_args[0][0]
            # Безопасный вывод текста
            safe_text = text.encode('ascii', 'ignore').decode('ascii')
            print(f"   Текст: {safe_text[:100]}...")
        else:
            print("   ОШИБКА: Сообщение НЕ было обновлено!")
            
    except Exception as e:
        print(f"   ОШИБКА в calc_book: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n=== ТЕСТ ЗАВЕРШЕН ===")

if __name__ == "__main__":
    asyncio.run(test_real_calc_book())
