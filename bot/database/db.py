"""Управление базой данных для Lumi Beauty"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional
import logging

from bot.config import DATABASE_URL, SUPER_ADMINS
from bot.database.models import (
    Base,
    City,
    CountryCurrency,
    MasterAccount,
    ServiceCategory,
    Service,
    WorkPeriod,
    User,
    UserMaster,
    Booking,
    Payment,
    Portfolio
)

logger = logging.getLogger(__name__)


# Создание движка БД
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def migrate_portfolio_table():
    """Миграция таблицы portfolio: замена master_account_id на service_id"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    
    # Проверяем, существует ли таблица portfolio
    if 'portfolio' not in inspector.get_table_names():
        logger.info("Таблица portfolio не существует, будет создана при инициализации.")
        return
    
    columns = [col['name'] for col in inspector.get_columns('portfolio')]
    
    # Проверяем, нужна ли миграция
    has_old_column = 'master_account_id' in columns
    has_new_column = 'service_id' in columns
    
    if has_old_column and not has_new_column:
        logger.info("Выполняется миграция таблицы portfolio...")
        with engine.connect() as conn:
            # Удаляем все старые записи портфолио (так как их нельзя точно привязать к услугам)
            conn.execute(text("DELETE FROM portfolio"))
            conn.commit()
            
            # Удаляем старую колонку и добавляем новую
            # SQLite не поддерживает DROP COLUMN напрямую, нужно пересоздать таблицу
            conn.execute(text("""
                CREATE TABLE portfolio_new (
                    id INTEGER PRIMARY KEY,
                    service_id INTEGER NOT NULL,
                    file_id VARCHAR(255) NOT NULL,
                    caption TEXT,
                    order_index INTEGER DEFAULT 0,
                    created_at DATETIME,
                    FOREIGN KEY(service_id) REFERENCES services(id)
                )
            """))
            
            conn.execute(text("DROP TABLE portfolio"))
            conn.execute(text("ALTER TABLE portfolio_new RENAME TO portfolio"))
            conn.commit()
            
        logger.info("Миграция таблицы portfolio завершена!")
    elif not has_new_column:
        # Если нет ни старой, ни новой колонки, просто создаем таблицу заново
        Base.metadata.create_all(bind=engine, tables=[Portfolio.__table__])
        logger.info("Таблица portfolio создана с новой структурой!")
    else:
        logger.info("Таблица portfolio уже имеет правильную структуру.")


def migrate_city_table():
    """Миграция: добавление поля city_id в master_accounts"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    
    # Проверяем, существует ли таблица master_accounts
    if 'master_accounts' not in inspector.get_table_names():
        logger.info("Таблица master_accounts не существует, будет создана при инициализации.")
        return
    
    columns = [col['name'] for col in inspector.get_columns('master_accounts')]
    
    # Проверяем, нужно ли добавлять поле city_id
    if 'city_id' not in columns:
        logger.info("Выполняется миграция: добавление поля city_id в master_accounts...")
        with engine.connect() as conn:
            # SQLite не поддерживает ADD COLUMN с FOREIGN KEY напрямую в некоторых версиях
            # Используем простой ADD COLUMN
            try:
                conn.execute(text("ALTER TABLE master_accounts ADD COLUMN city_id INTEGER"))
                conn.commit()
                logger.info("Миграция: поле city_id добавлено в master_accounts!")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении city_id: {e}. Возможно, поле уже существует.")
    else:
        logger.info("Поле city_id уже существует в master_accounts.")


def migrate_service_ai_generated():
    """Миграция: добавление поля description_ai_generated в services"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    
    # Проверяем, существует ли таблица services
    if 'services' not in inspector.get_table_names():
        logger.info("Таблица services не существует, будет создана при инициализации.")
        return
    
    columns = [col['name'] for col in inspector.get_columns('services')]
    
    # Проверяем, нужно ли добавлять поле description_ai_generated
    if 'description_ai_generated' not in columns:
        logger.info("Выполняется миграция: добавление поля description_ai_generated в services...")
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE services ADD COLUMN description_ai_generated BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("Миграция: поле description_ai_generated добавлено в services!")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении description_ai_generated: {e}. Возможно, поле уже существует.")
    else:
        logger.info("Поле description_ai_generated уже существует в services.")


def migrate_master_currency():
    """Миграция: добавление поля currency в master_accounts и автоматическое определение валюты"""
    from sqlalchemy import text, inspect
    from bot.utils.currency import get_currency_by_country
    
    inspector = inspect(engine)
    
    # Проверяем, существует ли таблица master_accounts
    if 'master_accounts' not in inspector.get_table_names():
        logger.info("Таблица master_accounts не существует, будет создана при инициализации.")
        return
    
    columns = [col['name'] for col in inspector.get_columns('master_accounts')]
    
    # Проверяем, нужно ли добавлять поле currency
    if 'currency' not in columns:
        logger.info("Выполняется миграция: добавление поля currency в master_accounts...")
        with engine.connect() as conn:
            try:
                # Добавляем поле currency
                conn.execute(text("ALTER TABLE master_accounts ADD COLUMN currency VARCHAR(3) DEFAULT 'RUB'"))
                conn.commit()
                
                # Обновляем валюту для существующих мастеров на основе их города
                # Получаем всех мастеров с городами
                result = conn.execute(text("""
                    SELECT ma.id, c.country_code 
                    FROM master_accounts ma
                    LEFT JOIN cities c ON ma.city_id = c.id
                    WHERE ma.city_id IS NOT NULL
                """))
                
                for row in result:
                    master_id, country_code = row
                    currency = get_currency_by_country(country_code)
                    conn.execute(
                        text("UPDATE master_accounts SET currency = :currency WHERE id = :master_id"),
                        {"currency": currency, "master_id": master_id}
                    )
                
                conn.commit()
                logger.info("Миграция: поле currency добавлено в master_accounts и валюты обновлены!")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении currency: {e}. Возможно, поле уже существует.")
    else:
        logger.info("Поле currency уже существует в master_accounts.")


def migrate_country_currency_table():
    """Миграция: создание таблицы country_currencies"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    
    # Проверяем, существует ли таблица country_currencies
    if 'country_currencies' not in inspector.get_table_names():
        logger.info("Таблица country_currencies не существует, будет создана при инициализации.")
        return
    
    logger.info("Таблица country_currencies уже существует.")


def init_db():
    """Инициализация базы данных"""
    # Сначала выполняем миграции, если нужно
    try:
        migrate_portfolio_table()
        migrate_city_table()
        migrate_service_ai_generated()
        migrate_master_currency()
        migrate_country_currency_table()
    except Exception as e:
        logger.warning(f"Ошибка при миграции: {e}. Продолжаем инициализацию...")
    
    # Создаем все таблицы
    Base.metadata.create_all(bind=engine)
    print("[OK] База данных инициализирована!")


@contextmanager
def get_session():
    """Контекстный менеджер для сессии БД"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ===== City =====

def get_or_create_city(session: Session, name_ru: str, name_local: str, name_en: str, 
                       latitude: float = None, longitude: float = None, 
                       country_code: str = None) -> City:
    """Получить или создать город"""
    # Ищем город по названию на русском (основной поиск)
    city = session.query(City).filter_by(name_ru=name_ru).first()
    
    if not city:
        # Если не нашли, ищем по местному названию
        city = session.query(City).filter_by(name_local=name_local).first()
    
    if not city:
        # Если не нашли, ищем по английскому названию
        city = session.query(City).filter_by(name_en=name_en).first()
    
    if not city:
        # Создаем новый город
        city = City(
            name_ru=name_ru,
            name_local=name_local,
            name_en=name_en,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code
        )
        session.add(city)
        session.commit()
        logger.info(f"Created new city: {name_ru} ({name_local}, {name_en})")
    else:
        # Обновляем координаты, если они не были установлены
        if city.latitude is None and latitude is not None:
            city.latitude = latitude
        if city.longitude is None and longitude is not None:
            city.longitude = longitude
        if city.country_code is None and country_code is not None:
            city.country_code = country_code
        session.commit()
    
    return city


def get_city_by_id(session: Session, city_id: int) -> Optional[City]:
    """Получить город по ID"""
    return session.query(City).filter_by(id=city_id).first()


def get_all_cities(session: Session) -> List[City]:
    """Получить все города"""
    return session.query(City).order_by(City.name_ru.asc()).all()


def search_cities(session: Session, query: str) -> List[City]:
    """Поиск городов по названию (на любом языке)"""
    search_term = f"%{query.lower()}%"
    return session.query(City).filter(
        (City.name_ru.ilike(search_term)) |
        (City.name_local.ilike(search_term)) |
        (City.name_en.ilike(search_term))
    ).order_by(City.name_ru.asc()).all()


# ===== CountryCurrency =====

def get_or_create_country_currency(
    session: Session,
    country_code: str,
    currency_code: str,
    currency_name: str = None,
    currency_symbol: str = None
) -> CountryCurrency:
    """Получить или создать запись о валюте страны"""
    country_currency = session.query(CountryCurrency).filter_by(
        country_code=country_code.upper()
    ).first()
    
    if country_currency:
        # Обновляем существующую запись
        country_currency.currency_code = currency_code
        if currency_name:
            country_currency.currency_name = currency_name
        if currency_symbol:
            country_currency.currency_symbol = currency_symbol
        country_currency.updated_at = datetime.utcnow()
        session.commit()
        return country_currency
    
    # Создаем новую запись
    country_currency = CountryCurrency(
        country_code=country_code.upper(),
        currency_code=currency_code,
        currency_name=currency_name,
        currency_symbol=currency_symbol
    )
    session.add(country_currency)
    session.commit()
    return country_currency


def get_country_currency(session: Session, country_code: str) -> Optional[CountryCurrency]:
    """Получить валюту страны из базы данных"""
    return session.query(CountryCurrency).filter_by(
        country_code=country_code.upper()
    ).first()


# ===== MasterAccount =====

def create_master_account(session: Session, telegram_id: int, name: str, description: str = '', 
                          avatar_url: str = None, city_id: int = None) -> MasterAccount:
    """Создать аккаунт мастера"""
    from bot.utils.currency import get_currency_by_country
    
    # Определяем валюту на основе города, если город указан
    currency = 'RUB'  # По умолчанию
    if city_id:
        city = get_city_by_id(session, city_id)
        if city and city.country_code:
            currency = get_currency_by_country(city.country_code)
    
    acc = MasterAccount(telegram_id=telegram_id, name=name, description=description, 
                        avatar_url=avatar_url, city_id=city_id, currency=currency)
    session.add(acc)
    session.commit()
    return acc


def get_master_by_telegram(session: Session, telegram_id: int) -> Optional[MasterAccount]:
    """Получить мастера по Telegram ID"""
    return session.query(MasterAccount).filter_by(telegram_id=telegram_id).first()


def get_master_clients_count(session: Session, master_id: int) -> int:
    """Получить количество клиентов мастера"""
    return session.query(UserMaster).filter_by(master_account_id=master_id).count()


# ===== User =====

def get_or_create_user(session: Session, telegram_id: int) -> User:
    """Получить или создать пользователя"""
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
    return user


# ===== User–Master linking =====

def add_user_master_link(session: Session, user: User, master: MasterAccount) -> UserMaster:
    """Добавить связь между пользователем и мастером"""
    link = session.query(UserMaster).filter_by(user_id=user.id, master_account_id=master.id).first()
    if not link:
        link = UserMaster(user_id=user.id, master_account_id=master.id)
        session.add(link)
        session.commit()
    return link


def remove_user_master_link(session: Session, user: User, master: MasterAccount) -> bool:
    """Удалить связь между пользователем и мастером"""
    link = session.query(UserMaster).filter_by(user_id=user.id, master_account_id=master.id).first()
    if link:
        session.delete(link)
        session.commit()
        return True
    return False


def get_client_masters(session: Session, user: User) -> List[UserMaster]:
    """Получить всех мастеров клиента (только активных, не заблокированных)"""
    # Фильтруем заблокированных мастеров
    return session.query(UserMaster).join(MasterAccount).filter(
        UserMaster.user_id == user.id,
        MasterAccount.is_blocked == False
    ).all()


# ===== ServiceCategory =====

def create_service_category(
    session: Session, 
    master_id: int, 
    title: str, 
    emoji: str = None, 
    is_predefined: bool = False, 
    category_key: str = None
) -> ServiceCategory:
    """Создать категорию услуг"""
    cat = ServiceCategory(
        master_account_id=master_id, 
        title=title,
        emoji=emoji,
        is_predefined=is_predefined,
        category_key=category_key
    )
    session.add(cat)
    session.commit()
    return cat


def get_or_create_predefined_category(session: Session, master_id: int, category_key: str) -> ServiceCategory:
    """Получить или создать предустановленную категорию"""
    from bot.data.service_templates import get_category_info
    
    # Проверяем, существует ли уже такая категория
    existing = session.query(ServiceCategory).filter_by(
        master_account_id=master_id,
        category_key=category_key,
        is_predefined=True
    ).first()
    
    if existing:
        return existing
    
    # Создаем новую предустановленную категорию
    cat_info = get_category_info(category_key)
    if not cat_info:
        return None
    
    return create_service_category(
        session=session,
        master_id=master_id,
        title=cat_info['name'],
        emoji=cat_info['emoji'],
        is_predefined=True,
        category_key=category_key
    )


def get_categories_by_master(session: Session, master_id: int) -> List[ServiceCategory]:
    """Получить все категории услуг мастера"""
    return session.query(ServiceCategory).filter_by(master_account_id=master_id).all()


def get_category_by_id(session: Session, category_id: int) -> Optional[ServiceCategory]:
    """Получить категорию по ID"""
    return session.query(ServiceCategory).filter_by(id=category_id).first()


# ===== Service =====

def create_service(
    session: Session, 
    master_id: int, 
    title: str, 
    price: float, 
    duration: int, 
    cooling: int, 
    category_id: int = None, 
    description: str = ''
) -> Service:
    """Создать услугу"""
    srv = Service(
        master_account_id=master_id,
        title=title,
        price=price,
        duration_mins=duration,
        cooling_period_mins=cooling,
        category_id=category_id,
        description=description
    )
    session.add(srv)
    session.commit()
    return srv


def get_services_by_master(session: Session, master_id: int, active_only: bool = True) -> List[Service]:
    """Получить все услуги мастера"""
    q = session.query(Service).filter_by(master_account_id=master_id)
    if active_only:
        q = q.filter_by(active=True)
    return q.all()


def update_service(session: Session, service_id: int, **kwargs) -> bool:
    """Обновить услугу"""
    service = session.query(Service).filter_by(id=service_id).first()
    if not service:
        return False
    for k, v in kwargs.items():
        if hasattr(service, k):
            setattr(service, k, v)
    session.commit()
    return True


def deactivate_service(session: Session, service_id: int) -> bool:
    """Деактивировать услугу"""
    return update_service(session, service_id, active=False)


def get_service_by_id(session: Session, service_id: int) -> Optional[Service]:
    """Получить услугу по ID"""
    return session.query(Service).filter_by(id=service_id).first()


def delete_service(session: Session, service_id: int) -> bool:
    """Удалить услугу полностью"""
    service = get_service_by_id(session, service_id)
    if not service:
        return False
    session.delete(service)
    session.commit()
    return True


# ===== WorkPeriod =====

def set_work_period(session: Session, master_id: int, weekday: int, start: str, end: str) -> WorkPeriod:
    """Создать рабочий период мастера"""
    wp = WorkPeriod(master_account_id=master_id, weekday=weekday, start_time=start, end_time=end)
    session.add(wp)
    session.commit()
    return wp


def get_work_periods(session: Session, master_id: int) -> List[WorkPeriod]:
    """Получить все рабочие периоды мастера"""
    return session.query(WorkPeriod).filter_by(master_account_id=master_id).all()


def get_work_periods_by_weekday(session: Session, master_id: int, weekday: int) -> List[WorkPeriod]:
    """Получить рабочие периоды мастера для конкретного дня недели"""
    return session.query(WorkPeriod).filter_by(
        master_account_id=master_id,
        weekday=weekday
    ).order_by(WorkPeriod.start_time).all()


def delete_work_period(session: Session, period_id: int) -> bool:
    """Удалить рабочий период"""
    period = session.query(WorkPeriod).filter_by(id=period_id).first()
    if period:
        session.delete(period)
        session.commit()
        return True
    return False


def delete_all_work_periods_for_day(session: Session, master_id: int, weekday: int) -> int:
    """Удалить все периоды для конкретного дня недели"""
    deleted = session.query(WorkPeriod).filter_by(
        master_account_id=master_id,
        weekday=weekday
    ).delete()
    session.commit()
    return deleted


# ===== Booking =====

def create_booking(
    session: Session, 
    user_id: int, 
    master_id: int, 
    service_id: int, 
    start_dt: datetime, 
    end_dt: datetime, 
    price: float, 
    comment: str = ''
) -> Booking:
    """Создать бронирование"""
    bk = Booking(
        user_id=user_id, 
        master_account_id=master_id, 
        service_id=service_id, 
        start_dt=start_dt, 
        end_dt=end_dt, 
        price=price, 
        comment=comment
    )
    session.add(bk)
    session.commit()
    return bk


def get_bookings_for_client(session: Session, user_id: int) -> List[Booking]:
    """Получить все бронирования клиента"""
    return session.query(Booking).filter_by(user_id=user_id).order_by(Booking.start_dt.desc()).all()


def get_bookings_for_master(session: Session, master_id: int) -> List[Booking]:
    """Получить все бронирования мастера"""
    return session.query(Booking).filter_by(master_account_id=master_id).order_by(Booking.start_dt.desc()).all()


def get_bookings_for_master_in_range(session: Session, master_id: int, start_dt: datetime, end_dt: datetime) -> List[Booking]:
    """Получить бронирования мастера в диапазоне дат"""
    return session.query(Booking).filter(
        Booking.master_account_id == master_id,
        Booking.start_dt >= start_dt,
        Booking.start_dt < end_dt
    ).order_by(Booking.start_dt).all()


def get_booking(session: Session, booking_id: int) -> Optional[Booking]:
    """Получить бронирование по ID"""
    return session.query(Booking).filter_by(id=booking_id).first()


def check_booking_conflict(
    session: Session, 
    master_id: int, 
    start_dt: datetime, 
    end_dt: datetime,
    exclude_booking_id: Optional[int] = None
) -> bool:
    """Проверить, есть ли конфликтующие бронирования (пересечения по времени)"""
    query = session.query(Booking).filter(
        Booking.master_account_id == master_id,
        # Проверка пересечения: новое бронирование начинается до конца существующего
        # И новое бронирование заканчивается после начала существующего
        Booking.start_dt < end_dt,
        Booking.end_dt > start_dt
    )
    
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)
    
    return query.first() is not None


# ===== Super Admin =====

def is_superadmin(user_id: int) -> bool:
    """Проверка суперадмина по конфигу"""
    return user_id in SUPER_ADMINS


# ===== Admin Functions =====

def get_all_masters(session: Session, include_blocked: bool = True) -> List[MasterAccount]:
    """Получить всех мастеров"""
    query = session.query(MasterAccount)
    if not include_blocked:
        query = query.filter_by(is_blocked=False)
    return query.order_by(MasterAccount.created_at.desc()).all()


def get_blocked_masters(session: Session) -> List[MasterAccount]:
    """Получить всех заблокированных мастеров"""
    return session.query(MasterAccount).filter_by(is_blocked=True).order_by(MasterAccount.blocked_at.desc()).all()


def get_master_by_id(session: Session, master_id: int) -> Optional[MasterAccount]:
    """Получить мастера по ID"""
    return session.query(MasterAccount).filter_by(id=master_id).first()


def get_masters_by_city(session: Session, city_id: int, exclude_user_id: int = None, active_only: bool = True) -> List[MasterAccount]:
    """
    Получить мастеров по городу
    
    Args:
        session: Сессия БД
        city_id: ID города
        exclude_user_id: Telegram ID пользователя, мастеров которого нужно исключить (уже добавленных)
        active_only: Только активные (не заблокированные) мастера
    
    Returns:
        Список мастеров
    """
    query = session.query(MasterAccount).filter_by(city_id=city_id)
    
    if active_only:
        query = query.filter_by(is_blocked=False)
    
    # Исключаем мастеров, которые уже добавлены пользователем
    if exclude_user_id:
        user = get_or_create_user(session, exclude_user_id)
        if user:
            # Получаем ID мастеров, которые уже добавлены
            added_master_ids = [
                link.master_account_id 
                for link in session.query(UserMaster).filter_by(user_id=user.id).all()
            ]
            logger.info(f"User {exclude_user_id} has {len(added_master_ids)} masters already added: {added_master_ids}")
            if added_master_ids:
                query = query.filter(~MasterAccount.id.in_(added_master_ids))
    
    masters = query.order_by(MasterAccount.name.asc()).all()
    logger.info(f"Found {len(masters)} masters in city {city_id} (excluding user {exclude_user_id})")
    return masters


def block_master(session: Session, master_id: int, reason: str = None) -> bool:
    """Заблокировать мастера"""
    master = get_master_by_id(session, master_id)
    if not master:
        return False
    master.is_blocked = True
    master.blocked_at = datetime.utcnow()
    master.block_reason = reason
    session.commit()
    return True


def unblock_master(session: Session, master_id: int) -> bool:
    """Разблокировать мастера"""
    master = get_master_by_id(session, master_id)
    if not master:
        return False
    master.is_blocked = False
    master.blocked_at = None
    master.block_reason = None
    session.commit()
    return True


def delete_master(session: Session, master_id: int) -> bool:
    """Удалить мастера и все связанные данные (каскадное удаление)"""
    try:
        master = get_master_by_id(session, master_id)
        if not master:
            logger.warning(f"Master {master_id} not found for deletion")
            return False
        
        # Удаляем все связанные данные явно для гарантии каскадного удаления
        # Это важно, потому что bulk delete может не вызывать каскадное удаление
        # Порядок удаления важен из-за foreign keys
        
        # 1. Удаляем бронирования (Booking) - они могут ссылаться на услуги
        bookings = get_bookings_for_master(session, master_id)
        for booking in bookings:
            session.delete(booking)
        
        # 2. Удаляем услуги (Service) - они ссылаются на категории
        services = get_services_by_master(session, master_id, active_only=False)
        for service in services:
            session.delete(service)
        
        # 3. Удаляем категории услуг (ServiceCategory) - после удаления услуг
        from bot.database.models import ServiceCategory
        categories = session.query(ServiceCategory).filter_by(master_account_id=master_id).all()
        for category in categories:
            session.delete(category)
        
        # 4. Удаляем периоды работы (WorkPeriod)
        work_periods = get_work_periods(session, master_id)
        for period in work_periods:
            session.delete(period)
        
        # 5. Удаляем связи с клиентами (UserMaster) - последними, так как они ссылаются на мастера
        user_masters = session.query(UserMaster).filter_by(master_account_id=master_id).all()
        for user_master in user_masters:
            session.delete(user_master)
        
        # 6. Удаляем самого мастера - в последнюю очередь
        session.delete(master)
        
        # Коммитим все изменения
        session.commit()
        
        logger.info(f"Master {master_id} and all related data deleted successfully")
        return True
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting master {master_id}: {e}", exc_info=True)
        return False


def update_master_subscription(session: Session, master_id: int, subscription_level: str, expires_at: datetime = None) -> bool:
    """Обновить подписку мастера"""
    master = get_master_by_id(session, master_id)
    if not master:
        return False
    
    if subscription_level not in ['free', 'basic', 'premium']:
        return False
    
    master.subscription_level = subscription_level
    master.subscription_expires_at = expires_at
    session.commit()
    return True


# ===== Payment =====

def create_payment_record(
    session: Session,
    master_id: int,
    payment_id: str,
    amount: float,
    subscription_type: str,
    confirmation_url: str,
    currency: str = 'RUB'
) -> Optional[Payment]:
    """Создать запись о платеже"""
    try:
        payment = Payment(
            master_account_id=master_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            status='pending',
            subscription_type=subscription_type,
            confirmation_url=confirmation_url
        )
        session.add(payment)
        session.commit()
        return payment
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating payment record: {e}", exc_info=True)
        return None


def update_payment_status(
    session: Session,
    payment_id: str,
    status: str,
    paid_at: datetime = None
) -> bool:
    """Обновить статус платежа"""
    try:
        payment = session.query(Payment).filter_by(payment_id=payment_id).first()
        if not payment:
            return False
        
        payment.status = status
        if paid_at:
            payment.paid_at = paid_at
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating payment status: {e}", exc_info=True)
        return False


def get_payment_by_id(session: Session, payment_id: str) -> Optional[Payment]:
    """Получить платеж по ID от ЮKassa"""
    return session.query(Payment).filter_by(payment_id=payment_id).first()


# ===== Portfolio =====

def add_portfolio_photo(session: Session, service_id: int, file_id: str, caption: str = None) -> Optional[Portfolio]:
    """Добавить фото в портфолио услуги (максимум 3 фото на услугу)"""
    try:
        # Проверяем, существует ли услуга
        service = get_service_by_id(session, service_id)
        if not service:
            return None
        
        # Получаем текущее количество фото в портфолио услуги
        current_count = session.query(Portfolio).filter_by(service_id=service_id).count()
        
        # Лимит: 3 фото на услугу
        max_photos = 3
        
        if current_count >= max_photos:
            return None  # Достигнут лимит
        
        # Получаем максимальный order_index для этой услуги
        max_order = session.query(Portfolio.order_index).filter_by(service_id=service_id).order_by(Portfolio.order_index.desc()).first()
        next_order = (max_order[0] + 1) if max_order else 0
        
        portfolio = Portfolio(
            service_id=service_id,
            file_id=file_id,
            caption=caption,
            order_index=next_order
        )
        session.add(portfolio)
        session.commit()
        return portfolio
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding portfolio photo: {e}", exc_info=True)
        return None


def get_portfolio_photos(session: Session, service_id: int) -> List[Portfolio]:
    """Получить все фото портфолио услуги"""
    return session.query(Portfolio).filter_by(service_id=service_id).order_by(Portfolio.order_index.asc()).all()


def delete_portfolio_photo(session: Session, photo_id: int) -> bool:
    """Удалить фото из портфолио"""
    try:
        photo = session.query(Portfolio).filter_by(id=photo_id).first()
        if not photo:
            return False
        
        session.delete(photo)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting portfolio photo: {e}", exc_info=True)
        return False


def get_portfolio_limit(session: Session, service_id: int) -> tuple[int, int]:
    """Получить текущее количество и лимит фото в портфолио услуги"""
    service = get_service_by_id(session, service_id)
    if not service:
        return 0, 0
    
    current_count = session.query(Portfolio).filter_by(service_id=service_id).count()
    max_photos = 3  # Лимит: 3 фото на услугу
    
    return current_count, max_photos


def get_master_stats(session: Session) -> dict:
    """Получить статистику по мастерам"""
    total_masters = session.query(MasterAccount).count()
    active_masters = session.query(MasterAccount).filter_by(is_blocked=False).count()
    blocked_masters = session.query(MasterAccount).filter_by(is_blocked=True).count()
    
    # Подписки
    free_count = session.query(MasterAccount).filter_by(subscription_level='free', is_blocked=False).count()
    basic_count = session.query(MasterAccount).filter_by(subscription_level='basic', is_blocked=False).count()
    premium_count = session.query(MasterAccount).filter_by(subscription_level='premium', is_blocked=False).count()
    
    # Клиенты
    total_clients = session.query(User).count()
    
    # Активные записи (будущие)
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    active_bookings = session.query(Booking).filter(Booking.start_dt > now).count()
    
    return {
        'total_masters': total_masters,
        'active_masters': active_masters,
        'blocked_masters': blocked_masters,
        'subscriptions': {
            'free': free_count,
            'basic': basic_count,
            'premium': premium_count
        },
        'total_clients': total_clients,
        'active_bookings': active_bookings
    }


def get_masters_paginated(session: Session, page: int = 1, per_page: int = 10, include_blocked: bool = True, search_query: str = None) -> tuple[List[MasterAccount], int]:
    """Получить мастеров с пагинацией"""
    query = session.query(MasterAccount)
    
    if not include_blocked:
        query = query.filter_by(is_blocked=False)
    
    if search_query:
        # Поиск по имени или telegram_id
        try:
            telegram_id = int(search_query)
            query = query.filter(MasterAccount.telegram_id == telegram_id)
        except ValueError:
            # Поиск по имени
            query = query.filter(MasterAccount.name.ilike(f'%{search_query}%'))
    
    total = query.count()
    offset = (page - 1) * per_page
    masters = query.order_by(MasterAccount.created_at.desc()).offset(offset).limit(per_page).all()
    
    return masters, total
