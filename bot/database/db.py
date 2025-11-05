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


def init_db():
    """Инициализация базы данных"""
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


# ===== MasterAccount =====

def create_master_account(session: Session, telegram_id: int, name: str, description: str = '', avatar_url: str = None) -> MasterAccount:
    """Создать аккаунт мастера"""
    acc = MasterAccount(telegram_id=telegram_id, name=name, description=description, avatar_url=avatar_url)
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

def add_portfolio_photo(session: Session, master_id: int, file_id: str, caption: str = None) -> Optional[Portfolio]:
    """Добавить фото в портфолио мастера"""
    try:
        # Проверяем лимиты портфолио в зависимости от подписки
        master = get_master_by_id(session, master_id)
        if not master:
            return None
        
        # Получаем текущее количество фото в портфолио
        current_count = session.query(Portfolio).filter_by(master_account_id=master_id).count()
        
        # Определяем лимиты
        if master.subscription_level == 'premium':
            max_photos = 50  # Премиум - без ограничений (практически)
        elif master.subscription_level == 'basic':
            max_photos = 10
        else:  # free
            max_photos = 3
        
        if current_count >= max_photos:
            return None  # Достигнут лимит
        
        # Получаем максимальный order_index
        max_order = session.query(Portfolio.order_index).filter_by(master_account_id=master_id).order_by(Portfolio.order_index.desc()).first()
        next_order = (max_order[0] + 1) if max_order else 0
        
        portfolio = Portfolio(
            master_account_id=master_id,
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


def get_portfolio_photos(session: Session, master_id: int) -> List[Portfolio]:
    """Получить все фото портфолио мастера"""
    return session.query(Portfolio).filter_by(master_account_id=master_id).order_by(Portfolio.order_index.asc()).all()


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


def get_portfolio_limit(session: Session, master_id: int) -> tuple[int, int]:
    """Получить текущее количество и лимит фото в портфолио"""
    master = get_master_by_id(session, master_id)
    if not master:
        return 0, 0
    
    current_count = session.query(Portfolio).filter_by(master_account_id=master_id).count()
    
    if master.subscription_level == 'premium':
        max_photos = 50
    elif master.subscription_level == 'basic':
        max_photos = 10
    else:  # free
        max_photos = 3
    
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
