# 💻 Ролевая система - Детальная реализация

## 📦 Полные примеры кода

### 1. Функции работы с ролями

```python
# bot/database/rbac.py

from typing import Optional, List
from sqlalchemy.orm import Session
from bot.database.models import ClubRole, RoleType, Permission, ROLE_PERMISSIONS

def get_user_club_role(
    session: Session,
    user_id: int,
    club_id: int
) -> Optional[ClubRole]:
    """Получить роль пользователя в клубе"""
    return session.query(ClubRole).filter(
        ClubRole.user_id == user_id,
        ClubRole.club_id == club_id,
        ClubRole.active == True
    ).first()


def get_user_roles_in_club(
    session: Session,
    user_id: int,
    club_id: int
) -> List[ClubRole]:
    """Получить все роли пользователя в клубе"""
    return session.query(ClubRole).filter(
        ClubRole.user_id == user_id,
        ClubRole.club_id == club_id,
        ClubRole.active == True
    ).all()


def has_permission(
    session: Session,
    user_id: int,
    club_id: int,
    permission: Permission
) -> bool:
    """Проверить наличие права у пользователя"""
    # Суперадмин имеет все права
    if is_superadmin(user_id):
        return True
    
    roles = get_user_roles_in_club(session, user_id, club_id)
    
    for role in roles:
        if role.has_permission(permission):
            return True
    
    return False


def assign_role(
    session: Session,
    user_id: int,
    club_id: int,
    role: RoleType,
    assigned_by: int
) -> ClubRole:
    """Назначить роль пользователю"""
    # Проверяем существующую роль
    existing = session.query(ClubRole).filter(
        ClubRole.user_id == user_id,
        ClubRole.club_id == club_id,
        ClubRole.role == role
    ).first()
    
    if existing:
        existing.active = True
        existing.assigned_by = assigned_by
        existing.assigned_at = datetime.utcnow()
        session.commit()
        return existing
    
    # Создаем новую роль
    club_role = ClubRole(
        user_id=user_id,
        club_id=club_id,
        role=role,
        assigned_by=assigned_by
    )
    session.add(club_role)
    session.commit()
    
    return club_role


def revoke_role(
    session: Session,
    user_id: int,
    club_id: int,
    role: RoleType
) -> bool:
    """Отозвать роль у пользователя"""
    club_role = session.query(ClubRole).filter(
        ClubRole.user_id == user_id,
        ClubRole.club_id == club_id,
        ClubRole.role == role
    ).first()
    
    if club_role:
        club_role.active = False
        session.commit()
        return True
    
    return False


def get_club_members_by_role(
    session: Session,
    club_id: int,
    role: RoleType
) -> List[ClubRole]:
    """Получить всех членов клуба с определенной ролью"""
    return session.query(ClubRole).filter(
        ClubRole.club_id == club_id,
        ClubRole.role == role,
        ClubRole.active == True
    ).all()


def get_all_instructors(session: Session, club_id: int) -> List[ClubRole]:
    """Получить всех инструкторов клуба"""
    return session.query(ClubRole).filter(
        ClubRole.club_id == club_id,
        ClubRole.role.in_([RoleType.INSTRUCTOR, RoleType.SENIOR_INSTRUCTOR]),
        ClubRole.active == True
    ).all()


def is_superadmin(user_id: int) -> bool:
    """Проверить, является ли пользователь суперадмином"""
    from bot.config import SUPER_ADMINS
    return user_id in SUPER_ADMINS


def get_highest_role(
    session: Session,
    user_id: int,
    club_id: int
) -> Optional[RoleType]:
    """Получить самую высокую роль пользователя в клубе"""
    roles = get_user_roles_in_club(session, user_id, club_id)
    
    if not roles:
        return None
    
    # Приоритет ролей (от высшей к низшей)
    role_priority = [
        RoleType.CLUB_OWNER,
        RoleType.SENIOR_INSTRUCTOR,
        RoleType.INSTRUCTOR,
        RoleType.USER
    ]
    
    for priority_role in role_priority:
        for role in roles:
            if role.role == priority_role:
                return priority_role
    
    return RoleType.USER
```

### 2. Функции работы с подписками

```python
# bot/database/subscriptions.py

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from bot.database.models import ClubSubscription, PlanFeature, SubscriptionPlan

def get_club_subscription(
    session: Session,
    club_id: int
) -> Optional[ClubSubscription]:
    """Получить подписку клуба"""
    return session.query(ClubSubscription).filter_by(club_id=club_id).first()


def create_club_subscription(
    session: Session,
    club_id: int,
    plan: SubscriptionPlan = SubscriptionPlan.FREE,
    is_demo: bool = False
) -> ClubSubscription:
    """Создать подписку для клуба"""
    subscription = ClubSubscription(
        club_id=club_id,
        plan=plan,
        is_demo=is_demo
    )
    
    if is_demo:
        subscription.demo_started_at = datetime.utcnow()
        subscription.demo_ends_at = datetime.utcnow() + timedelta(days=14)
    
    session.add(subscription)
    session.commit()
    
    return subscription


def upgrade_subscription(
    session: Session,
    club_id: int,
    new_plan: SubscriptionPlan
) -> ClubSubscription:
    """Обновить план подписки"""
    subscription = get_club_subscription(session, club_id)
    
    if not subscription:
        return create_club_subscription(session, club_id, new_plan)
    
    subscription.plan = new_plan
    subscription.is_demo = False
    subscription.subscription_started_at = datetime.utcnow()
    
    session.commit()
    
    return subscription


def check_and_expire_demos(session: Session):
    """Проверить и деактивировать истекшие демо-подписки"""
    now = datetime.utcnow()
    
    expired_demos = session.query(ClubSubscription).filter(
        ClubSubscription.is_demo == True,
        ClubSubscription.demo_ends_at < now
    ).all()
    
    for subscription in expired_demos:
        subscription.is_demo = False
        subscription.plan = SubscriptionPlan.FREE
        subscription.demo_ends_at = None
    
    if expired_demos:
        session.commit()
    
    return len(expired_demos)


def can_perform_action(
    session: Session,
    club_id: int,
    action: str
) -> tuple[bool, str]:
    """
    Проверить возможность выполнения действия в рамках тарифа
    
    Returns:
        (can_perform, error_message)
    """
    subscription = get_club_subscription(session, club_id)
    
    if not subscription:
        return False, "Нет активной подписки"
    
    if not subscription.is_active():
        return False, "Подписка истекла"
    
    features = subscription.get_plan_features(session)
    
    # Проверка лимитов в зависимости от действия
    if action == 'add_field':
        if not subscription.can_add_field(session):
            return False, f"Достигнут лимит площадок ({features.max_fields}). Улучшите тариф."
    
    elif action == 'add_instructor':
        if not subscription.can_add_instructor(session):
            return False, f"Достигнут лимит инструкторов ({features.max_instructors}). Улучшите тариф."
    
    elif action == 'upload_image':
        if features.max_images and subscription.current_images_count >= features.max_images:
            return False, f"Достигнут лимит изображений ({features.max_images}). Улучшите тариф."
    
    elif action == 'sms_notification':
        if not features.sms_notifications:
            return False, "SMS-уведомления доступны в тарифах Basic и Premium."
    
    return True, ""


def increment_usage(
    session: Session,
    club_id: int,
    metric: str,
    amount: int = 1
):
    """Увеличить счетчик использования"""
    subscription = get_club_subscription(session, club_id)
    
    if not subscription:
        return
    
    if metric == 'fields':
        subscription.current_fields_count += amount
    elif metric == 'instructors':
        subscription.current_instructors_count += amount
    elif metric == 'bookings':
        subscription.current_month_bookings += amount
    elif metric == 'images':
        subscription.current_images_count += amount
    
    session.commit()


def decrement_usage(
    session: Session,
    club_id: int,
    metric: str,
    amount: int = 1
):
    """Уменьшить счетчик использования"""
    subscription = get_club_subscription(session, club_id)
    
    if not subscription:
        return
    
    if metric == 'fields':
        subscription.current_fields_count = max(0, subscription.current_fields_count - amount)
    elif metric == 'instructors':
        subscription.current_instructors_count = max(0, subscription.current_instructors_count - amount)
    elif metric == 'images':
        subscription.current_images_count = max(0, subscription.current_images_count - amount)
    
    session.commit()


def reset_monthly_counters(session: Session):
    """Сбросить месячные счетчики (запускать 1-го числа каждого месяца)"""
    session.query(ClubSubscription).update(
        {ClubSubscription.current_month_bookings: 0}
    )
    session.commit()
```

### 3. Функции назначения инструкторов

```python
# bot/database/assignments.py

from sqlalchemy.orm import Session
from bot.database.models import InstructorAssignment, Booking

def assign_instructor_to_booking(
    session: Session,
    booking_id: int,
    instructor_id: int,
    assigned_by: int,
    notes: str = None
) -> InstructorAssignment:
    """Назначить инструктора на игру"""
    # Проверяем существующее назначение
    existing = session.query(InstructorAssignment).filter_by(
        booking_id=booking_id
    ).first()
    
    if existing:
        # Обновляем существующее
        existing.instructor_id = instructor_id
        existing.assigned_by = assigned_by
        existing.assigned_at = datetime.utcnow()
        existing.status = 'pending'
        existing.notes = notes
        session.commit()
        return existing
    
    # Получаем club_id из бронирования
    booking = session.query(Booking).join(Field).join(Location).filter(
        Booking.id == booking_id
    ).first()
    
    # Создаем новое назначение
    assignment = InstructorAssignment(
        booking_id=booking_id,
        instructor_id=instructor_id,
        club_id=booking.field.location.club_id,
        assigned_by=assigned_by,
        notes=notes
    )
    
    session.add(assignment)
    session.commit()
    
    return assignment


def get_instructor_assignments(
    session: Session,
    instructor_id: int,
    club_id: int,
    status: str = None
) -> List[InstructorAssignment]:
    """Получить назначения инструктора"""
    query = session.query(InstructorAssignment).filter(
        InstructorAssignment.instructor_id == instructor_id,
        InstructorAssignment.club_id == club_id
    )
    
    if status:
        query = query.filter(InstructorAssignment.status == status)
    
    return query.order_by(InstructorAssignment.assigned_at.desc()).all()


def get_booking_assignment(
    session: Session,
    booking_id: int
) -> Optional[InstructorAssignment]:
    """Получить назначение для бронирования"""
    return session.query(InstructorAssignment).filter_by(
        booking_id=booking_id
    ).first()


def confirm_assignment(
    session: Session,
    assignment_id: int,
    instructor_id: int
) -> bool:
    """Инструктор подтверждает назначение"""
    assignment = session.query(InstructorAssignment).filter_by(
        id=assignment_id,
        instructor_id=instructor_id
    ).first()
    
    if not assignment:
        return False
    
    assignment.status = 'confirmed'
    assignment.confirmed_at = datetime.utcnow()
    session.commit()
    
    return True


def decline_assignment(
    session: Session,
    assignment_id: int,
    instructor_id: int
) -> bool:
    """Инструктор отклоняет назначение"""
    assignment = session.query(InstructorAssignment).filter_by(
        id=assignment_id,
        instructor_id=instructor_id
    ).first()
    
    if not assignment:
        return False
    
    assignment.status = 'declined'
    session.commit()
    
    return True


def get_unassigned_bookings(
    session: Session,
    club_id: int,
    from_date: date = None
) -> List[Booking]:
    """Получить бронирования без назначенных инструкторов"""
    if from_date is None:
        from_date = date.today()
    
    # Подзапрос для ID бронирований с назначениями
    assigned_bookings = session.query(InstructorAssignment.booking_id).subquery()
    
    # Основной запрос
    return session.query(Booking).join(Field).join(Location).filter(
        Location.club_id == club_id,
        Booking.date >= from_date,
        Booking.status == BookingStatus.CONFIRMED,
        ~Booking.id.in_(assigned_bookings)
    ).order_by(Booking.date, Booking.start_time).all()
```

### 4. Handlers для владельца клуба

```python
# bot/handlers/club_owner.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.rbac import require_permission, require_role
from bot.database.models import Permission, RoleType

@require_role(RoleType.CLUB_OWNER)
async def manage_roles_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления ролями"""
    query = update.callback_query
    await query.answer()
    
    club_id = context.user_data['club_id']
    
    with get_session() as session:
        # Получаем статистику по ролям
        owners = len(get_club_members_by_role(session, club_id, RoleType.CLUB_OWNER))
        seniors = len(get_club_members_by_role(session, club_id, RoleType.SENIOR_INSTRUCTOR))
        instructors = len(get_club_members_by_role(session, club_id, RoleType.INSTRUCTOR))
    
    text = f"""
👥 <b>Управление ролями</b>

<b>Текущий состав:</b>
• Владельцы: {owners}
• Старшие инструкторы: {seniors}
• Инструкторы: {instructors}

Выберите действие:
"""
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить старшего инструктора", callback_data="add_senior")],
        [InlineKeyboardButton("➕ Добавить инструктора", callback_data="add_instructor")],
        [InlineKeyboardButton("📋 Список инструкторов", callback_data="list_instructors")],
        [InlineKeyboardButton("« Назад", callback_data="owner_panel")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_permission(Permission.MANAGE_CLUB_ROLES)
async def add_instructor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления инструктора"""
    query = update.callback_query
    await query.answer()
    
    # Определяем роль из callback_data
    role_type = RoleType.SENIOR_INSTRUCTOR if query.data == "add_senior" else RoleType.INSTRUCTOR
    context.user_data['adding_role'] = role_type
    
    role_name = "старшего инструктора" if role_type == RoleType.SENIOR_INSTRUCTOR else "инструктора"
    
    text = f"""
➕ <b>Добавление {role_name}</b>

Отправьте username пользователя Telegram (например: @username) или его ID.

<i>Для отмены используйте кнопку ниже</i>
"""
    
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="manage_roles")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADDING_ROLE


async def receive_user_for_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить user_id для назначения роли"""
    user_input = update.message.text.strip()
    
    # Парсим ввод
    if user_input.startswith('@'):
        # Username - нужно попросить пользователя начать диалог с ботом
        username = user_input[1:]
        
        await update.message.reply_text(
            f"⚠️ Для добавления по username, пользователь @{username} должен "
            f"сначала начать диалог с ботом (/start).\n\n"
            f"Попросите его это сделать, затем повторите попытку."
        )
        return ADDING_ROLE
    
    elif user_input.isdigit():
        # Telegram ID
        user_id = int(user_input)
    else:
        await update.message.reply_text(
            "❌ Неверный формат. Отправьте @username или числовой ID."
        )
        return ADDING_ROLE
    
    # Назначаем роль
    club_id = context.user_data['club_id']
    role_type = context.user_data['adding_role']
    
    with get_session() as session:
        try:
            assign_role(
                session,
                user_id=user_id,
                club_id=club_id,
                role=role_type,
                assigned_by=update.effective_user.id
            )
            
            # Инкремент счетчика инструкторов если нужно
            if role_type in [RoleType.INSTRUCTOR, RoleType.SENIOR_INSTRUCTOR]:
                increment_usage(session, club_id, 'instructors')
            
            role_name = "старшим инструктором" if role_type == RoleType.SENIOR_INSTRUCTOR else "инструктором"
            
            await update.message.reply_text(
                f"✅ Пользователь {user_id} назначен {role_name}!"
            )
            
            # Уведомляем нового инструктора
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Вы назначены {role_name} в клубе!"
                )
            except:
                pass
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка при назначении роли: {e}"
            )
    
    # Возвращаемся в меню
    await manage_roles_menu(update, context)
    
    return ConversationHandler.END


@require_permission(Permission.MANAGE_SERVICES)
async def manage_services_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления услугами"""
    query = update.callback_query
    await query.answer()
    
    club_id = context.user_data['club_id']
    
    with get_session() as session:
        services = session.query(Service).filter_by(
            club_id=club_id,
            active=True
        ).all()
        
        club = session.query(Club).filter_by(id=club_id).first()
        pricing_mode = club.pricing_mode
    
    text = f"""
💰 <b>Управление услугами</b>

<b>Текущий режим расчета:</b> {PRICING_MODES[pricing_mode]}

<b>Активные услуги ({len(services)}):</b>
"""
    
    for service in services:
        text += f"\n• {service.name} - {service.price}₽"
        if service.duration_hours:
            text += f" ({service.duration_hours}ч)"
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Изменить режим расчета", callback_data="change_pricing_mode")],
        [InlineKeyboardButton("➕ Добавить услугу", callback_data="add_service")],
        [InlineKeyboardButton("📋 Редактировать услуги", callback_data="edit_services")],
        [InlineKeyboardButton("« Назад", callback_data="owner_panel")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_permission(Permission.UPLOAD_IMAGES)
async def upload_field_image_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало загрузки изображения"""
    query = update.callback_query
    await query.answer()
    
    field_id = int(query.data.split('_')[-1])
    club_id = context.user_data['club_id']
    
    # Проверяем лимит
    with get_session() as session:
        can_upload, error = can_perform_action(session, club_id, 'upload_image')
        
        if not can_upload:
            await query.answer(error, show_alert=True)
            return
    
    context.user_data['uploading_image_field'] = field_id
    
    text = """
📸 <b>Загрузка изображения</b>

Отправьте фотографию площадки.

<i>Для отмены используйте кнопку ниже</i>
"""
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"field_{field_id}")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return UPLOADING_IMAGE


async def receive_field_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить изображение площадки"""
    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте фотографию")
        return UPLOADING_IMAGE
    
    field_id = context.user_data['uploading_image_field']
    club_id = context.user_data['club_id']
    
    # Берем самое большое фото
    photo = update.message.photo[-1]
    file_id = photo.file_id
    file_unique_id = photo.file_unique_id
    caption = update.message.caption or ""
    
    with get_session() as session:
        # Создаем запись об изображении
        image = FieldImage(
            field_id=field_id,
            club_id=club_id,
            file_id=file_id,
            file_unique_id=file_unique_id,
            caption=caption,
            uploaded_by=update.effective_user.id
        )
        session.add(image)
        
        # Инкремент счетчика
        increment_usage(session, club_id, 'images')
        
        session.commit()
    
    await update.message.reply_text("✅ Изображение успешно загружено!")
    
    # Возвращаемся к площадке
    # TODO: вызвать handler просмотра площадки
    
    return ConversationHandler.END
```

Продолжить с панелью инструктора и суперадмина?

