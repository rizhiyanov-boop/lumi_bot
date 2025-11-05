"""Детальная отладка кнопки Забронировать"""
import asyncio
from unittest.mock import Mock, AsyncMock, patch

async def debug_calc_book():
    """Детальная отладка calc_book"""
    
    print("=== ОТЛАДКА КНОПКИ ЗАБРОНИРОВАТЬ ===")
    
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
    
    print("1. Данные калькулятора:")
    print(f"   calc_service: {mock_context.user_data['calc_service']}")
    print(f"   calc_players: {mock_context.user_data['calc_players']}")
    print(f"   calc_addons: {mock_context.user_data['calc_addons']}")
    
    # Импортируем функции
    from bot.handlers.calculator import calc_book, _calc_summary
    from bot.handlers.booking import start_booking, show_locations_menu, select_field
    
    print("\n2. Тестируем _calc_summary...")
    try:
        summary = _calc_summary(3, {}, 'paintball', 0)
        print(f"   Результат: {summary}")
    except Exception as e:
        print(f"   ОШИБКА в _calc_summary: {e}")
        return
    
    print("\n3. Тестируем calc_book...")
    try:
        # Мокаем start_booking
        with patch('bot.handlers.booking.start_booking', new_callable=AsyncMock) as mock_start_booking:
            await calc_book(mock_update, mock_context)
            
            print("   calc_book выполнен успешно")
            print(f"   booking_from_calc: {mock_context.user_data.get('booking_from_calc')}")
            print(f"   calc_summary: {mock_context.user_data.get('calc_summary')}")
            
            # Проверяем, что start_booking был вызван
            if mock_start_booking.called:
                print("   start_booking был вызван")
            else:
                print("   ОШИБКА: start_booking НЕ был вызван!")
                
    except Exception as e:
        print(f"   ОШИБКА в calc_book: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n4. Тестируем start_booking...")
    try:
        # Сбрасываем моки
        mock_query.answer.reset_mock()
        mock_query.message.edit_text.reset_mock()
        
        # Мокаем show_locations_menu
        with patch('bot.handlers.booking.show_locations_menu', new_callable=AsyncMock) as mock_show_locations:
            await start_booking(mock_update, mock_context)
            
            print("   start_booking выполнен успешно")
            
            if mock_show_locations.called:
                print("   show_locations_menu был вызван")
            else:
                print("   ОШИБКА: show_locations_menu НЕ был вызван!")
                
    except Exception as e:
        print(f"   ОШИБКА в start_booking: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n5. Тестируем show_locations_menu...")
    try:
        # Сбрасываем моки
        mock_query.answer.reset_mock()
        mock_query.message.edit_text.reset_mock()
        
        # Мокаем select_field
        with patch('bot.handlers.booking.select_field', new_callable=AsyncMock) as mock_select_field:
            await show_locations_menu(mock_update, mock_context)
            
            print("   show_locations_menu выполнен успешно")
            
            if mock_select_field.called:
                print("   select_field был вызван")
            else:
                print("   ОШИБКА: select_field НЕ был вызван!")
                
    except Exception as e:
        print(f"   ОШИБКА в show_locations_menu: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n=== ОТЛАДКА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    asyncio.run(debug_calc_book())
