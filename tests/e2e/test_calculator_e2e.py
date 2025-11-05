"""End-to-end tests for calculator functionality"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from bot.handlers.calculator import (
    calc_start,
    calc_select_service,
    calc_players_inc,
    calc_players_dec,
    calc_duration_inc,
    calc_to_addons,
    calc_add,
    calc_remove,
    calc_book
)


class TestCalculatorE2E:
    """End-to-end tests for calculator user flow"""
    
    @pytest.mark.asyncio
    async def test_complete_calculator_flow_paintball(self, mock_update_with_callback, mock_context, test_db):
        """Test complete calculator flow for paintball"""
        # Setup test data
        club = test_db.query(Club).first()
        if not club:
            club = Club(name="Test Club", address="Test Address")
            test_db.add(club)
            test_db.commit()
        
        # Create paintball service
        service = Service(
            club_id=club.id,
            name="Пейнтбол",
            description="Paintball game",
            price=1000.0,
            duration_hours=3,
            booking_type=Service.BookingType.TIME_WINDOW,
            time_window_hours=3,
            max_players=20,
            active=True
        )
        test_db.add(service)
        test_db.commit()
        
        # Create addons
        addon1 = ServiceAddon(
            service_id=service.id,
            name="Пакет шаров",
            unit_price=500.0,
            unit_shots=500,
            unit_label="пакет",
            active=True
        )
        addon2 = ServiceAddon(
            service_id=service.id,
            name="Коробка шаров",
            unit_price=2000.0,
            unit_shots=2000,
            unit_label="коробка",
            active=True
        )
        test_db.add_all([addon1, addon2])
        test_db.commit()
        
        # Create pricing
        pricing = ParticipationPricing(
            club_id=club.id,
            service_code='paintball',
            base_price=300.0,
            max_players=100,
            active=True
        )
        test_db.add(pricing)
        test_db.commit()
        
        # Mock database calls
        with patch('bot.handlers.calculator.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=test_db)
            mock_session.__exit__ = Mock(return_value=None)
            mock_get_session.return_value = mock_session
            
            # Step 1: Start calculator
            mock_update_with_callback.callback_query.data = "calc_start"
            await calc_start(mock_update_with_callback, mock_context)
            
            # Verify service selection menu was shown
            mock_update_with_callback.callback_query.message.edit_text.assert_called()
            
            # Step 2: Select paintball service
            mock_update_with_callback.callback_query.data = "calc_service_paintball"
            mock_context.user_data = {}  # Reset user data
            await calc_select_service(mock_update_with_callback, mock_context)
            
            # Verify players menu was shown
            assert mock_context.user_data['calc_service']['code'] == 'paintball'
            assert mock_context.user_data['calc_players'] == 1
            
            # Step 3: Increase players to 5
            mock_update_with_callback.callback_query.data = "calc_players_inc"
            await calc_players_inc(mock_update_with_callback, mock_context)
            
            # Verify players count increased
            assert mock_context.user_data['calc_players'] == 2
            
            # Step 4: Go to addons
            mock_update_with_callback.callback_query.data = "calc_to_addons"
            await calc_to_addons(mock_update_with_callback, mock_context)
            
            # Verify addons menu was shown
            mock_update_with_callback.callback_query.message.edit_text.assert_called()
            
            # Step 5: Add some addons
            mock_update_with_callback.callback_query.data = f"calc_add_{addon1.id}"
            await calc_add(mock_update_with_callback, mock_context)
            
            # Verify addon was added
            assert addon1.id in mock_context.user_data['calc_addons']
            assert mock_context.user_data['calc_addons'][addon1.id]['qty'] == 1
            
            # Step 6: Add more addons
            mock_update_with_callback.callback_query.data = f"calc_add_{addon1.id}"
            await calc_add(mock_update_with_callback, mock_context)
            
            # Verify quantity increased
            assert mock_context.user_data['calc_addons'][addon1.id]['qty'] == 2
            
            # Step 7: Try to book
            mock_update_with_callback.callback_query.data = "calc_book"
            await calc_book(mock_update_with_callback, mock_context)
            
            # Verify booking data was prepared
            assert 'calc_summary' in mock_context.user_data
            assert 'booking_from_calc' in mock_context.user_data
            assert mock_context.user_data['booking_from_calc'] == True
    
    @pytest.mark.asyncio
    async def test_calculator_lasertag_flow(self, mock_update_with_callback, mock_context, test_db):
        """Test calculator flow for lasertag with duration selection"""
        # Setup test data
        club = test_db.query(Club).first()
        if not club:
            club = Club(name="Test Club", address="Test Address")
            test_db.add(club)
            test_db.commit()
        
        # Create lasertag service
        service = Service(
            club_id=club.id,
            name="Лазертаг",
            description="Lasertag game",
            price=300.0,
            duration_hours=1,
            booking_type=Service.BookingType.HOURLY,
            time_window_hours=1,
            max_players=15,
            active=True
        )
        test_db.add(service)
        test_db.commit()
        
        # Create pricing
        pricing = ParticipationPricing(
            club_id=club.id,
            service_code='lasertag',
            base_price=300.0,
            additional_hour_price=200.0,
            max_players=100,
            active=True
        )
        test_db.add(pricing)
        test_db.commit()
        
        # Mock database calls
        with patch('bot.handlers.calculator.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=test_db)
            mock_session.__exit__ = Mock(return_value=None)
            mock_get_session.return_value = mock_session
            
            # Select lasertag service
            mock_update_with_callback.callback_query.data = "calc_service_lasertag"
            mock_context.user_data = {}
            await calc_select_service(mock_update_with_callback, mock_context)
            
            # Verify lasertag setup
            assert mock_context.user_data['calc_service']['code'] == 'lasertag'
            assert mock_context.user_data['calc_duration'] == 1
            
            # Increase duration to 3 hours
            mock_update_with_callback.callback_query.data = "calc_duration_inc"
            await calc_duration_inc(mock_update_with_callback, mock_context)
            
            # Verify duration increased
            assert mock_context.user_data['calc_duration'] == 2
            
            # Go to addons (lasertag has no addons in this test)
            mock_update_with_callback.callback_query.data = "calc_to_addons"
            await calc_to_addons(mock_update_with_callback, mock_context)
            
            # Verify addons menu was shown (should be empty for lasertag)
            mock_update_with_callback.callback_query.message.edit_text.assert_called()
            
            # Try to book
            mock_update_with_callback.callback_query.data = "calc_book"
            await calc_book(mock_update_with_callback, mock_context)
            
            # Verify booking data
            assert 'calc_summary' in mock_context.user_data
            assert mock_context.user_data['booking_from_calc'] == True
