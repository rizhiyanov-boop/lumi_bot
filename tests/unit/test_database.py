"""Unit tests for database functionality"""
import pytest
from sqlalchemy.orm import Session

from bot.database.models import Service, ServiceAddon, Club, ParticipationPricing
from bot.database.db import (
    get_services,
    get_addons_by_service,
    get_participation_pricing,
    create_or_update_participation_pricing
)


class TestDatabaseOperations:
    """Test database CRUD operations"""
    
    def test_get_services_by_club(self, test_db):
        """Test getting services by club ID"""
        # Create test club
        club = Club(slug="test-club-1", name="Test Club 1", description="Test club for testing")
        test_db.add(club)
        test_db.commit()
        
        # Create test service
        service = Service(
            club_id=club.id,
            name="Test Service",
            description="Test Description",
            price=1000.0,
            duration_hours=3,
            booking_type=Service.BookingType.TIME_WINDOW,
            active=True
        )
        test_db.add(service)
        test_db.commit()
        
        # Test getting services
        services = get_services(test_db, club.id)
        
        assert len(services) == 1
        assert services[0].name == "Test Service"
        assert services[0].price == 1000.0
    
    def test_get_addons_by_service(self, test_db):
        """Test getting addons by service ID"""
        # Create test club and service
        club = Club(slug="test-club-1", name="Test Club 1", description="Test club for testing")
        test_db.add(club)
        test_db.commit()
        
        service = Service(
            club_id=club.id,
            name="Test Service",
            description="Test Description",
            price=1000.0,
            duration_hours=3,
            booking_type=Service.BookingType.TIME_WINDOW,
            active=True
        )
        test_db.add(service)
        test_db.commit()
        
        # Create test addon
        addon = ServiceAddon(
            club_id=club.id,
            service_id=service.id,
            name="Test Addon",
            unit_price=500.0,
            unit_shots=500,
            unit_label="пакет",
            active=True
        )
        test_db.add(addon)
        test_db.commit()
        
        # Test getting addons
        addons = get_addons_by_service(test_db, service.id)
        
        assert len(addons) == 1
        assert addons[0].name == "Test Addon"
        assert addons[0].unit_price == 500.0
    
    def test_participation_pricing_operations(self, test_db):
        """Test participation pricing CRUD operations"""
        # Use existing club from conftest.py (id=1)
        club_id = 1
        
        # Test creating pricing
        pricing = create_or_update_participation_pricing(
            test_db, club_id, 'paintball', 300.0, None, 50
        )
        
        assert pricing.club_id == club_id
        assert pricing.service_code == 'paintball'
        assert pricing.base_price == 300.0
        assert pricing.max_players == 50
        
        # Test getting pricing
        retrieved_pricing = get_participation_pricing(test_db, club_id, 'paintball')
        
        assert retrieved_pricing is not None
        assert retrieved_pricing.base_price == 300.0
        assert retrieved_pricing.max_players == 50
        
        # Test updating pricing
        updated_pricing = create_or_update_participation_pricing(
            test_db, club_id, 'paintball', 350.0, None, 60
        )
        
        assert updated_pricing.id == pricing.id  # Same record
        assert updated_pricing.base_price == 350.0
        assert updated_pricing.max_players == 60
    
    def test_service_creation_with_booking_types(self, test_db):
        """Test creating services with different booking types"""
        club = Club(slug="test-club-1", name="Test Club 1", description="Test club for testing")
        test_db.add(club)
        test_db.commit()
        
        # Test paintball service (TIME_WINDOW)
        paintball_service = Service(
            club_id=club.id,
            name="Paintball",
            description="Paintball game",
            price=1000.0,
            duration_hours=3,
            booking_type=Service.BookingType.TIME_WINDOW,
            time_window_hours=3,
            active=True
        )
        test_db.add(paintball_service)
        
        # Test lasertag service (HOURLY)
        lasertag_service = Service(
            club_id=club.id,
            name="Lasertag",
            description="Lasertag game",
            price=300.0,
            duration_hours=1,
            booking_type=Service.BookingType.HOURLY,
            time_window_hours=1,
            active=True
        )
        test_db.add(lasertag_service)
        test_db.commit()
        
        # Verify services
        services = get_services(test_db, club.id)
        assert len(services) == 2
        
        paintball = next(s for s in services if s.name == "Paintball")
        lasertag = next(s for s in services if s.name == "Lasertag")
        
        assert paintball.booking_type == Service.BookingType.TIME_WINDOW
        assert lasertag.booking_type == Service.BookingType.HOURLY
        assert paintball.duration_hours == 3
        assert lasertag.duration_hours == 1
