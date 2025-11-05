"""Unit tests for calculator functionality"""
import pytest
from unittest.mock import Mock, patch

from bot.handlers.calculator import _calc_summary


class TestCalculatorSummary:
    """Test calculator summary calculations"""
    
    def test_paintball_calculation(self):
        """Test paintball cost calculation"""
        players = 5
        selections = {
            1: {'qty': 2, 'unit_price': 500, 'unit_shots': 500},
            2: {'qty': 1, 'unit_price': 2000, 'unit_shots': 2000}
        }
        service_code = 'paintball'
        
        with patch('bot.database.db.get_participation_pricing') as mock_pricing:
            # Mock pricing data
            mock_pricing.return_value = Mock(
                base_price=300,
                additional_hour_price=200,
                max_players=100
            )
            
            result = _calc_summary(players, selections, service_code)
            
            # Check participation cost (5 players * 300 rubles)
            assert result['participation_cost'] == 1500
            
            # Check addons cost (2*500 + 1*2000 = 3000)
            addons_cost = sum(item['qty'] * item['unit_price'] for item in selections.values())
            assert addons_cost == 3000
            
            # Check total cost (1500 + 3000 = 4500)
            assert result['total_price'] == 4500
            
            # Check price per player (4500 / 5 = 900)
            assert result['price_per_player'] == 900
            
            # Check shots per player ((2*500 + 1*2000) / 5 = 600)
            assert result['shots_per_player'] == 600
    
    def test_lasertag_calculation_single_hour(self):
        """Test lasertag cost calculation for single hour"""
        players = 3
        selections = {}
        service_code = 'lasertag'
        duration_hours = 1
        
        with patch('bot.database.db.get_participation_pricing') as mock_pricing:
            mock_pricing.return_value = Mock(
                base_price=300,
                additional_hour_price=200,
                max_players=100
            )
            
            result = _calc_summary(players, selections, service_code, duration_hours)
            
            # Check participation cost (3 players * 300 rubles for 1 hour)
            assert result['participation_cost'] == 900
            
            # Check total cost (900 + 0 = 900)
            assert result['total_price'] == 900
            
            # Check price per player (900 / 3 = 300)
            assert result['price_per_player'] == 300
    
    def test_lasertag_calculation_multiple_hours(self):
        """Test lasertag cost calculation for multiple hours"""
        players = 4
        selections = {}
        service_code = 'lasertag'
        duration_hours = 3
        
        with patch('bot.database.db.get_participation_pricing') as mock_pricing:
            mock_pricing.return_value = Mock(
                base_price=300,
                additional_hour_price=200,
                max_players=100
            )
            
            result = _calc_summary(players, selections, service_code, duration_hours)
            
            # Check participation cost (4 players * (300 + 2*200) = 4 * 700 = 2800)
            assert result['participation_cost'] == 2800
            
            # Check total cost (2800 + 0 = 2800)
            assert result['total_price'] == 2800
            
            # Check price per player (2800 / 4 = 700)
            assert result['price_per_player'] == 700
    
    def test_empty_selections(self):
        """Test calculation with no addon selections"""
        players = 2
        selections = {}
        service_code = 'paintball'
        
        with patch('bot.database.db.get_participation_pricing') as mock_pricing:
            mock_pricing.return_value = Mock(
                base_price=300,
                additional_hour_price=200,
                max_players=100
            )
            
            result = _calc_summary(players, selections, service_code)
            
            # Check participation cost (2 players * 300 rubles)
            assert result['participation_cost'] == 600
            
            # Check addons cost (0)
            addons_cost = sum(item['qty'] * item['unit_price'] for item in selections.values())
            assert addons_cost == 0
            
            # Check total cost (600 + 0 = 600)
            assert result['total_price'] == 600
            
            # Check price per player (600 / 2 = 300)
            assert result['price_per_player'] == 300
    
    def test_fallback_pricing(self):
        """Test fallback to hardcoded prices when DB pricing is not available"""
        players = 2
        selections = {}
        service_code = 'paintball'
        
        with patch('bot.database.db.get_participation_pricing') as mock_pricing:
            # Return None to trigger fallback
            mock_pricing.return_value = None
            
            result = _calc_summary(players, selections, service_code)
            
            # Should use fallback prices
            assert result['participation_cost'] == 600  # 2 * 300
            assert result['total_price'] == 600
            assert result['price_per_player'] == 300
