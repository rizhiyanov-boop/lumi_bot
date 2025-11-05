# 💡 Примеры кода для мультиклубной системы

## 📌 Вариант 1: Deep Links - Детальная реализация

### 1. Обновленные модели БД

```python
# bot/database/models.py

from sqlalchemy import UniqueConstraint

class Club(Base):
    """Клуб - верхний уровень изоляции"""
    __tablename__ = 'clubs'
    
    id = Column(Integer, primary_key=True)
    slug = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    active = Column(Boolean, default=True)
    
    # Настройки клуба
    work_start = Column(String(5), default="09:00")
    work_end = Column(String(5), default="21:00")
    timezone = Column(String(50), default="Europe/Moscow")
    
    # Контактная информация
    phone = Column(String(20))
    email = Column(String(100))
    website = Column(String(255))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    locations = relationship("Location", back_populates="club", cascade="all, delete-orphan")
    user_contexts = relationship("UserContext", back_populates="club")
    admins = relationship("ClubAdmin", back_populates="club")
    
    def __repr__(self):
        return f"<Club(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class UserContext(Base):
    """Контекст пользователя - привязка к клубу"""
    __tablename__ = 'user_contexts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)
    
    # Telegram информация
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="user_contexts")
    
    def __repr__(self):
        return f"<UserContext(user_id={self.user_id}, club_id={self.club_id})>"


class ClubAdmin(Base):
    """Администраторы клуба"""
    __tablename__ = 'club_admins'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)
    
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    
    notify = Column(Boolean, default=True)
    is_super_admin = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="admins")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'club_id', name='unique_admin_per_club'),
    )
    
    def __repr__(self):
        return f"<ClubAdmin(user_id={self.user_id}, club_id={self.club_id})>"


# Обновляем Location
class Location(Base):
    """Локация пейнтбольного клуба"""
    __tablename__ = 'locations'
    
    id = Column(Integer, primary_key=True)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)  # ← НОВОЕ
    name = Column(String(100), nullable=False)
    address = Column(String(255), nullable=False)
    description = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="locations")  # ← НОВОЕ
    fields = relationship("Field", back_populates="location", cascade="all, delete-orphan")
```

### 2. Функции работы с БД

```python
# bot/database/db.py

# ===== Функции для работы с клубами =====

def get_club_by_slug(session: Session, slug: str) -> Optional[Club]:
    """Получить клуб по slug"""
    return session.query(Club).filter(
        Club.slug == slug,
        Club.active == True
    ).first()


def get_all_clubs(session: Session, active_only: bool = True) -> List[Club]:
    """Получить все клубы"""
    query = session.query(Club)
    if active_only:
        query = query.filter(Club.active == True)
    return query.all()


# ===== Функции для работы с контекстом пользователя =====

def get_user_context(session: Session, user_id: int) -> Optional[UserContext]:
    """Получить контекст пользователя"""
    return session.query(UserContext).filter_by(user_id=user_id).first()


def create_user_context(
    session: Session,
    user_id: int,
    club_id: int,
    username: str = None,
    first_name: str = None,
    last_name: str = None
) -> UserContext:
    """Создать контекст пользователя"""
    context = UserContext(
        user_id=user_id,
        club_id=club_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    session.add(context)
    session.commit()
    return context


def update_user_last_active(session: Session, user_id: int):
    """Обновить время последней активности пользователя"""
    context = get_user_context(session, user_id)
    if context:
        context.last_active = datetime.utcnow()
        session.commit()


# ===== Обновленные функции с фильтрацией по клубу =====

def get_all_locations(session: Session, club_id: int, active_only: bool = True) -> List[Location]:
    """Получить все локации клуба"""
    query = session.query(Location).filter(Location.club_id == club_id)
    if active_only:
        query = query.filter(Location.active == True)
    return query.all()


def get_fields_by_location(session: Session, location_id: int, club_id: int, active_only: bool = True) -> List[Field]:
    """Получить все площадки локации (с проверкой club_id)"""
    query = session.query(Field).join(Location).filter(
        Field.location_id == location_id,
        Location.club_id == club_id
    )
    if active_only:
        query = query.filter(Field.active == True)
    return query.all()


def get_user_bookings(session: Session, user_id: int, club_id: int, active_only: bool = True) -> List[Booking]:
    """Получить все бронирования пользователя В РАМКАХ клуба"""
    query = session.query(Booking).join(Field).join(Location).filter(
        Booking.user_id == user_id,
        Location.club_id == club_id
    )
    
    if active_only:
        query = query.filter(Booking.status != BookingStatus.CANCELLED)
    
    return query.order_by(Booking.date.desc(), Booking.start_time.desc()).all()


def get_all_bookings(
    session: Session,
    club_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    status: Optional[BookingStatus] = None
) -> List[Booking]:
    """Получить все бронирования клуба с фильтрами"""
    query = session.query(Booking).join(Field).join(Location).filter(
        Location.club_id == club_id
    )
    
    if from_date:
        query = query.filter(Booking.date >= from_date)
    if to_date:
        query = query.filter(Booking.date <= to_date)
    if status:
        query = query.filter(Booking.status == status)
    
    return query.order_by(Booking.date.desc(), Booking.start_time.desc()).all()


# ===== Функции для работы с админами клуба =====

def is_club_admin(session: Session, user_id: int, club_id: int) -> bool:
    """Проверить, является ли пользователь админом клуба"""
    return session.query(ClubAdmin).filter(
        ClubAdmin.user_id == user_id,
        ClubAdmin.club_id == club_id
    ).first() is not None


def get_club_admin(session: Session, user_id: int, club_id: int) -> Optional[ClubAdmin]:
    """Получить админа клуба"""
    return session.query(ClubAdmin).filter(
        ClubAdmin.user_id == user_id,
        ClubAdmin.club_id == club_id
    ).first()


def get_all_club_admins(session: Session, club_id: int, notify_only: bool = False) -> List[ClubAdmin]:
    """Получить всех админов клуба"""
    query = session.query(ClubAdmin).filter(ClubAdmin.club_id == club_id)
    if notify_only:
        query = query.filter(ClubAdmin.notify == True)
    return query.all()


def add_club_admin(
    session: Session,
    user_id: int,
    club_id: int,
    username: str = None,
    first_name: str = None,
    is_super_admin: bool = False
) -> ClubAdmin:
    """Добавить админа клуба"""
    admin = ClubAdmin(
        user_id=user_id,
        club_id=club_id,
        username=username,
        first_name=first_name,
        is_super_admin=is_super_admin,
        notify=True
    )
    session.add(admin)
    session.commit()
    return admin
```

### 3. Middleware для проверки контекста

```python
# bot/utils/middleware.py

from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_user_context, update_user_last_active

def require_club_context(func):
    """
    Декоратор для проверки наличия контекста клуба у пользователя.
    Автоматически добавляет club_id в context.user_data
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not user:
            return
        
        with get_session() as session:
            user_context = get_user_context(session, user.id)
            
            if not user_context:
                message = (
                    "⚠️ Ваш аккаунт не привязан к клубу.\n\n"
                    "Для использования бота перейдите по ссылке, "
                    "предоставленной администратором вашего клуба."
                )
                
                if update.message:
                    await update.message.reply_text(message)
                elif update.callback_query:
                    await update.callback_query.answer(
                        "Нет доступа. Используйте ссылку от клуба.",
                        show_alert=True
                    )
                
                return
            
            # Обновляем время последней активности
            update_user_last_active(session, user.id)
            
            # Сохраняем club_id в context для использования в handler
            context.user_data['club_id'] = user_context.club_id
            context.user_data['club'] = {
                'id': user_context.club.id,
                'name': user_context.club.name,
                'slug': user_context.club.slug
            }
        
        return await func(update, context)
    
    return wrapper


def require_club_admin(func):
    """
    Декоратор для проверки прав администратора клуба.
    Требует наличия club_id в context.user_data (использовать после require_club_context)
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        club_id = context.user_data.get('club_id')
        
        if not club_id:
            await update.callback_query.answer(
                "Ошибка контекста",
                show_alert=True
            )
            return
        
        with get_session() as session:
            if not is_club_admin(session, user.id, club_id):
                await update.callback_query.answer(
                    "У вас нет прав администратора",
                    show_alert=True
                )
                return
        
        return await func(update, context)
    
    return wrapper
```

### 4. Обновленные handlers

```python
# bot/handlers/user.py

from bot.utils.middleware import require_club_context

@require_club_context
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start с deep link поддержкой"""
    user = update.effective_user
    args = context.args
    
    with get_session() as session:
        # Проверяем существующий контекст
        user_context = get_user_context(session, user.id)
        
        # Если есть deep link параметр
        if args and args[0].startswith('club_'):
            club_slug = args[0].replace('club_', '')
            club = get_club_by_slug(session, club_slug)
            
            if not club:
                await update.message.reply_text(
                    "❌ Неверная ссылка клуба.\n"
                    "Обратитесь к администратору."
                )
                return
            
            # Если пользователь уже привязан к другому клубу
            if user_context and user_context.club_id != club.id:
                await update.message.reply_text(
                    f"⚠️ Вы уже привязаны к клубу '{user_context.club.name}'.\n\n"
                    f"Хотите переключиться на '{club.name}'? "
                    "Обратитесь к администратору для смены клуба."
                )
                return
            
            # Создаем новый контекст
            if not user_context:
                create_user_context(
                    session,
                    user_id=user.id,
                    club_id=club.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name
                )
                
                await update.message.reply_text(
                    f"🎯 Добро пожаловать в {club.name}!\n\n"
                    f"Теперь вы можете бронировать площадки."
                )
        
        # Обновляем контекст (он мог быть создан выше)
        user_context = get_user_context(session, user.id)
        
        if not user_context:
            await update.message.reply_text(
                "⚠️ Для использования бота перейдите по ссылке от вашего клуба.\n\n"
                "Свяжитесь с администратором клуба для получения ссылки."
            )
            return
        
        club = user_context.club
        is_admin = is_club_admin(session, user.id, club.id)
    
    welcome_text = f"""
👋 Привет, {user.first_name}!

Вы в системе бронирования <b>{club.name}</b>

🎯 Здесь вы можете:
• Забронировать игру на удобное время
• Выбрать площадку
• Управлять своими бронированиями

Выберите действие из меню ниже:
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=get_main_menu_keyboard(is_admin)
    )


@require_club_context
async def my_bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /my_bookings с фильтрацией по клубу"""
    user = update.effective_user
    club_id = context.user_data['club_id']
    
    if update.callback_query:
        await update.callback_query.answer()
    
    with get_session() as session:
        bookings = get_user_bookings(session, user.id, club_id, active_only=False)
        
        # Извлекаем данные
        bookings_data = []
        for booking in bookings:
            bookings_data.append({
                'id': booking.id,
                'date': booking.date,
                'start_time': booking.start_time,
                'field_name': booking.field.name,
                'location_name': booking.field.location.name,
                'status': booking.status.value
            })
    
    if not bookings_data:
        text = "У вас пока нет бронирований."
    else:
        text = f"📋 <b>Ваши бронирования ({len(bookings_data)}):</b>\n\nВыберите для подробностей:"
    
    keyboard = get_my_bookings_keyboard(bookings_data)
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
```

```python
# bot/handlers/booking.py

from bot.utils.middleware import require_club_context

@require_club_context
async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать процесс бронирования"""
    query = update.callback_query
    await query.answer()
    
    club_id = context.user_data['club_id']
    
    with get_session() as session:
        locations = get_all_locations(session, club_id)
        
        if not locations:
            await query.answer(
                "К сожалению, сейчас нет доступных локаций",
                show_alert=True
            )
            return
        
        # Извлекаем данные
        locations_data = [(loc.id, loc.name) for loc in locations]
    
    text = "📍 <b>Выберите локацию:</b>"
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = []
    for loc_id, loc_name in locations_data:
        keyboard.append([
            InlineKeyboardButton(
                f"📍 {loc_name}",
                callback_data=f"location_{loc_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="main_menu")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
```

```python
# bot/handlers/admin.py

from bot.utils.middleware import require_club_context, require_club_admin

@require_club_context
@require_club_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-панель"""
    query = update.callback_query
    await query.answer()
    
    club_name = context.user_data['club']['name']
    
    text = f"👨‍💼 <b>Админ-панель</b>\n<i>{club_name}</i>\n\nВыберите действие:"
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=get_admin_panel_keyboard()
    )


@require_club_context
@require_club_admin
async def admin_all_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все бронирования клуба"""
    query = update.callback_query
    await query.answer()
    
    club_id = context.user_data['club_id']
    
    with get_session() as session:
        from_date = date.today() - timedelta(days=30)
        bookings = get_all_bookings(session, club_id, from_date=from_date)
        
        # Извлекаем данные
        bookings_data = []
        for booking in bookings:
            bookings_data.append({
                'id': booking.id,
                'date': booking.date,
                'start_time': booking.start_time,
                'field_name': booking.field.name,
                'username': booking.username,
                'status': booking.status.value
            })
    
    if not bookings_data:
        text = "📊 <b>Все бронирования</b>\n\nБронирований не найдено."
    else:
        text = f"📊 <b>Все бронирования</b>\n\nВсего: {len(bookings_data)}\nВыберите для просмотра:"
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=get_admin_bookings_keyboard(bookings_data, page=0)
    )
```

### 5. Миграционный скрипт

```python
# migrations/add_multiclub_support.py

from bot.database.db import get_session, engine
from bot.database.models import Base, Club, UserContext, ClubAdmin, Location, Admin
from sqlalchemy import text

def migrate():
    """Миграция на мультиклубную систему"""
    
    print("[INFO] Starting migration to multi-club system...")
    
    # 1. Создаем новые таблицы
    print("[1/5] Creating new tables...")
    Base.metadata.create_all(bind=engine)
    
    with get_session() as session:
        # 2. Создаем дефолтный клуб для существующих данных
        print("[2/5] Creating default club...")
        default_club = Club(
            slug='default',
            name='Пейнтбол (главный)',
            description='Дефолтный клуб для существующих данных',
            active=True
        )
        session.add(default_club)
        session.flush()
        
        # 3. Добавляем club_id к существующим локациям
        print("[3/5] Migrating locations...")
        session.execute(
            text(f"UPDATE locations SET club_id = {default_club.id} WHERE club_id IS NULL")
        )
        
        # 4. Мигрируем админов
        print("[4/5] Migrating admins...")
        old_admins = session.query(Admin).all()
        for old_admin in old_admins:
            club_admin = ClubAdmin(
                user_id=old_admin.user_id,
                club_id=default_club.id,
                username=old_admin.username,
                first_name=old_admin.first_name,
                notify=old_admin.notify,
                is_super_admin=old_admin.is_super_admin
            )
            session.add(club_admin)
        
        # 5. Создаем контексты для пользователей с бронированиями
        print("[5/5] Creating user contexts...")
        session.execute(text(f"""
            INSERT INTO user_contexts (user_id, club_id, created_at)
            SELECT DISTINCT user_id, {default_club.id}, datetime('now')
            FROM bookings
            WHERE user_id NOT IN (SELECT user_id FROM user_contexts)
        """))
        
        session.commit()
    
    print("[OK] Migration completed successfully!")

if __name__ == '__main__':
    migrate()
```

---

## 🔗 Генерация ссылок для клубов

```python
# admin_tools/generate_club_link.py

def generate_club_link(bot_username: str, club_slug: str) -> str:
    """Генерация deep link для клуба"""
    return f"https://t.me/{bot_username}?start=club_{club_slug}"

# Использование:
print(generate_club_link("PaintballBot", "kaluga"))
# → https://t.me/PaintballBot?start=club_kaluga

print(generate_club_link("PaintballBot", "moscow"))
# → https://t.me/PaintballBot?start=club_moscow
```

---

## 📊 Создание новых клубов

```python
# admin_tools/create_club.py

from bot.database.db import get_session
from bot.database.models import Club, Location, Field, ClubAdmin

def create_new_club(
    slug: str,
    name: str,
    admin_user_id: int,
    admin_username: str = None
):
    """Создать новый клуб с админом"""
    
    with get_session() as session:
        # Создаем клуб
        club = Club(
            slug=slug,
            name=name,
            active=True
        )
        session.add(club)
        session.flush()
        
        # Добавляем админа
        admin = ClubAdmin(
            user_id=admin_user_id,
            club_id=club.id,
            username=admin_username,
            is_super_admin=True,
            notify=True
        )
        session.add(admin)
        
        # Создаем первую локацию (опционально)
        location = Location(
            club_id=club.id,
            name="Основная локация",
            address="Адрес локации",
            description="Описание",
            active=True
        )
        session.add(location)
        session.flush()
        
        # Создаем первую площадку (опционально)
        field = Field(
            location_id=location.id,
            name="Площадка №1",
            capacity=30,
            price_per_hour=0,
            is_outdoor=True,
            active=True
        )
        session.add(field)
        
        session.commit()
        
        print(f"[OK] Club '{name}' created!")
        print(f"[OK] Link: https://t.me/YourBot?start=club_{slug}")
        print(f"[OK] Admin: {admin_user_id}")

# Использование:
create_new_club(
    slug='moscow',
    name='Пейнтбол Москва',
    admin_user_id=123456789,
    admin_username='moscow_admin'
)
```



