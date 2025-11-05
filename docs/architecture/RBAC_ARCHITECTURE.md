# 🔐 Ролевая система и тарификация - Архитектура

## 📋 Требования

### Роли и права

```
┌─────────────────────────────────────────────────────────┐
│                      СУПЕРАДМИН                         │
│  • Создание клубов                                      │
│  • Назначение владельцев                                │
│  • Настройка тарифных планов                            │
│  • Настройка дефолтных шаблонов                         │
│  • Глобальная аналитика                                 │
└─────────────────────────────────────────────────────────┘
                          │
                          │ создает клубы
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  ВЛАДЕЛЕЦ КЛУБА                         │
│  • Полное управление своим клубом                       │
│  • Назначение ролей (старший инструктор, инструктор)    │
│  • Управление услугами и ценами                         │
│  • Настройка способов расчета                           │
│  • Редактирование площадок и изображений                │
│  • Просмотр всех бронирований                           │
│  • Статистика и аналитика клуба                         │
└─────────────────────────────────────────────────────────┘
                          │
                          │ назначает
                          ▼
┌─────────────────────────────────────────────────────────┐
│               СТАРШИЙ ИНСТРУКТОР                        │
│  • Просмотр всех бронирований клуба                     │
│  • Назначение инструкторов на игры                      │
│  • Управление расписанием инструкторов                  │
│  • Просмотр статистики по инструкторам                  │
└─────────────────────────────────────────────────────────┘
                          │
                          │ назначает на игры
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    ИНСТРУКТОР                           │
│  • Просмотр своих назначенных игр                       │
│  • Уведомления о новых назначениях                      │
│  • Подтверждение/отмена участия                         │
└─────────────────────────────────────────────────────────┘
```

### Тарифные планы

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│     FREE     │    BASIC     │   PREMIUM    │     DEMO     │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ 1 площадка   │ 5 площадок   │ Безлимит     │ = Premium    │
│ 2 инструктора│ 10 инструкт. │ Безлимит     │ 14 дней      │
│ 50 броней/мес│ 300 броней   │ Безлимит     │ Авто-сброс   │
│ Базовые отч. │ Расшир.отч.  │ Полная анал. │              │
│ Без фото     │ 10 фото      │ Безлимит фото│              │
│ Email        │ Email + SMS  │ Все каналы   │              │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

---

## 🗄️ Модели базы данных

### 1. Роли и права

```python
# bot/database/models.py

class RoleType(enum.Enum):
    """Типы ролей в системе"""
    SUPERADMIN = "superadmin"           # Глобальный админ
    CLUB_OWNER = "club_owner"           # Владелец клуба
    SENIOR_INSTRUCTOR = "senior_instructor"  # Старший инструктор
    INSTRUCTOR = "instructor"           # Инструктор
    USER = "user"                       # Обычный пользователь


class Permission(enum.Enum):
    """Права доступа"""
    # Глобальные права
    MANAGE_CLUBS = "manage_clubs"
    MANAGE_PLANS = "manage_plans"
    MANAGE_TEMPLATES = "manage_templates"
    VIEW_GLOBAL_STATS = "view_global_stats"
    
    # Права клуба
    MANAGE_CLUB_SETTINGS = "manage_club_settings"
    MANAGE_CLUB_ROLES = "manage_club_roles"
    MANAGE_SERVICES = "manage_services"
    MANAGE_FIELDS = "manage_fields"
    UPLOAD_IMAGES = "upload_images"
    MANAGE_PRICING = "manage_pricing"
    VIEW_ALL_BOOKINGS = "view_all_bookings"
    CANCEL_ANY_BOOKING = "cancel_any_booking"
    VIEW_CLUB_STATS = "view_club_stats"
    
    # Права инструктора
    VIEW_BOOKINGS = "view_bookings"
    ASSIGN_INSTRUCTORS = "assign_instructors"
    VIEW_OWN_ASSIGNMENTS = "view_own_assignments"
    CONFIRM_ASSIGNMENT = "confirm_assignment"


class ClubRole(Base):
    """Роль пользователя в клубе"""
    __tablename__ = 'club_roles'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)
    role = Column(Enum(RoleType), nullable=False)
    
    # Метаданные
    assigned_by = Column(Integer)  # user_id кто назначил
    assigned_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)
    
    # Relationships
    club = relationship("Club", back_populates="roles")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'club_id', 'role', name='unique_user_club_role'),
    )
    
    def has_permission(self, permission: Permission) -> bool:
        """Проверка наличия права"""
        return permission in ROLE_PERMISSIONS[self.role]


# Маппинг ролей на права
ROLE_PERMISSIONS = {
    RoleType.SUPERADMIN: {
        Permission.MANAGE_CLUBS,
        Permission.MANAGE_PLANS,
        Permission.MANAGE_TEMPLATES,
        Permission.VIEW_GLOBAL_STATS,
        # Суперадмин имеет все права
        *list(Permission)
    },
    
    RoleType.CLUB_OWNER: {
        Permission.MANAGE_CLUB_SETTINGS,
        Permission.MANAGE_CLUB_ROLES,
        Permission.MANAGE_SERVICES,
        Permission.MANAGE_FIELDS,
        Permission.UPLOAD_IMAGES,
        Permission.MANAGE_PRICING,
        Permission.VIEW_ALL_BOOKINGS,
        Permission.CANCEL_ANY_BOOKING,
        Permission.VIEW_CLUB_STATS,
        Permission.ASSIGN_INSTRUCTORS,
    },
    
    RoleType.SENIOR_INSTRUCTOR: {
        Permission.VIEW_ALL_BOOKINGS,
        Permission.ASSIGN_INSTRUCTORS,
        Permission.VIEW_CLUB_STATS,
        Permission.VIEW_OWN_ASSIGNMENTS,
    },
    
    RoleType.INSTRUCTOR: {
        Permission.VIEW_OWN_ASSIGNMENTS,
        Permission.CONFIRM_ASSIGNMENT,
    },
    
    RoleType.USER: set()  # Нет специальных прав
}
```

### 2. Тарифные планы

```python
class SubscriptionPlan(enum.Enum):
    """Тарифные планы"""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"


class PlanFeature(Base):
    """Возможности тарифного плана"""
    __tablename__ = 'plan_features'
    
    id = Column(Integer, primary_key=True)
    plan = Column(Enum(SubscriptionPlan), nullable=False, unique=True)
    
    # Лимиты
    max_fields = Column(Integer, nullable=True)  # None = безлимит
    max_instructors = Column(Integer, nullable=True)
    max_bookings_per_month = Column(Integer, nullable=True)
    max_images = Column(Integer, nullable=True)
    
    # Возможности
    advanced_reports = Column(Boolean, default=False)
    sms_notifications = Column(Boolean, default=False)
    custom_branding = Column(Boolean, default=False)
    api_access = Column(Boolean, default=False)
    
    # Стоимость
    price_monthly = Column(Float, default=0)
    price_yearly = Column(Float, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<PlanFeature(plan='{self.plan.value}')>"


class ClubSubscription(Base):
    """Подписка клуба"""
    __tablename__ = 'club_subscriptions'
    
    id = Column(Integer, primary_key=True)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False, unique=True)
    plan = Column(Enum(SubscriptionPlan), nullable=False, default=SubscriptionPlan.FREE)
    
    # Демо режим
    is_demo = Column(Boolean, default=False)
    demo_started_at = Column(DateTime, nullable=True)
    demo_ends_at = Column(DateTime, nullable=True)
    
    # Подписка
    subscription_started_at = Column(DateTime, default=datetime.utcnow)
    subscription_ends_at = Column(DateTime, nullable=True)
    auto_renew = Column(Boolean, default=False)
    
    # Метрики использования (для контроля лимитов)
    current_fields_count = Column(Integer, default=0)
    current_instructors_count = Column(Integer, default=0)
    current_month_bookings = Column(Integer, default=0)
    current_images_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="subscription")
    
    def is_active(self) -> bool:
        """Проверка активности подписки"""
        if self.is_demo:
            if self.demo_ends_at and datetime.utcnow() > self.demo_ends_at:
                return False
            return True
        
        if self.subscription_ends_at and datetime.utcnow() > self.subscription_ends_at:
            return False
        
        return True
    
    def get_plan_features(self, session) -> PlanFeature:
        """Получить возможности плана"""
        # Если демо - используем Premium
        if self.is_demo and self.is_active():
            return session.query(PlanFeature).filter_by(
                plan=SubscriptionPlan.PREMIUM
            ).first()
        
        return session.query(PlanFeature).filter_by(plan=self.plan).first()
    
    def can_add_field(self, session) -> bool:
        """Можно ли добавить площадку"""
        features = self.get_plan_features(session)
        if features.max_fields is None:
            return True
        return self.current_fields_count < features.max_fields
    
    def can_add_instructor(self, session) -> bool:
        """Можно ли добавить инструктора"""
        features = self.get_plan_features(session)
        if features.max_instructors is None:
            return True
        return self.current_instructors_count < features.max_instructors
```

### 3. Обновленная модель Club

```python
class Club(Base):
    """Клуб с расширенными настройками"""
    __tablename__ = 'clubs'
    
    id = Column(Integer, primary_key=True)
    slug = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    active = Column(Boolean, default=True)
    
    # Настройки расчета стоимости
    pricing_mode = Column(String(20), default='hourly')  # hourly, fixed_hours, full_day
    default_booking_hours = Column(Integer, default=6)   # для fixed_hours
    
    # Настройки работы
    work_start = Column(String(5), default="09:00")
    work_end = Column(String(5), default="21:00")
    timezone = Column(String(50), default="Europe/Moscow")
    
    # Контакты
    phone = Column(String(20))
    email = Column(String(100))
    website = Column(String(255))
    
    # Брендинг
    logo_file_id = Column(String(255))  # Telegram file_id
    primary_color = Column(String(7))   # #FF5733
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    locations = relationship("Location", back_populates="club")
    roles = relationship("ClubRole", back_populates="club")
    subscription = relationship("ClubSubscription", back_populates="club", uselist=False)
    services = relationship("Service", back_populates="club")
    instructor_assignments = relationship("InstructorAssignment", back_populates="club")
```

### 4. Услуги

```python
class Service(Base):
    """Услуга клуба"""
    __tablename__ = 'services'
    
    id = Column(Integer, primary_key=True)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)
    
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    duration_hours = Column(Integer, nullable=True)  # None для full_day
    
    active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="services")
```

### 5. Назначения инструкторов

```python
class InstructorAssignment(Base):
    """Назначение инструктора на игру"""
    __tablename__ = 'instructor_assignments'
    
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey('bookings.id'), nullable=False)
    instructor_id = Column(Integer, nullable=False)  # user_id инструктора
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)
    
    # Статус
    status = Column(String(20), default='pending')  # pending, confirmed, declined
    
    # Метаданные
    assigned_by = Column(Integer, nullable=False)  # user_id кто назначил
    assigned_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    
    notes = Column(Text)
    
    # Relationships
    booking = relationship("Booking", back_populates="instructor_assignment")
    club = relationship("Club", back_populates="instructor_assignments")
    
    def __repr__(self):
        return f"<InstructorAssignment(id={self.id}, instructor_id={self.instructor_id}, status='{self.status}')>"


# Обновляем Booking
class Booking(Base):
    # ... existing fields ...
    
    # Relationships
    instructor_assignment = relationship("InstructorAssignment", back_populates="booking", uselist=False)
```

### 6. Изображения

```python
class FieldImage(Base):
    """Изображения площадок"""
    __tablename__ = 'field_images'
    
    id = Column(Integer, primary_key=True)
    field_id = Column(Integer, ForeignKey('fields.id'), nullable=False)
    club_id = Column(Integer, ForeignKey('clubs.id'), nullable=False)
    
    file_id = Column(String(255), nullable=False)  # Telegram file_id
    file_unique_id = Column(String(255))
    caption = Column(String(255))
    
    is_primary = Column(Boolean, default=False)
    order = Column(Integer, default=0)
    
    uploaded_by = Column(Integer, nullable=False)  # user_id
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    field = relationship("Field", back_populates="images")
    
    def __repr__(self):
        return f"<FieldImage(id={self.id}, field_id={self.field_id})>"


# Обновляем Field
class Field(Base):
    # ... existing fields ...
    
    # Relationships
    images = relationship("FieldImage", back_populates="field", cascade="all, delete-orphan")
```

### 7. Шаблоны (для суперадмина)

```python
class DefaultTemplate(Base):
    """Шаблоны по умолчанию для новых клубов"""
    __tablename__ = 'default_templates'
    
    id = Column(Integer, primary_key=True)
    template_type = Column(String(50), nullable=False)  # field, service, etc
    name = Column(String(100), nullable=False)
    description = Column(Text)
    data = Column(JSON)  # Дополнительные параметры
    
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('template_type', 'name', name='unique_template'),
    )
```

---

## 🔒 Система проверки прав (RBAC)

### Декораторы для проверки прав

```python
# bot/utils/rbac.py

from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_user_club_role, is_superadmin
from bot.database.models import Permission

def require_permission(permission: Permission):
    """
    Декоратор для проверки наличия права у пользователя
    Требует наличия club_id в context.user_data
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            club_id = context.user_data.get('club_id')
            
            if not club_id:
                await update.callback_query.answer(
                    "Ошибка контекста клуба",
                    show_alert=True
                )
                return
            
            with get_session() as session:
                # Проверяем суперадмина
                if is_superadmin(user.id):
                    return await func(update, context)
                
                # Проверяем роль в клубе
                role = get_user_club_role(session, user.id, club_id)
                
                if not role or not role.has_permission(permission):
                    await update.callback_query.answer(
                        "❌ Недостаточно прав для этого действия",
                        show_alert=True
                    )
                    return
            
            return await func(update, context)
        
        return wrapper
    return decorator


def require_role(required_role: RoleType):
    """Декоратор для проверки конкретной роли"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            club_id = context.user_data.get('club_id')
            
            with get_session() as session:
                # Суперадмин проходит всегда
                if is_superadmin(user.id):
                    return await func(update, context)
                
                role = get_user_club_role(session, user.id, club_id)
                
                if not role or role.role != required_role:
                    await update.callback_query.answer(
                        f"❌ Требуется роль: {required_role.value}",
                        show_alert=True
                    )
                    return
            
            return await func(update, context)
        
        return wrapper
    return decorator


def require_subscription_feature(feature_check):
    """
    Декоратор для проверки возможности тарифного плана
    feature_check - функция, принимающая PlanFeature и возвращающая bool
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            club_id = context.user_data.get('club_id')
            
            with get_session() as session:
                subscription = get_club_subscription(session, club_id)
                
                if not subscription or not subscription.is_active():
                    await update.callback_query.answer(
                        "⚠️ Подписка клуба неактивна",
                        show_alert=True
                    )
                    return
                
                features = subscription.get_plan_features(session)
                
                if not feature_check(features):
                    await update.callback_query.answer(
                        "⚠️ Эта функция недоступна в вашем тарифе.\n"
                        "Улучшите план для доступа.",
                        show_alert=True
                    )
                    return
            
            return await func(update, context)
        
        return wrapper
    return decorator
```

---

## 📱 Административные панели

### 1. Панель владельца клуба

```python
# bot/handlers/club_owner.py

from bot.utils.rbac import require_role, require_permission
from bot.database.models import RoleType, Permission

@require_role(RoleType.CLUB_OWNER)
async def club_owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель управления владельца клуба"""
    query = update.callback_query
    await query.answer()
    
    club_id = context.user_data['club_id']
    club_name = context.user_data['club']['name']
    
    with get_session() as session:
        subscription = get_club_subscription(session, club_id)
        plan_name = subscription.plan.value if subscription else "FREE"
    
    text = f"""
👑 <b>Панель владельца</b>
<i>{club_name}</i>

📊 Тариф: <b>{plan_name.upper()}</b>

<b>Управление:</b>
• Настройки клуба
• Управление ролями
• Услуги и цены
• Площадки и изображения
• Статистика

Выберите раздел:
"""
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Настройки клуба", callback_data="owner_settings")],
        [InlineKeyboardButton("👥 Управление ролями", callback_data="owner_roles")],
        [InlineKeyboardButton("💰 Услуги и цены", callback_data="owner_services")],
        [InlineKeyboardButton("🏟 Площадки", callback_data="owner_fields")],
        [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
        [InlineKeyboardButton("📋 Все бронирования", callback_data="owner_bookings")],
        [InlineKeyboardButton("« Назад", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_permission(Permission.MANAGE_CLUB_ROLES)
async def manage_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление ролями в клубе"""
    # Реализация...
```

### 2. Панель старшего инструктора

```python
@require_role(RoleType.SENIOR_INSTRUCTOR)
async def senior_instructor_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель старшего инструктора"""
    # Просмотр бронирований
    # Назначение инструкторов
    # Статистика по инструкторам
```

### 3. Панель инструктора

```python
@require_role(RoleType.INSTRUCTOR)
async def instructor_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель инструктора"""
    # Просмотр своих игр
    # Подтверждение/отмена
```

### 4. Суперадмин панель

```python
def require_superadmin(func):
    """Декоратор для суперадмина"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not is_superadmin(user.id):
            await update.callback_query.answer(
                "❌ Только для суперадминистратора",
                show_alert=True
            )
            return
        
        return await func(update, context)
    
    return wrapper


@require_superadmin
async def superadmin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель суперадминистратора"""
    # Управление клубами
    # Настройка тарифов
    # Шаблоны
    # Глобальная аналитика
```

---

## 🎯 План внедрения

### Этап 1: Роли и права (4-6 часов)
1. Создать новые модели (ClubRole, Permission)
2. Реализовать RBAC систему
3. Добавить декораторы проверки прав

### Этап 2: Тарифы (3-4 часа)
1. Создать модели тарифов
2. Реализовать проверку лимитов
3. Добавить демо-режим

### Этап 3: Административные панели (6-8 часов)
1. Панель владельца клуба
2. Панель старшего инструктора
3. Панель инструктора
4. Суперадмин панель

### Этап 4: Назначение инструкторов (3-4 часа)
1. Модель назначений
2. Уведомления
3. Подтверждения

### Этап 5: Управление услугами и ценами (4-6 часов)
1. CRUD услуг
2. Настройка способов расчета
3. Загрузка изображений

**Общее время:** 20-28 часов разработки

---

Готовы приступить к реализации? 🚀

