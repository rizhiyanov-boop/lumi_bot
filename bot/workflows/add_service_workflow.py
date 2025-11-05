"""Workflow для добавления услуги - декларативное описание шагов"""
from bot.core.workflow import Workflow, Step, StepType, workflow_manager
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import get_session, get_master_by_telegram, get_categories_by_master
from bot.data.service_templates import get_predefined_categories_list, get_category_templates, get_category_info
from bot.database.db import get_or_create_predefined_category
import logging

logger = logging.getLogger(__name__)


def validate_price(price_str: str, context: ContextTypes.DEFAULT_TYPE) -> bool | str:
    """Валидация цены"""
    try:
        price = float(price_str)
        if price <= 0:
            return "❌ Цена должна быть больше 0. Попробуйте снова:"
        if price > 1000000:
            return "❌ Цена слишком большая. Попробуйте снова:"
        return True
    except ValueError:
        return "❌ Введите число. Попробуйте снова:"


def validate_duration(duration_str: str, context: ContextTypes.DEFAULT_TYPE) -> bool | str:
    """Валидация длительности"""
    try:
        duration = int(duration_str)
        if duration <= 0:
            return "❌ Длительность должна быть больше 0. Попробуйте снова:"
        if duration > 1440:  # 24 часа
            return "❌ Длительность слишком большая (максимум 1440 минут). Попробуйте снова:"
        return True
    except ValueError:
        return "❌ Введите число. Попробуйте снова:"


def validate_cooling(cooling_str: str, context: ContextTypes.DEFAULT_TYPE) -> bool | str:
    """Валидация времени охлаждения"""
    try:
        cooling = int(cooling_str)
        if cooling < 0:
            return "❌ Время охлаждения не может быть отрицательным. Попробуйте снова:"
        if cooling > 1440:
            return "❌ Время охлаждения слишком большое. Попробуйте снова:"
        return True
    except ValueError:
        return "❌ Введите число. Попробуйте снова:"


async def step_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик шага выбора категории"""
    query = update.callback_query
    if not query:
        return None
    
    from bot.handlers.master import get_master_telegram_id
    
    predefined_categories = get_predefined_categories_list()
    user_categories_data = []
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return None
        
        user_categories = get_categories_by_master(session, master.id)
        for cat in user_categories:
            if not cat.is_predefined:
                emoji = cat.emoji if cat.emoji else "📁"
                user_categories_data.append((cat.id, emoji, cat.title))
    
    # Формируем клавиатуру
    keyboard = []
    has_other = False
    
    for key, emoji, name in predefined_categories:
        keyboard.append([{
            'text': f"{emoji} {name}",
            'callback_data': f"workflow_callback_{key}"
        }])
        if key == "other":
            has_other = True
    
    if user_categories_data:
        for cat_id, emoji, cat_title in user_categories_data:
            keyboard.append([{
                'text': f"{emoji} {cat_title}",
                'callback_data': f"workflow_callback_user_{cat_id}"
            }])
    
    if not has_other:
        keyboard.append([{
            'text': "➕ Другое",
            'callback_data': "workflow_callback_custom"
        }])
    
    # Обновляем шаг с клавиатурой
    step = workflow_manager.workflows['add_service'].steps['category']
    step.keyboard = keyboard
    
    return None


async def step_category_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Обработчик callback выбора категории"""
    query = update.callback_query
    await query.answer()
    
    parts = callback_data.split('_')
    
    if len(parts) < 3:
        return None
    
    if parts[2] == 'custom' or (len(parts) >= 3 and parts[2] == 'other'):
        # Создание новой категории
        await query.message.edit_text(
            "➕ <b>Создание категории</b>\n\nВведите название новой категории:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Отмена", callback_data="workflow_cancel")
            ]])
        )
        context.user_data['workflow_step'] = 'category_name'
        return 'category_name'
    
    # Определяем следующий шаг на основе категории
    category_key = parts[2] if len(parts) > 2 else None
    if category_key:
        context.user_data['workflow_data']['category_key'] = category_key
        
        # Проверяем есть ли шаблоны
        templates = get_category_templates(category_key) if category_key else []
        if templates:
            context.user_data['workflow_step'] = 'template'
        else:
            context.user_data['workflow_step'] = 'name'
    
    return None


async def on_complete_add_service(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict):
    """Действие при завершении добавления услуги"""
    from bot.handlers.master import get_master_telegram_id, create_service
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if not master:
            logger.error("Master not found in on_complete")
            return
        
        try:
            service = create_service(
                session=session,
                master_id=master.id,
                title=data.get('name', ''),
                price=float(data.get('price', 0)),
                duration=int(data.get('duration', 0)),
                cooling=int(data.get('cooling', 0)),
                category_id=data.get('category_id'),
                description=data.get('description', '')
            )
            
            logger.info(f"Service '{service.title}' created successfully")
        except Exception as e:
            logger.error(f"Error creating service: {e}", exc_info=True)
            raise


def create_add_service_workflow() -> Workflow:
    """Создать workflow для добавления услуги"""
    
    workflow = Workflow(
        name="add_service",
        entry_point="category",
        steps={
            "category": Step(
                id="category",
                type=StepType.CALLBACK,
                title="Выбор категории",
                message="➕ <b>Добавление услуги</b>\n\nВыберите категорию для новой услуги:",
                handler=step_category_handler,
                data_key="category_id",
                next_step="check_template",
                keyboard=[]  # Будет заполнено в handler
            ),
            "check_template": Step(
                id="check_template",
                type=StepType.CONDITIONAL,
                title="Проверка шаблонов",
                message="",
                condition=lambda u, c: "template" if get_category_templates(c.user_data['workflow_data'].get('category_key', '')) else "name",
                next_step=None
            ),
            "template": Step(
                id="template",
                type=StepType.CALLBACK,
                title="Выбор шаблона",
                message="➕ <b>Добавление услуги</b>\n\nВыберите шаблон или создайте услугу с нуля:",
                data_key="template_index",
                next_step="price"
            ),
            "name": Step(
                id="name",
                type=StepType.INPUT,
                title="Название услуги",
                message="➕ <b>Добавление услуги</b>\n\nВведите название услуги:",
                validator=lambda text, ctx: True if text and len(text) <= 100 else "❌ Название должно быть не пустым и не более 100 символов. Попробуйте снова:",
                data_key="name",
                next_step="price"
            ),
            "price": Step(
                id="price",
                type=StepType.INPUT,
                title="Цена услуги",
                message="💰 Введите цену услуги (в рублях, только число):",
                validator=validate_price,
                data_key="price",
                next_step="duration"
            ),
            "duration": Step(
                id="duration",
                type=StepType.INPUT,
                title="Длительность",
                message="⏱ Введите длительность услуги (в минутах, только число):",
                validator=validate_duration,
                data_key="duration",
                next_step="cooling"
            ),
            "cooling": Step(
                id="cooling",
                type=StepType.INPUT,
                title="Время охлаждения",
                message="🔄 Введите время охлаждения между записями (в минутах, только число, по умолчанию 0):",
                validator=validate_cooling,
                data_key="cooling",
                default_value=0,
                next_step=None  # Завершение
            )
        },
        fallbacks=["cancel"],
        context_keys=["service_category_id", "service_category_key", "service_category_name", "service_category_emoji"]
    )
    
    workflow.on_complete = on_complete_add_service
    
    return workflow

