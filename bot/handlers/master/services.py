"""Управление услугами мастера"""
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    get_services_by_master,
    get_categories_by_master,
    create_service_category,
    get_category_by_id,
    get_or_create_predefined_category,
    create_service,
    get_service_by_id,
    update_service,
    delete_service,
)
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from bot.data.service_templates import get_predefined_categories_list, get_category_info, get_category_templates
from .common import (
    WAITING_CATEGORY_NAME,
    WAITING_CATEGORY,
    WAITING_TEMPLATE,
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_DURATION,
    WAITING_SERVICE_DESCRIPTION,
    WAITING_SERVICE_COOLING,
    WAITING_SERVICE_ADVANCED,
    WAITING_EDIT_SERVICE_NAME,
    WAITING_EDIT_SERVICE_PRICE,
    WAITING_EDIT_SERVICE_DURATION,
    WAITING_EDIT_SERVICE_COOLING,
)

logger = logging.getLogger(__name__)


async def master_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список услуг мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        # Получаем услуги и категории
        services = get_services_by_master(session, master.id, active_only=False)
        categories = get_categories_by_master(session, master.id)
        
        # Группируем услуги по категориям
        services_by_category = {}
        for svc in services:
            if svc.category:
                cat_name = svc.category.title
                cat_emoji = svc.category.emoji if svc.category.emoji else "📁"
                category_key = f"{cat_emoji} {cat_name}"
            else:
                category_key = "📁 Без категории"
            
            if category_key not in services_by_category:
                services_by_category[category_key] = []
            
            status_icon = "✅" if svc.active else "❌"
            services_by_category[category_key].append({
                'id': svc.id,
                'title': svc.title,
                'price': svc.price,
                'duration': svc.duration_mins,
                'active': svc.active,
                'status_icon': status_icon
            })
        
        # Формируем текст
        total_services = sum(len(svcs) for svcs in services_by_category.values())
        text = f"💼 <b>Ваши услуги</b> ({total_services})\n\n"
        
        if services_by_category:
            for category_key, svcs in services_by_category.items():
                text += f"<b>{category_key}:</b>\n"
                for svc in svcs:
                    text += f"  {svc['status_icon']} {svc['title']} — {svc['price']}₽ ({svc['duration']} мин)\n"
                text += "\n"
        else:
            text += "<i>У вас пока нет услуг. Добавьте первую услугу!</i>\n"
        
        text += get_impersonation_banner(context)
        
        # Формируем клавиатуру
        keyboard = []
        
        # Кнопки для каждой услуги
        for category_key, svcs in services_by_category.items():
            for svc in svcs:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{svc['status_icon']} {svc['title']}",
                        callback_data=f"edit_service_{svc['id']}"
                    )
                ])
        
        # Кнопки управления
        keyboard.append([InlineKeyboardButton("➕ Добавить услугу", callback_data="add_service")])
        keyboard.append([InlineKeyboardButton("📁 Добавить категорию", callback_data="add_category")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_menu")])
        
        if query:
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif update.message:
            await update.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def add_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление категории"""
    query = update.callback_query
    await query.answer()
    
    text = "📁 <b>Добавление категории</b>\n\nВведите название категории:"
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_services")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_CATEGORY_NAME


async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить название категории"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Название слишком короткое.")
        return WAITING_CATEGORY_NAME
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if master:
            # Извлекаем эмодзи из начала строки, если есть
            emoji_match = re.match(r'^([^\w\s]+)', text)
            emoji = emoji_match.group(1) if emoji_match else None
            
            if emoji:
                title = text[len(emoji):].strip()
            else:
                title = text
                emoji = "📁"
            
            category = create_service_category(session, master.id, title, emoji=emoji)
            await update.message.reply_text(f"✅ Категория <b>{emoji} {title}</b> добавлена!", parse_mode='HTML')
            await master_services(update, context)
    
    return ConversationHandler.END


async def add_service_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление услуги"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем данные предыдущего создания услуги
    service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
    for key in service_keys:
        del context.user_data[key]
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return ConversationHandler.END
        
        # Получаем предустановленные категории
        predefined_categories = get_predefined_categories_list()
        
        # Получаем пользовательские категории
        user_categories = get_categories_by_master(session, master.id)
        
        text = "💼 <b>Добавление услуги</b>\n\nВыберите категорию:"
        
        keyboard = []
        
        # Предустановленные категории
        for key, emoji, name in predefined_categories:
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {name}",
                    callback_data=f"service_category_predef_{key}"
                )
            ])
        
        # Пользовательские категории (сначала новые, потом старые)
        sorted_categories = sorted(user_categories, key=lambda x: x.id, reverse=True)
        for cat in sorted_categories:
            emoji = cat.emoji if cat.emoji else "📁"
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {cat.title}",
                    callback_data=f"service_category_{cat.id}"
                )
            ])
        
        # Кнопки "Другое" и "Отмена"
        keyboard.append([InlineKeyboardButton("➕ Другое", callback_data="service_category_custom")])
        keyboard.append([InlineKeyboardButton("« Отмена", callback_data="master_services")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_CATEGORY


async def service_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории при добавлении услуги"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return ConversationHandler.END
        
        # Определяем тип категории
        if data.startswith('service_category_predef_'):
            # Предустановленная категория
            category_key = data.replace('service_category_predef_', '')
            cat_info = get_category_info(category_key)
            
            if cat_info:
                # Получаем или создаем предустановленную категорию
                category = get_or_create_predefined_category(session, master.id, category_key)
                if category:
                    context.user_data['service_category_id'] = category.id
                    context.user_data['service_category_name'] = category.title
                else:
                    await query.message.edit_text("❌ Ошибка создания категории")
                    return ConversationHandler.END
            else:
                await query.message.edit_text("❌ Категория не найдена")
                return ConversationHandler.END
        elif data.startswith('service_category_') and data != 'service_category_custom':
            # Пользовательская категория
            try:
                category_id = int(data.replace('service_category_', ''))
                category = get_category_by_id(session, category_id)
                if category and category.master_account_id == master.id:
                    context.user_data['service_category_id'] = category.id
                    context.user_data['service_category_name'] = category.title
                else:
                    await query.message.edit_text("❌ Категория не найдена")
                    return ConversationHandler.END
            except ValueError:
                await query.message.edit_text("❌ Ошибка обработки категории")
                return ConversationHandler.END
        elif data == 'service_category_custom':
            # Создание новой категории
            context.user_data['service_creating_category'] = True
            await query.message.edit_text(
                "📁 Введите название новой категории:\n\n"
                "<i>Рекомендуем использовать эмодзи в названии для лучшей визуализации (например: 💅 Маникюр)</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Отмена", callback_data="master_services")
                ]])
            )
            return WAITING_CATEGORY_NAME
        
        # Получаем шаблоны для категории
        category_key = data.replace('service_category_predef_', '').replace('service_category_', '')
        if category_key and category_key != 'custom':
            templates = get_category_templates(category_key)
        else:
            templates = []
        
        category_name = context.user_data.get('service_category_name', '')
        text = f"💼 <b>Добавление услуги</b>\n\n"
        text += f"Категория: <b>{category_name}</b>\n\n"
        
        if templates:
            text += "Выберите шаблон или создайте с нуля:"
            keyboard = []
            
            for template in templates:
                keyboard.append([
                    InlineKeyboardButton(
                        template['name'],
                        callback_data=f"service_template_{template['name']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("➕ Создать с нуля", callback_data="service_template_none")])
            keyboard.append([InlineKeyboardButton("« Назад", callback_data="add_service")])
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING_TEMPLATE
        else:
            text += "Введите название услуги:"
            keyboard = [[InlineKeyboardButton("« Назад", callback_data="add_service")]]
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING_SERVICE_NAME


async def service_template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора шаблона"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    template_name = data.replace('service_template_', '')
    
    if template_name == 'none':
        # Пользователь выбрал "создать с нуля"
        text = "💼 <b>Добавление услуги</b>\n\nВведите название услуги:"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="add_service")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_NAME
    else:
        # Используем шаблон (пока просто сохраняем название)
        context.user_data['service_name'] = template_name
        text = f"💰 Введите цену услуги (в рублях, только число):"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_template")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_PRICE


async def receive_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить название услуги"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Минимум 2 символа.")
        return WAITING_SERVICE_NAME
    
    if len(text) > 100:
        await update.message.reply_text("❌ Название слишком длинное. Максимум 100 символов.")
        return WAITING_SERVICE_NAME
    
    context.user_data['service_name'] = text
    
    reply_text = "💰 Введите цену услуги (в рублях, только число):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]]
    
    await update.message.reply_text(
        reply_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_PRICE


async def receive_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить цену услуги"""
    try:
        price = float(update.message.text.strip().replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text("❌ Цена должна быть больше 0. Попробуйте снова:")
            return WAITING_SERVICE_PRICE
        
        if price > 1000000:
            await update.message.reply_text("❌ Цена слишком большая. Попробуйте снова:")
            return WAITING_SERVICE_PRICE
        
        context.user_data['service_price'] = price
        
        # Предлагаем выбрать длительность
        text = "⏱ Выберите длительность услуги (в минутах):"
        keyboard = [
            [InlineKeyboardButton("30 мин", callback_data="service_duration_30")],
            [InlineKeyboardButton("60 мин", callback_data="service_duration_60")],
            [InlineKeyboardButton("90 мин", callback_data="service_duration_90")],
            [InlineKeyboardButton("120 мин", callback_data="service_duration_120")],
            [InlineKeyboardButton("Другое (ввести вручную)", callback_data="service_duration_manual")],
            [InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_DURATION
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_SERVICE_PRICE


async def service_duration_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора длительности"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    duration_str = data.replace('service_duration_', '')
    
    if duration_str == 'manual':
        text = "⏱ Введите длительность услуги (в минутах, только число):"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_price")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_DURATION
    else:
        try:
            duration = int(duration_str)
            context.user_data['service_duration'] = duration
            return await service_advanced_settings(update, context)
        except ValueError:
            await query.message.edit_text("❌ Ошибка обработки длительности")
            return WAITING_SERVICE_DURATION


async def receive_service_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить длительность услуги"""
    try:
        duration = int(update.message.text.strip())
        
        if duration <= 0:
            await update.message.reply_text("❌ Длительность должна быть больше 0. Попробуйте снова:")
            return WAITING_SERVICE_DURATION
        
        if duration > 1440:
            await update.message.reply_text("❌ Длительность слишком большая (максимум 1440 минут). Попробуйте снова:")
            return WAITING_SERVICE_DURATION
        
        context.user_data['service_duration'] = duration
        return await service_advanced_settings(update, context)
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_SERVICE_DURATION


async def service_advanced_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать расширенные настройки"""
    query = update.callback_query if hasattr(update, 'callback_query') and update.callback_query else None
    
    duration = context.user_data.get('service_duration', 60)
    cooling = context.user_data.get('service_cooling', 0)
    
    text = f"⚙️ <b>Расширенные настройки</b>\n\n"
    text += f"Длительность: <b>{duration} мин</b>\n"
    text += f"Время охлаждения: <b>{cooling} мин</b>\n\n"
    text += "Выберите действие:"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить длительность", callback_data="service_change_duration")],
        [InlineKeyboardButton("🔄 Настроить время охлаждения", callback_data="service_set_cooling")],
        [InlineKeyboardButton("✅ Сохранить с настройками по умолчанию", callback_data="service_save_default")],
        [InlineKeyboardButton("« Назад", callback_data="service_back_to_price")]
    ]
    
    if query:
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_SERVICE_ADVANCED


async def service_change_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить длительность"""
    query = update.callback_query
    await query.answer()
    
    text = "⏱ Выберите длительность услуги (в минутах):"
    keyboard = [
        [InlineKeyboardButton("30 мин", callback_data="service_duration_30")],
        [InlineKeyboardButton("60 мин", callback_data="service_duration_60")],
        [InlineKeyboardButton("90 мин", callback_data="service_duration_90")],
        [InlineKeyboardButton("120 мин", callback_data="service_duration_120")],
        [InlineKeyboardButton("Другое (ввести вручную)", callback_data="service_duration_manual")],
        [InlineKeyboardButton("« Назад", callback_data="service_back_to_advanced")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_DURATION


async def receive_service_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время охлаждения"""
    try:
        cooling = int(update.message.text.strip())
        
        if cooling < 0:
            await update.message.reply_text("❌ Время охлаждения не может быть отрицательным. Попробуйте снова:")
            return WAITING_SERVICE_COOLING
        
        if cooling > 1440:
            await update.message.reply_text("❌ Время охлаждения слишком большое. Попробуйте снова:")
            return WAITING_SERVICE_COOLING
        
        context.user_data['service_cooling'] = cooling
        return await create_service_from_data(update, context)
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_SERVICE_COOLING


async def service_set_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настроить время охлаждения"""
    query = update.callback_query
    await query.answer()
    
    text = "🔄 Введите время охлаждения между записями (в минутах, только число, по умолчанию 0):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_advanced")]]
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_COOLING


async def service_save_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить услугу с настройками по умолчанию"""
    query = update.callback_query
    await query.answer()
    
    # Устанавливаем значения по умолчанию
    if 'service_cooling' not in context.user_data:
        context.user_data['service_cooling'] = 0
    
    return await create_service_from_data(update, context)


async def create_service_from_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать услугу из собранных данных"""
    query = update.callback_query if hasattr(update, 'callback_query') and update.callback_query else None
    
    # Получаем данные
    name = context.user_data.get('service_name')
    price = context.user_data.get('service_price')
    duration = context.user_data.get('service_duration')
    cooling = context.user_data.get('service_cooling', 0)
    category_id = context.user_data.get('service_category_id')
    description = context.user_data.get('service_description', '')
    
    if not name or not price or not duration:
        error_text = "❌ Ошибка: не все данные заполнены"
        if query:
            await query.message.edit_text(error_text)
        else:
            await update.message.reply_text(error_text)
        return ConversationHandler.END
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            error_text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return ConversationHandler.END
        
        # Создаем услугу
        service = create_service(
            session=session,
            master_id=master.id,
            title=name,
            price=price,
            duration=duration,
            cooling=cooling,
            category_id=category_id,
            description=description
        )
        
        # Очищаем данные
        service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
        for key in service_keys:
            del context.user_data[key]
        
        success_text = f"✅ Услуга <b>{name}</b> успешно добавлена!"
        keyboard = [
            [InlineKeyboardButton("💼 Мои услуги", callback_data="master_services")],
            [InlineKeyboardButton("➕ Добавить еще", callback_data="add_service")]
        ]
        
        if query:
            await query.message.edit_text(
                success_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                success_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    return ConversationHandler.END


async def receive_service_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить описание услуги"""
    description = update.message.text.strip()
    context.user_data['service_description'] = description
    return await create_service_from_data(update, context)


async def service_skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить описание"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['service_description'] = ''
    return await create_service_from_data(update, context)


# Функции навигации назад
async def service_back_to_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к вводу названия"""
    query = update.callback_query
    await query.answer()
    
    text = "💼 <b>Добавление услуги</b>\n\nВведите название услуги:"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="add_service")]]
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_NAME


async def service_back_to_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к вводу цены"""
    query = update.callback_query
    await query.answer()
    
    text = "💰 Введите цену услуги (в рублях, только число):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]]
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_PRICE


async def service_back_to_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к выбору шаблона"""
    query = update.callback_query
    await query.answer()
    
    # Перезапускаем выбор категории
    return await add_service_start(update, context)


async def service_back_to_advanced(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к расширенным настройкам"""
    return await service_advanced_settings(update, context)


# ===== Функции редактирования и удаления услуги =====

async def edit_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню редактирования услуги"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: edit_service_123
    service_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        # Формируем информацию об услуге
        category_name = service.category.title if service.category else "Без категории"
        status_icon = "✅" if service.active else "❌"
        
        text = f"✏️ <b>Редактирование услуги</b>\n\n"
        text += f"{status_icon} <b>{service.title}</b>\n"
        text += f"📁 Категория: {category_name}\n"
        text += f"💰 Цена: {service.price}₽\n"
        text += f"⏱ Длительность: {service.duration_mins} мин\n"
        text += f"🔄 Время охлаждения: {service.cooling_period_mins} мин\n"
        if service.description:
            text += f"📝 Описание: {service.description}\n"
        text += f"\n{get_impersonation_banner(context)}"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить название", callback_data=f"edit_service_name_{service_id}")],
            [InlineKeyboardButton("💰 Изменить цену", callback_data=f"edit_service_price_{service_id}")],
            [InlineKeyboardButton("⏱ Изменить длительность", callback_data=f"edit_service_duration_{service_id}")],
            [InlineKeyboardButton("🔄 Изменить время охлаждения", callback_data=f"edit_service_cooling_{service_id}")],
            [InlineKeyboardButton("🗑 Удалить услугу", callback_data=f"delete_service_confirm_{service_id}")],
            [InlineKeyboardButton("« Назад", callback_data="master_services")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def edit_service_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование названия услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'name'
        
        text = f"✏️ <b>Изменение названия услуги</b>\n\n"
        text += f"Текущее название: <b>{service.title}</b>\n\n"
        text += "Введите новое название:"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_NAME


async def receive_edit_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое название услуги"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Минимум 2 символа.")
        return WAITING_EDIT_SERVICE_NAME
    
    if len(text) > 100:
        await update.message.reply_text("❌ Название слишком длинное. Максимум 100 символов.")
        return WAITING_EDIT_SERVICE_NAME
    
    service_id = context.user_data.get('edit_service_id')
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await update.message.reply_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Обновляем название
        update_service(session, service_id, title=text)
        
        await update.message.reply_text(f"✅ Название изменено на: <b>{text}</b>", parse_mode='HTML')
        
        # Очищаем контекст
        context.user_data.pop('edit_service_id', None)
        context.user_data.pop('edit_service_field', None)
        
        # Возвращаемся к меню редактирования
        query = update.callback_query
        if not query:
            # Создаем фиктивный callback_query
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
        
        await edit_service(update, context)
    
    return ConversationHandler.END


async def edit_service_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование цены услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'price'
        
        text = f"💰 <b>Изменение цены услуги</b>\n\n"
        text += f"Текущая цена: <b>{service.price}₽</b>\n\n"
        text += "Введите новую цену (в рублях, только число):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_PRICE


async def receive_edit_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новую цену услуги"""
    try:
        price = float(update.message.text.strip().replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text("❌ Цена должна быть больше 0. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_PRICE
        
        if price > 1000000:
            await update.message.reply_text("❌ Цена слишком большая. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_PRICE
        
        service_id = context.user_data.get('edit_service_id')
        
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            service = get_service_by_id(session, service_id)
            
            if not service or service.master_account_id != master.id:
                await update.message.reply_text("❌ Услуга не найдена")
                return ConversationHandler.END
            
            # Обновляем цену
            update_service(session, service_id, price=price)
            
            await update.message.reply_text(f"✅ Цена изменена на: <b>{price}₽</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
            await edit_service(update, context)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_PRICE


async def edit_service_duration_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование длительности услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'duration'
        
        text = f"⏱ <b>Изменение длительности услуги</b>\n\n"
        text += f"Текущая длительность: <b>{service.duration_mins} мин</b>\n\n"
        text += "Введите новую длительность (в минутах, только число):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_DURATION


async def receive_edit_service_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новую длительность услуги"""
    try:
        duration = int(update.message.text.strip())
        
        if duration <= 0:
            await update.message.reply_text("❌ Длительность должна быть больше 0. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_DURATION
        
        if duration > 1440:
            await update.message.reply_text("❌ Длительность слишком большая (максимум 1440 минут). Попробуйте снова:")
            return WAITING_EDIT_SERVICE_DURATION
        
        service_id = context.user_data.get('edit_service_id')
        
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            service = get_service_by_id(session, service_id)
            
            if not service or service.master_account_id != master.id:
                await update.message.reply_text("❌ Услуга не найдена")
                return ConversationHandler.END
            
            # Обновляем длительность
            update_service(session, service_id, duration_mins=duration)
            
            await update.message.reply_text(f"✅ Длительность изменена на: <b>{duration} мин</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
            await edit_service(update, context)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_DURATION


async def edit_service_cooling_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование времени охлаждения услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        context.user_data['edit_service_id'] = service_id
        context.user_data['edit_service_field'] = 'cooling'
        
        text = f"🔄 <b>Изменение времени охлаждения</b>\n\n"
        text += f"Текущее время охлаждения: <b>{service.cooling_period_mins} мин</b>\n\n"
        text += "Введите новое время охлаждения (в минутах, только число, по умолчанию 0):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_COOLING


async def receive_edit_service_cooling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое время охлаждения услуги"""
    try:
        cooling = int(update.message.text.strip())
        
        if cooling < 0:
            await update.message.reply_text("❌ Время охлаждения не может быть отрицательным. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_COOLING
        
        if cooling > 1440:
            await update.message.reply_text("❌ Время охлаждения слишком большое. Попробуйте снова:")
            return WAITING_EDIT_SERVICE_COOLING
        
        service_id = context.user_data.get('edit_service_id')
        
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            service = get_service_by_id(session, service_id)
            
            if not service or service.master_account_id != master.id:
                await update.message.reply_text("❌ Услуга не найдена")
                return ConversationHandler.END
            
            # Обновляем время охлаждения
            update_service(session, service_id, cooling_period_mins=cooling)
            
            await update.message.reply_text(f"✅ Время охлаждения изменено на: <b>{cooling} мин</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования
            class FakeCallbackQuery:
                def __init__(self, message, service_id):
                    self.message = message
                    self.data = f"edit_service_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message, service_id)
            await edit_service(update, context)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_COOLING


async def delete_service_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        text = f"🗑 <b>Удаление услуги</b>\n\n"
        text += f"Вы уверены, что хотите удалить услугу <b>{service.title}</b>?\n\n"
        text += "⚠️ Это действие нельзя отменить!"
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_service_execute_{service_id}")],
            [InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def delete_service_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить удаление услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        service_title = service.title
        
        # Удаляем услугу
        if delete_service(session, service_id):
            text = f"✅ Услуга <b>{service_title}</b> успешно удалена!"
            keyboard = [[InlineKeyboardButton("💼 Мои услуги", callback_data="master_services")]]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.message.edit_text("❌ Ошибка при удалении услуги")

