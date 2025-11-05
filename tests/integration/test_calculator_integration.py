"""Integration tests for calculator with database"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from bot.handlers.calculator import _calc_summary
from bot.database.models import Service, ServiceAddon, Club, ParticipationPricing


class TestCalculatorDatabaseIntegration:
    """Test calculator integration with database"""
    
    def test_calculator_with_real_database_data(self, test_db):
        """Test calculator with real database data"""
        # Create test club
        club = Club(name="Test Club", address="Test Address")
        test_db.add(club)
        test_db.commit()
        
        # Create test service
        service = Service(
            club_id=club.id,
            name="Test Paintball",
            description="Test paintball service",
            price=1000.0,
            duration_hours=3,
            booking_type=Service.BookingType.TIME_WINDOW,
            time_window_hours=3,
            max_players=20,
            active=True
        )
        test_db.add(service)
        test_db.commit()
        
        # Create test addons
        addon1 = ServiceAddon(
            service_id=service.id,
            name="Paintballs Pack",
            unit_price=500.0,
            unit_shots=500,
            unit_label="пакет",
            active=True
        )
        addon2 = ServiceAddon(
            service_id=service.id,
            name="Paintballs Box",
            unit_price=2000.0,
            unit_shots=2000,
            unit_label="коробка",
            active=True
        )
        test_db.add_all([addon1, addon2])
        test_db.commit()
        
        # Create participation pricing
        pricing = ParticipationPricing(
            club_id=club.id,
            service_code='paintball',
            base_price=300.0,
            max_players=100,
            active=True
        )
        test_db.add(pricing)
        test_db.commit()
        
        # Test calculation with real data
        players = 5
        selections = {
            addon1.id: {'qty': 2, 'unit_price': 500.0, 'unit_shots': 500},
            addon2.id: {'qty': 1, 'unit_price': 2000.0, 'unit_shots': 2000}
        }
        
        # Mock the database session in calculator
        with patch('bot.handlers.calculator.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=test_db)
            mock_session.__exit__ = Mock(return_value=None)
            mock_get_session.return_value = mock_session
            
            result = _calc_summary(players, selections, 'paintball')
            
            # Verify calculations
            assert result['participation_cost'] == 1500  # 5 * 300
            assert result['addons_cost'] == 3000  # 2*500 + 1*2000
            assert result['total_price'] == 4500  # 1500 + 3000
            assert result['price_per_player'] == 900  # 4500 / 5
            assert result['shots_per_player'] == 600  # (2*500 + 1*2000) / 5
    
    def test_calculator_with_lasertag_pricing(self, test_db):
        """Test calculator with lasertag pricing from database"""
        # Create test club
        club = Club(name="Test Club", address="Test Address")
        test_db.add(club)
        test_db.commit()
        
        # Create lasertag pricing
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
        
        # Test lasertag calculation
        players = 4
        selections = {}
        duration_hours = 3
        
        with patch('bot.handlers.calculator.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=test_db)
            mock_session.__exit__ = Mock(return_value=None)
            mock_get_session.return_value = mock_session
            
            result = _calc_summary(players, selections, 'lasertag', duration_hours)
            
            # Verify lasertag pricing: 4 * (300 + 2*200) = 4 * 700 = 2800
            assert result['participation_cost'] == 2800
            assert result['total_price'] == 2800
            assert result['price_per_player'] == 700
    
    def test_calculator_fallback_when_no_pricing(self, test_db):
        """Test calculator fallback when no pricing in database"""
        # Create test club but no pricing
        club = Club(name="Test Club", address="Test Address")
        test_db.add(club)
        test_db.commit()
        
        players = 3
        selections = {}
        
        with patch('bot.handlers.calculator.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=test_db)
            mock_session.__exit__ = Mock(return_value=None)
            mock_get_session.return_value = mock_session
            
            result = _calc_summary(players, selections, 'paintball')
            
            # Should use fallback pricing
            assert result['participation_cost'] == 900  # 3 * 300 (fallback)
            assert result['total_price'] == 900
            assert result['price_per_player'] == 300
