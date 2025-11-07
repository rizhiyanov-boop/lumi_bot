"""Модели базы данных"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, 
    DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class City(Base):
    """Справочник городов с названиями на трех языках"""
    __tablename__ = 'cities'
    id = Column(Integer, primary_key=True)
    name_ru = Column(String(100), nullable=False)  # Название на русском
    name_local = Column(String(100), nullable=False)  # Название на местном языке
    name_en = Column(String(100), nullable=False)  # Название на английском
    latitude = Column(Float, nullable=True)  # Широта (для поиска)
    longitude = Column(Float, nullable=True)  # Долгота (для поиска)
    country_code = Column(String(2), nullable=True)  # Код страны (RU, BY, KZ и т.д.)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    masters = relationship('MasterAccount', back_populates='city')


class CountryCurrency(Base):
    """Кэш маппинга стран на валюты"""
    __tablename__ = 'country_currencies'
    id = Column(Integer, primary_key=True)
    country_code = Column(String(2), unique=True, nullable=False)  # Код страны (ISO 3166-1 alpha-2)
    currency_code = Column(String(3), nullable=False)  # Код валюты (ISO 4217)
    currency_name = Column(String(100), nullable=True)  # Название валюты
    currency_symbol = Column(String(10), nullable=True)  # Символ валюты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MasterAccount(Base):
    __tablename__ = 'master_accounts'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)  # Telegram user id мастера (основной)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    avatar_url = Column(String(255))  # ссылается на Telegram (или future upload)
    city_id = Column(Integer, ForeignKey('cities.id'), nullable=True)  # Город мастера
    currency = Column(String(3), default='RUB')  # Валюта мастера (RUB, BYN, KZT и т.д.)
    created_at = Column(DateTime, default=datetime.utcnow)
    # multi-master — резервируем поле для будущих мастеров
    extra_masters_json = Column(Text, default=None)  # json c информацией о нескольких мастерах внутри аккаунта
    # Подписка и блокировка
    subscription_level = Column(String(20), default='free')  # free, basic, premium
    subscription_expires_at = Column(DateTime, nullable=True)
    is_blocked = Column(Boolean, default=False)
    blocked_at = Column(DateTime, nullable=True)
    block_reason = Column(Text, nullable=True)  # Причина блокировки (для админа)

    services = relationship('Service', back_populates='master_account', cascade="all, delete-orphan")
    work_periods = relationship('WorkPeriod', back_populates='master_account', cascade="all, delete-orphan")
    bookings = relationship('Booking', back_populates='master_account', cascade="all, delete-orphan")
    user_links = relationship('UserMaster', back_populates='master_account', cascade="all, delete-orphan")
    city = relationship('City', back_populates='masters')

class ServiceCategory(Base):
    __tablename__ = 'service_categories'
    id = Column(Integer, primary_key=True)
    master_account_id = Column(Integer, ForeignKey('master_accounts.id'), nullable=False)
    title = Column(String(100), nullable=False)
    emoji = Column(String(10), nullable=True)  # Эмодзи категории
    is_predefined = Column(Boolean, default=False)  # Флаг предустановленной категории
    category_key = Column(String(50), nullable=True)  # Ключ предустановленной категории (nails, hair, etc.)
    services = relationship('Service', back_populates='category')

class Service(Base):
    __tablename__ = 'services'
    id = Column(Integer, primary_key=True)
    master_account_id = Column(Integer, ForeignKey('master_accounts.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('service_categories.id'), nullable=True)
    title = Column(String(100), nullable=False)
    description = Column(Text)
    description_ai_generated = Column(Boolean, default=False)  # Флаг: было ли описание сгенерировано через ИИ
    price = Column(Float, nullable=False)
    duration_mins = Column(Integer, nullable=False)
    cooling_period_mins = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    master_account = relationship('MasterAccount', back_populates='services')
    category = relationship('ServiceCategory', back_populates='services')
    portfolio_photos = relationship('Portfolio', back_populates='service', cascade="all, delete-orphan", order_by='Portfolio.order_index')

class WorkPeriod(Base):
    __tablename__ = 'work_periods'
    id = Column(Integer, primary_key=True)
    master_account_id = Column(Integer, ForeignKey('master_accounts.id'), nullable=False)
    weekday = Column(Integer, nullable=False)  # понедельник=0, воскресенье=6
    start_time = Column(String(5), nullable=False)  # "09:00"
    end_time = Column(String(5), nullable=False)    # "18:00"
    created_at = Column(DateTime, default=datetime.utcnow)

    master_account = relationship('MasterAccount', back_populates='work_periods')

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    bookings = relationship('Booking', back_populates='user', cascade="all, delete-orphan")
    master_links = relationship('UserMaster', back_populates='user', cascade="all, delete-orphan")

class UserMaster(Base):
    __tablename__ = 'user_master_links'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    master_account_id = Column(Integer, ForeignKey('master_accounts.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship('User', back_populates='master_links')
    master_account = relationship('MasterAccount', back_populates='user_links')

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    master_account_id = Column(Integer, ForeignKey('master_accounts.id'), nullable=False)
    service_id = Column(Integer, ForeignKey('services.id'), nullable=False)
    start_dt = Column(DateTime, nullable=False)
    end_dt = Column(DateTime, nullable=False)
    price = Column(Float, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship('User', back_populates='bookings')
    master_account = relationship('MasterAccount', back_populates='bookings')
    service = relationship('Service')


class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
    master_account_id = Column(Integer, ForeignKey('master_accounts.id'), nullable=False)
    payment_id = Column(String(100), unique=True, nullable=False)  # ID платежа от ЮKassa
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default='RUB')
    status = Column(String(20), nullable=False)  # pending, succeeded, canceled
    subscription_type = Column(String(20), nullable=False)  # premium, basic, etc.
    confirmation_url = Column(String(500))  # URL для перенаправления пользователя
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Срок действия подписки после оплаты

    master_account = relationship('MasterAccount')


class Portfolio(Base):
    __tablename__ = 'portfolio'
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey('services.id'), nullable=False)  # Привязка к услуге
    file_id = Column(String(255), nullable=False)  # file_id фото в Telegram
    caption = Column(Text, nullable=True)  # Подпись к фото
    order_index = Column(Integer, default=0)  # Порядок отображения
    created_at = Column(DateTime, default=datetime.utcnow)

    service = relationship('Service', back_populates='portfolio_photos')

