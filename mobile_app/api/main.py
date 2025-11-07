"""
REST API для Android приложения Lumi Beauty
Использует FastAPI для взаимодействия с базой данных
"""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date, time, timedelta
from bot.database.db import (
    get_session,
    get_or_create_user,
    get_master_by_id,
    get_master_by_telegram,
    get_client_masters,
    get_services_by_master,
    get_bookings_for_client,
    create_booking,
    check_booking_conflict,
    add_user_master_link,
    remove_user_master_link,
    get_all_cities,
    get_masters_by_city,
    get_work_periods,
    get_portfolio_photos
)
from bot.utils.schedule_utils import get_available_time_slots, has_available_slots_on_date
from bot.database.models import Service
from bot.config import DATABASE_URL
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Lumi Beauty API", version="1.0.0")

# CORS для Android приложения
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# Pydantic модели для API
class MasterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    city_name: Optional[str]
    services_count: int
    
    class Config:
        from_attributes = True


class ServiceResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    price: float
    duration_mins: int
    category_name: Optional[str]
    portfolio_photos: List[str] = []
    
    class Config:
        from_attributes = True


class TimeSlotResponse(BaseModel):
    date: str
    time: str
    available: bool


class BookingRequest(BaseModel):
    master_id: int
    service_id: int
    start_datetime: str  # ISO format
    comment: Optional[str] = None


class BookingResponse(BaseModel):
    id: int
    master_name: str
    service_title: str
    start_datetime: str
    end_datetime: str
    price: float
    status: str
    
    class Config:
        from_attributes = True


class CityResponse(BaseModel):
    id: int
    name_ru: str
    name_local: str
    name_en: str
    
    class Config:
        from_attributes = True


# Простая аутентификация через user_id в заголовке
# В продакшене использовать JWT токены
def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Получить user_id из токена (пока просто передаем user_id)"""
    try:
        user_id = int(credentials.credentials)
        return user_id
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


@app.get("/")
async def root():
    return {"message": "Lumi Beauty API", "version": "1.0.0"}


@app.get("/api/masters", response_model=List[MasterResponse])
async def get_masters(user_id: int = Depends(get_user_id)):
    """Получить список мастеров клиента"""
    with get_session() as session:
        user = get_or_create_user(session, user_id)
        masters = get_client_masters(session, user)
        
        result = []
        for master in masters:
            services = get_services_by_master(session, master.id, active_only=True)
            city_name = master.city.name_ru if master.city else None
            
            result.append(MasterResponse(
                id=master.id,
                name=master.name,
                description=master.description,
                avatar_url=master.avatar_url,
                city_name=city_name,
                services_count=len(services)
            ))
        
        return result


class MasterDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    city: Optional[str]
    services: List[ServiceResponse]
    work_schedule: List[dict]
    
    class Config:
        from_attributes = True


@app.get("/api/masters/{master_id}", response_model=MasterDetailResponse)
async def get_master_detail(master_id: int, user_id: int = Depends(get_user_id)):
    """Получить детальную информацию о мастере"""
    with get_session() as session:
        master = get_master_by_id(session, master_id)
        if not master:
            raise HTTPException(status_code=404, detail="Master not found")
        
        services = get_services_by_master(session, master.id, active_only=True)
        work_periods = get_work_periods(session, master.id)
        
        services_list = []
        for service in services:
            portfolio = get_portfolio_photos(session, service.id)
            portfolio_urls = [p.file_id for p in portfolio]  # В продакшене конвертировать в URL
            
            services_list.append(ServiceResponse(
                id=service.id,
                title=service.title,
                description=service.description,
                price=service.price,
                duration_mins=service.duration_mins,
                category_name=service.category.title if service.category else None,
                portfolio_photos=portfolio_urls
            ))
        
        return MasterDetailResponse(
            id=master.id,
            name=master.name,
            description=master.description,
            avatar_url=master.avatar_url,
            city=master.city.name_ru if master.city else None,
            services=services_list,
            work_schedule=[
                {
                    "weekday": wp.weekday,
                    "start_time": wp.start_time,
                    "end_time": wp.end_time
                }
                for wp in work_periods
            ]
        )


@app.get("/api/masters/{master_id}/services/{service_id}/time-slots")
async def get_time_slots(
    master_id: int,
    service_id: int,
    date_from: str,  # YYYY-MM-DD
    date_to: str,    # YYYY-MM-DD
    user_id: int = Depends(get_user_id)
):
    """Получить доступные слоты времени для услуги"""
    with get_session() as session:
        master = get_master_by_id(session, master_id)
        if not master:
            raise HTTPException(status_code=404, detail="Master not found")
        
        service = session.query(Service).filter_by(id=service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Парсим даты
        start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        
        slots = []
        current_date = start_date
        while current_date <= end_date:
            available_slots = get_available_time_slots(
                session, master.id, service.id, current_date
            )
            
            for slot_time in available_slots:
                slots.append(TimeSlotResponse(
                    date=current_date.isoformat(),
                    time=slot_time.strftime("%H:%M"),
                    available=True
                ))
            
            current_date += timedelta(days=1)
        
        return slots


@app.post("/api/bookings", response_model=BookingResponse)
async def create_booking_endpoint(
    booking: BookingRequest,
    user_id: int = Depends(get_user_id)
):
    """Создать бронирование"""
    with get_session() as session:
        user = get_or_create_user(session, user_id)
        master = get_master_by_id(session, booking.master_id)
        
        if not master:
            raise HTTPException(status_code=404, detail="Master not found")
        
        service = session.query(Service).filter_by(id=booking.service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Парсим datetime
        start_dt = datetime.fromisoformat(booking.start_datetime.replace('Z', '+00:00'))
        end_dt = start_dt + timedelta(minutes=service.duration_mins)
        
        # Проверяем конфликты
        if check_booking_conflict(session, master.id, start_dt, end_dt):
            raise HTTPException(
                status_code=400,
                detail="Time slot is already booked"
            )
        
        # Создаем бронирование
        booking_obj = create_booking(
            session,
            user.id,
            master.id,
            service.id,
            start_dt,
            end_dt,
            service.price,
            booking.comment
        )
        
        return BookingResponse(
            id=booking_obj.id,
            master_name=master.name,
            service_title=service.title,
            start_datetime=start_dt.isoformat(),
            end_datetime=end_dt.isoformat(),
            price=booking_obj.price,
            status="confirmed"
        )


@app.get("/api/bookings", response_model=List[BookingResponse])
async def get_bookings(user_id: int = Depends(get_user_id)):
    """Получить список бронирований клиента"""
    with get_session() as session:
        user = get_or_create_user(session, user_id)
        bookings = get_bookings_for_client(session, user.id)
        
        result = []
        for booking in bookings:
            result.append(BookingResponse(
                id=booking.id,
                master_name=booking.master_account.name,
                service_title=booking.service.title,
                start_datetime=booking.start_dt.isoformat(),
                end_datetime=booking.end_dt.isoformat(),
                price=booking.price,
                status="confirmed"  # В продакшене брать из модели
            ))
        
        return result


@app.post("/api/masters/{master_id}/add")
async def add_master(master_id: int, user_id: int = Depends(get_user_id)):
    """Добавить мастера в список клиента"""
    with get_session() as session:
        user = get_or_create_user(session, user_id)
        master = get_master_by_id(session, master_id)
        
        if not master:
            raise HTTPException(status_code=404, detail="Master not found")
        
        link = add_user_master_link(session, user, master)
        return {"success": True, "message": "Master added"}


@app.delete("/api/masters/{master_id}/remove")
async def remove_master(master_id: int, user_id: int = Depends(get_user_id)):
    """Удалить мастера из списка клиента"""
    with get_session() as session:
        user = get_or_create_user(session, user_id)
        master = get_master_by_id(session, master_id)
        
        if not master:
            raise HTTPException(status_code=404, detail="Master not found")
        
        remove_user_master_link(session, user.id, master.id)
        return {"success": True, "message": "Master removed"}


@app.get("/api/cities", response_model=List[CityResponse])
async def get_cities():
    """Получить список городов"""
    with get_session() as session:
        cities = get_all_cities(session)
        return [CityResponse(
            id=city.id,
            name_ru=city.name_ru,
            name_local=city.name_local,
            name_en=city.name_en
        ) for city in cities]


@app.get("/api/cities/{city_id}/masters", response_model=List[MasterResponse])
async def get_city_masters(
    city_id: int,
    user_id: int = Depends(get_user_id)
):
    """Получить мастеров в городе"""
    with get_session() as session:
        masters = get_masters_by_city(session, city_id, exclude_user_id=user_id, active_only=True)
        
        result = []
        for master in masters:
            services = get_services_by_master(session, master.id, active_only=True)
            
            result.append(MasterResponse(
                id=master.id,
                name=master.name,
                description=master.description,
                avatar_url=master.avatar_url,
                city_name=master.city.name_ru if master.city else None,
                services_count=len(services)
            ))
        
        return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

