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
    WAITING_EDIT_SERVICE_DESCRIPTION,
    WAITING_SERVICE_PORTFOLIO_PHOTO,
)

logger = logging.getLogger(__name__)


async def _send_onboarding_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, session, master):
    """Вспомогательная функция для отправки экрана анбординга"""
    from .onboarding import get_onboarding_progress, get_onboarding_message, get_onboarding_keyboard
    
    progress_info = get_onboarding_progress(session, master)
    text = get_onboarding_message(progress_info, master.name)
    text += get_impersonation_banner(context)
    keyboard = get_onboarding_keyboard(progress_info)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def _show_new_service_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session, service_id, master):
    """Показать меню для только что созданной услуги с опциями"""
    service = get_service_by_id(session, service_id)
    
    if not service:
        return
    
    # Получаем информацию о портфолио услуги
    from bot.database.db import get_portfolio_photos, get_portfolio_limit
    portfolio_photos = get_portfolio_photos(session, service_id)
    portfolio_count, portfolio_max = get_portfolio_limit(session, service_id)
    
    text = f"💼 <b>{service.title}</b>\n\n"
    text += "Вы можете:\n"
    text += "• Добавить описание (сгенерировать через ИИ или ввести вручную)\n"
    text += "• Добавить фото в портфолио\n"
    text += "• Продолжить без изменений"
    
    keyboard = []
    
    # Проверяем, было ли уже сгенерировано описание через ИИ
    if not service.description_ai_generated:
        keyboard.append([InlineKeyboardButton("✨ Сгенерировать описание", callback_data=f"new_service_generate_description_{service_id}")])
    
    keyboard.append([InlineKeyboardButton("✏️ Ввести описание вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")])
    keyboard.append([InlineKeyboardButton(f"📸 Добавить портфолио ({portfolio_count}/{portfolio_max})", callback_data=f"service_portfolio_{service_id}")])
    keyboard.append([InlineKeyboardButton("➡️ Продолжить", callback_data=f"service_created_next_{service_id}")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _send_edit_service_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session, service_id):
    """Вспомогательная функция для отправки меню редактирования услуги"""
    from bot.utils.currency import format_price
    
    master = get_master_by_telegram(session, get_master_telegram_id(update, context))
    service = get_service_by_id(session, service_id)
    
    if not service or service.master_account_id != master.id:
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text("❌ Услуга не найдена")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Услуга не найдена"
            )
        return
    
    # Формируем информацию об услуге
    category_name = service.category.title if service.category else "Без категории"
    status_icon = "✅" if service.active else "❌"
    price_formatted = format_price(service.price, master.currency)
    
    text = f"✏️ <b>Редактирование услуги</b>\n\n"
    text += f"{status_icon} <b>{service.title}</b>\n"
    text += f"📁 Категория: {category_name}\n"
    text += f"💰 Цена: {price_formatted}\n"
    text += f"⏱ Длительность: {service.duration_mins} мин\n"
    text += f"🔄 Время охлаждения: {service.cooling_period_mins} мин\n"
    if service.description:
        text += f"📝 Описание: {service.description}\n"
    text += f"\n{get_impersonation_banner(context)}"
    
    # Получаем информацию о портфолио услуги
    from bot.database.db import get_portfolio_photos, get_portfolio_limit
    portfolio_photos = get_portfolio_photos(session, service_id)
    portfolio_count, portfolio_max = get_portfolio_limit(session, service_id)
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить название", callback_data=f"edit_service_name_{service_id}")],
        [InlineKeyboardButton("💰 Изменить цену", callback_data=f"edit_service_price_{service_id}")],
        [InlineKeyboardButton("⏱ Изменить длительность", callback_data=f"edit_service_duration_{service_id}")],
        [InlineKeyboardButton("🔄 Изменить время охлаждения", callback_data=f"edit_service_cooling_{service_id}")]
    ]
    
    # Показываем кнопку генерации описания только если оно еще не было сгенерировано через ИИ
    if not service.description_ai_generated:
        keyboard.append([InlineKeyboardButton("✨ Сгенерировать описание", callback_data=f"edit_service_generate_description_{service_id}")])
    
    keyboard.append([InlineKeyboardButton("📝 Изменить описание", callback_data=f"edit_service_description_{service_id}")])
    keyboard.append([InlineKeyboardButton(f"📸 Портфолио ({portfolio_count}/{portfolio_max})", callback_data=f"service_portfolio_{service_id}")])
    keyboard.append([InlineKeyboardButton("🗑 Удалить услугу", callback_data=f"delete_service_confirm_{service_id}")])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_services")])
    
    # Если это callback из меню новой услуги, проверяем специальный флаг
    is_new_service = context.user_data.get('is_newly_created_service', False) and context.user_data.get('newly_created_service_id') == service_id
    if is_new_service:
        # Для новой услуги добавляем кнопку "Продолжить"
        keyboard.insert(-1, [InlineKeyboardButton("➡️ Продолжить", callback_data=f"service_created_next_{service_id}")])
    
    # Если есть callback_query, редактируем сообщение, иначе отправляем новое
    if hasattr(update, 'callback_query') and update.callback_query:
        try:
            await update.callback_query.message.edit_text(
                text=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            # Если не удалось отредактировать (например, сообщение не изменилось), отправляем новое
            logger.warning(f"Could not edit message, sending new one: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    elif hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            text=text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


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
        
        # Проверяем прогресс анбординга
        from .onboarding import get_onboarding_progress, get_onboarding_header, get_next_step_button
        
        progress_info = get_onboarding_progress(session, master)
        onboarding_header = get_onboarding_header(session, master)
        next_button = get_next_step_button(progress_info)
        
        # Формируем текст
        text = onboarding_header if onboarding_header else ""
        total_services = sum(len(svcs) for svcs in services_by_category.values())
        text += f"💼 <b>Ваши услуги</b> ({total_services})\n\n"
        
        # Получаем функцию форматирования цены
        from bot.utils.currency import format_price
        
        if services_by_category:
            for category_key, svcs in services_by_category.items():
                text += f"<b>{category_key}:</b>\n"
                for svc in svcs:
                    price_formatted = format_price(svc['price'], master.currency)
                    text += f"  {svc['status_icon']} {svc['title']} — {price_formatted} ({svc['duration']} мин)\n"
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
        
        # Добавляем кнопку "Далее" или "Назад" в зависимости от статуса анбординга
        if next_button:
            keyboard.append([next_button])
        else:
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
        
        # Предустановленные категории (исключаем "other", так как добавим отдельную кнопку)
        for key, emoji, name in predefined_categories:
            if key != "other":  # Исключаем категорию "Другое" из предустановленных
                keyboard.append([
                    InlineKeyboardButton(
                        f"{emoji} {name}",
                        callback_data=f"service_category_predef_{key}"
                    )
                ])
        
        # Пользовательские категории (исключаем предустановленные, чтобы избежать дублирования)
        # Сначала новые, потом старые
        user_only_categories = [cat for cat in user_categories if not cat.is_predefined]
        sorted_categories = sorted(user_only_categories, key=lambda x: x.id, reverse=True)
        for cat in sorted_categories:
            emoji = cat.emoji if cat.emoji else "📁"
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {cat.title}",
                    callback_data=f"service_category_{cat.id}"
                )
            ])
        
        # Кнопка "Другое" (предпоследняя) и "Отмена" (последняя)
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
        
        # Получаем валюту мастера для отображения
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            if not master:
                currency_name = 'рублях'
            else:
                # Обновляем объект из базы данных, чтобы получить актуальную валюту
                session.refresh(master)
                from bot.utils.currency import CURRENCY_NAMES_RU_PREPOSITIONAL
                currency_name = CURRENCY_NAMES_RU_PREPOSITIONAL.get(master.currency or 'RUB', 'рублях')
        
        text = f"💰 Введите цену услуги (в {currency_name}, только число):"
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
    
    # Получаем валюту мастера для отображения
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if not master:
            currency_name = 'рублях'
        else:
            # Обновляем объект из базы данных, чтобы получить актуальную валюту
            session.refresh(master)
            from bot.utils.currency import CURRENCY_NAMES_RU_PREPOSITIONAL
            currency_name = CURRENCY_NAMES_RU_PREPOSITIONAL.get(master.currency or 'RUB', 'рублях')
    
    reply_text = f"💰 Введите цену услуги (в {currency_name}, только число):"
    keyboard = [[InlineKeyboardButton("« Назад", callback_data="service_back_to_name")]]
    
    await update.message.reply_text(
        reply_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    logger.info(f"receive_service_name: Setting state to WAITING_SERVICE_PRICE (value: {WAITING_SERVICE_PRICE})")
    logger.info(f"receive_service_name: service_name saved: {context.user_data.get('service_name')}")
    return WAITING_SERVICE_PRICE


async def receive_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить цену услуги"""
    # КРИТИЧЕСКАЯ ПРОВЕРКА В САМОМ НАЧАЛЕ: если ожидаем ввод города, НЕ обрабатываем как цену
    # Это должно быть ПЕРВОЙ проверкой, до любых других операций
    if context.user_data.get('waiting_city_name'):
        logger.warning("waiting_city_name is set - this message is for city input, not price. Ending conversation.")
        return ConversationHandler.END
    
    logger.info("=" * 50)
    logger.info("receive_service_price CALLED")
    logger.info(f"Message text: {update.message.text if update.message else 'None'}")
    logger.info(f"Context user_data keys: {list(context.user_data.keys())}")
    logger.info(f"waiting_city_name: {context.user_data.get('waiting_city_name')}")
    logger.info("=" * 50)
    
    # Получаем валюту мастера для отображения
    master = None
    currency_code = 'RUB'
    currency_name = 'рублях'
    try:
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            if not master:
                logger.warning("Master not found in receive_service_price")
            else:
                # Обновляем объект из базы данных, чтобы получить актуальную валюту
                session.refresh(master)
                currency_code = master.currency or 'RUB'
                from bot.utils.currency import CURRENCY_NAMES_RU_PREPOSITIONAL
                currency_name = CURRENCY_NAMES_RU_PREPOSITIONAL.get(currency_code, 'рублях')
                logger.info(f"Master currency: {currency_code}, currency_name: {currency_name}")
    except Exception as e:
        logger.error(f"Error getting master currency: {e}", exc_info=True)
    
    try:
        price_text = update.message.text.strip().replace(',', '.')
        logger.info(f"Parsing price from text: '{price_text}'")
        price = float(price_text)
        logger.info(f"Parsed price: {price}")
        
        if price <= 0:
            logger.warning(f"Price <= 0: {price}")
            await update.message.reply_text(f"❌ Цена должна быть больше 0. Попробуйте снова (в {currency_name}):")
            return WAITING_SERVICE_PRICE
        
        # Увеличиваем лимит для валют с маленькой стоимостью (например, сумы, донги)
        # Для UZS, VND, IDR и других валют с большими числами увеличиваем лимит до 100 миллионов
        if currency_code in ['UZS', 'VND', 'IDR', 'KZT', 'AMD', 'KGS']:
            max_price = 100000000  # 100 миллионов
        else:
            max_price = 10000000  # 10 миллионов (увеличиваем для всех валют)
        
        if price > max_price:
            logger.warning(f"Price too large: {price} (max: {max_price})")
            await update.message.reply_text(f"❌ Цена слишком большая (максимум {max_price:,}). Попробуйте снова (в {currency_name}):")
            return WAITING_SERVICE_PRICE
        
        context.user_data['service_price'] = price
        logger.info(f"Service price saved: {price} in {currency_code}")
        
        # Предлагаем выбрать длительность
        text = "⏱ Выберите длительность услуги (в минутах):"
        keyboard = [
            [InlineKeyboardButton("30 мин", callback_data="service_duration_30")],
            [InlineKeyboardButton("60 мин", callback_data="service_duration_60")],
            [InlineKeyboardButton("90 мин", callback_data="service_duration_90")],
            [InlineKeyboardButton("120 мин", callback_data="service_duration_120")],
            [InlineKeyboardButton("180 мин", callback_data="service_duration_180")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data="service_duration_manual")],
            [InlineKeyboardButton("« Назад", callback_data="service_back_to_price")]
        ]
        
        logger.info("Sending duration selection message")
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info("Duration selection message sent successfully")
        return WAITING_SERVICE_DURATION
        
    except ValueError as e:
        logger.error(f"ValueError parsing price: {e}", exc_info=True)
        # Проверяем еще раз на случай, если флаг был установлен между началом функции и этим моментом
        if context.user_data.get('waiting_city_name'):
            logger.warning("waiting_city_name detected in ValueError handler - ending conversation")
            return ConversationHandler.END
        
        await update.message.reply_text(f"❌ Введите число. Попробуйте снова (в {currency_name}):")
        return WAITING_SERVICE_PRICE
    except Exception as e:
        logger.error(f"Unexpected error in receive_service_price: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Произошла ошибка при обработке цены. Попробуйте снова (в {currency_name}):")
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
    # Проверяем, не ожидаем ли мы ввод города - если да, пропускаем обработку
    if context.user_data.get('waiting_city_name'):
        return ConversationHandler.END
    
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
        # Проверяем, не ожидаем ли мы ввод города - если да, завершаем ConversationHandler
        if context.user_data.get('waiting_city_name'):
            return ConversationHandler.END
        
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
        [InlineKeyboardButton("🔄 Настроить паузу между записями", callback_data="service_set_cooling")],
        [InlineKeyboardButton("✅ Сохранить услугу", callback_data="service_save_default")],
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
    # Проверяем, не ожидаем ли мы ввод города - если да, пропускаем обработку
    if context.user_data.get('waiting_city_name'):
        return ConversationHandler.END
    
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
        # Проверяем, не ожидаем ли мы ввод города - если да, завершаем ConversationHandler
        if context.user_data.get('waiting_city_name'):
            return ConversationHandler.END
        
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
        
        # Создаем услугу (описание будет None, его можно добавить позже)
        service = create_service(
            session=session,
            master_id=master.id,
            title=name,
            price=price,
            duration=duration,
            cooling=cooling,
            category_id=category_id,
            description=description  # Может быть пустым, добавим через редактирование
        )
        
        service_id = service.id  # Сохраняем ID созданной услуги
        
        # Очищаем данные
        service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
        for key in service_keys:
            del context.user_data[key]
        
        success_text = f"✅ Услуга <b>{name}</b> успешно создана!\n\n"
        success_text += "Теперь вы можете добавить описание, портфолио или сразу перейти дальше."
        
        # Показываем меню редактирования только что созданной услуги
        if query:
            await query.message.edit_text(success_text, parse_mode='HTML')
        else:
            await update.message.reply_text(success_text, parse_mode='HTML')
        
        # Устанавливаем флаг, что это новая услуга
        context.user_data['is_newly_created_service'] = True
        context.user_data['newly_created_service_id'] = service_id
        
        # Показываем меню редактирования услуги с опциями для нового сервиса
        await _show_new_service_menu(update, context, session, service_id, master)
    
    return ConversationHandler.END


async def service_add_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать запрос описания услуги с кнопкой генерации"""
    query = update.callback_query
    await query.answer()
    
    service_name = context.user_data.get('service_name', 'Услуга')
    
    text = f"📝 <b>Добавить описание услуги</b>\n\n"
    text += f"Услуга: <b>{service_name}</b>\n\n"
    text += "Вы можете:\n"
    text += "• Сгенерировать описание с помощью ИИ\n"
    text += "• Ввести описание вручную\n"
    text += "• Пропустить этот шаг"
    
    keyboard = [
        [InlineKeyboardButton("✨ Сгенерировать описание с помощью ИИ", callback_data="service_generate_description")],
        [InlineKeyboardButton("✏️ Ввести вручную", callback_data="service_enter_description_manual")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="service_skip_description")],
        [InlineKeyboardButton("« Назад", callback_data="service_back_to_advanced")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SERVICE_DESCRIPTION


async def service_generate_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерировать описание услуги через ИИ"""
    query = update.callback_query
    await query.answer()
    
    service_name = context.user_data.get('service_name', '')
    
    if not service_name:
        await query.message.edit_text(
            "❌ Ошибка: название услуги не найдено",
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    # Показываем статус генерации
    text = "✨ <b>Генерируем описание...</b>\n\n"
    text += f"Услуга: <b>{service_name}</b>\n\n"
    text += "Пожалуйста, подождите несколько секунд."
    
    await query.message.edit_text(
        text,
        parse_mode='HTML'
    )
    
    # Получаем количество попыток генерации для вариативности
    generation_count = context.user_data.get('service_description_generation_count', 0)
    
    # Генерируем описание
    from bot.utils.openai_client import generate_service_description
    
    try:
        description = await generate_service_description(service_name, generation_count)
        
        if description:
            # Сохраняем сгенерированное описание во временное хранилище
            context.user_data['service_description_generated'] = description
            context.user_data['service_description_generation_count'] = generation_count + 1
            
            # Показываем результат с кнопками действий
            text = f"✨ <b>Описание сгенерировано!</b>\n\n"
            text += f"Услуга: <b>{service_name}</b>\n\n"
            text += f"📝 <b>Описание:</b>\n{description}\n\n"
            text += "Выберите действие:"
            
            keyboard = [
                [InlineKeyboardButton("✅ Сохранить и продолжить", callback_data="service_save_generated_description")],
                [InlineKeyboardButton("🔄 Сгенерировать заново", callback_data="service_generate_description")],
                [InlineKeyboardButton("✏️ Заполнить вручную", callback_data="service_enter_description_manual")],
                [InlineKeyboardButton("« Назад", callback_data="service_add_description")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return WAITING_SERVICE_DESCRIPTION
        else:
            # Ошибка генерации
            text = "❌ <b>Не удалось сгенерировать описание</b>\n\n"
            text += "Попробуйте ещё раз или введите описание вручную."
            
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data="service_generate_description")],
                [InlineKeyboardButton("✏️ Ввести вручную", callback_data="service_enter_description_manual")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="service_skip_description")],
                [InlineKeyboardButton("« Назад", callback_data="service_add_description")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return WAITING_SERVICE_DESCRIPTION
            
    except Exception as e:
        logger.error(f"Error in service_generate_description: {e}", exc_info=True)
        
        text = "❌ <b>Ошибка при генерации описания</b>\n\n"
        text += "Попробуйте ещё раз или введите описание вручную."
        
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data="service_generate_description")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data="service_enter_description_manual")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="service_skip_description")],
            [InlineKeyboardButton("« Назад", callback_data="service_add_description")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return WAITING_SERVICE_DESCRIPTION


async def service_save_generated_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить сгенерированное описание и продолжить"""
    query = update.callback_query
    await query.answer()
    
    # Сохраняем сгенерированное описание
    description = context.user_data.get('service_description_generated', '')
    if description:
        context.user_data['service_description'] = description
    
    # Очищаем временные данные
    context.user_data.pop('service_description_generated', None)
    context.user_data.pop('service_description_generation_count', None)
    
    # Продолжаем создание услуги
    return await create_service_from_data(update, context)


async def service_enter_description_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перейти к ручному вводу описания"""
    query = update.callback_query
    await query.answer()
    
    service_name = context.user_data.get('service_name', 'Услуга')
    
    # Очищаем сгенерированное описание, если было
    context.user_data.pop('service_description_generated', None)
    context.user_data.pop('service_description_generation_count', None)
    
    text = f"✏️ <b>Введите описание услуги вручную</b>\n\n"
    text += f"Услуга: <b>{service_name}</b>\n\n"
    text += "Введите описание в следующем сообщении (до 500 символов):"
    
    keyboard = [
        [InlineKeyboardButton("« Назад", callback_data="service_add_description")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SERVICE_DESCRIPTION


async def receive_service_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить описание услуги введенное вручную"""
    description = update.message.text.strip()
    
    # Проверка длины
    if len(description) > 500:
        await update.message.reply_text(
            "❌ Описание слишком длинное (максимум 500 символов). Попробуйте снова:",
            parse_mode='HTML'
        )
        return WAITING_SERVICE_DESCRIPTION
    
    context.user_data['service_description'] = description
    return await create_service_from_data(update, context)


async def service_skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить описание"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем все данные, связанные с описанием
    context.user_data['service_description'] = ''
    context.user_data.pop('service_description_generated', None)
    context.user_data.pop('service_description_generation_count', None)
    
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
    
    # Получаем валюту мастера для отображения
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if not master:
            currency_name = 'рублях'
        else:
            # Обновляем объект из базы данных, чтобы получить актуальную валюту
            session.refresh(master)
            from bot.utils.currency import CURRENCY_NAMES_RU_PREPOSITIONAL
            currency_name = CURRENCY_NAMES_RU_PREPOSITIONAL.get(master.currency or 'RUB', 'рублях')
    
    text = f"💰 Введите цену услуги (в {currency_name}, только число):"
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
    # Очищаем временные данные описания при возврате
    context.user_data.pop('service_description_generated', None)
    context.user_data.pop('service_description_generation_count', None)
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
        from bot.utils.currency import format_price
        
        category_name = service.category.title if service.category else "Без категории"
        status_icon = "✅" if service.active else "❌"
        price_formatted = format_price(service.price, master.currency)
        
        text = f"✏️ <b>Редактирование услуги</b>\n\n"
        text += f"{status_icon} <b>{service.title}</b>\n"
        text += f"📁 Категория: {category_name}\n"
        text += f"💰 Цена: {price_formatted}\n"
        text += f"⏱ Длительность: {service.duration_mins} мин\n"
        text += f"🔄 Время охлаждения: {service.cooling_period_mins} мин\n"
        if service.description:
            text += f"📝 Описание: {service.description}\n"
        text += f"\n{get_impersonation_banner(context)}"
        
        # Получаем информацию о портфолио услуги
        from bot.database.db import get_portfolio_photos, get_portfolio_limit
        portfolio_photos = get_portfolio_photos(session, service_id)
        portfolio_count, portfolio_max = get_portfolio_limit(session, service_id)
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить название", callback_data=f"edit_service_name_{service_id}")],
            [InlineKeyboardButton("💰 Изменить цену", callback_data=f"edit_service_price_{service_id}")],
            [InlineKeyboardButton("⏱ Изменить длительность", callback_data=f"edit_service_duration_{service_id}")],
            [InlineKeyboardButton("🔄 Изменить время охлаждения", callback_data=f"edit_service_cooling_{service_id}")],
            [InlineKeyboardButton("✨ Сгенерировать описание", callback_data=f"edit_service_generate_description_{service_id}")],
            [InlineKeyboardButton("📝 Изменить описание", callback_data=f"edit_service_description_{service_id}")],
            [InlineKeyboardButton(f"📸 Портфолио ({portfolio_count}/{portfolio_max})", callback_data=f"service_portfolio_{service_id}")],
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
        
        # Возвращаемся к меню редактирования - отправляем новое сообщение
        await _send_edit_service_menu(update, context, session, service_id)
    
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
        
        from bot.utils.currency import format_price, CURRENCY_NAMES_RU_PREPOSITIONAL
        price_formatted = format_price(service.price, master.currency)
        currency_name = CURRENCY_NAMES_RU_PREPOSITIONAL.get(master.currency, 'рублях')
        
        text = f"💰 <b>Изменение цены услуги</b>\n\n"
        text += f"Текущая цена: <b>{price_formatted}</b>\n\n"
        text += f"Введите новую цену (в {currency_name}, только число):"
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_PRICE


async def receive_edit_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новую цену услуги"""
    # Проверяем, не ожидаем ли мы ввод города - если да, пропускаем обработку
    if context.user_data.get('waiting_city_name'):
        return ConversationHandler.END
    
    try:
        price = float(update.message.text.strip().replace(',', '.'))
        
        # Получаем валюту мастера для отображения
        with get_session() as session:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            if not master:
                currency_name = 'рублях'
            else:
                # Обновляем объект из базы данных, чтобы получить актуальную валюту
                session.refresh(master)
                from bot.utils.currency import CURRENCY_NAMES_RU_PREPOSITIONAL
                currency_name = CURRENCY_NAMES_RU_PREPOSITIONAL.get(master.currency or 'RUB', 'рублях')
        
        if price <= 0:
            await update.message.reply_text(f"❌ Цена должна быть больше 0. Попробуйте снова (в {currency_name}):")
            return WAITING_EDIT_SERVICE_PRICE
        
        if price > 1000000:
            await update.message.reply_text(f"❌ Цена слишком большая. Попробуйте снова (в {currency_name}):")
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
            
            from bot.utils.currency import format_price
            price_formatted = format_price(price, master.currency)
            await update.message.reply_text(f"✅ Цена изменена на: <b>{price_formatted}</b>", parse_mode='HTML')
            
            # Очищаем контекст
            context.user_data.pop('edit_service_id', None)
            context.user_data.pop('edit_service_field', None)
            
            # Возвращаемся к меню редактирования - отправляем новое сообщение
            await _send_edit_service_menu(update, context, session, service_id)
        
        return ConversationHandler.END
        
    except ValueError:
        # Проверяем, не ожидаем ли мы ввод города - если да, завершаем ConversationHandler
        if context.user_data.get('waiting_city_name'):
            return ConversationHandler.END
        
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
    # Проверяем, не ожидаем ли мы ввод города - если да, пропускаем обработку
    if context.user_data.get('waiting_city_name'):
        return ConversationHandler.END
    
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
            
            # Возвращаемся к меню редактирования - отправляем новое сообщение
            await _send_edit_service_menu(update, context, session, service_id)
        
        return ConversationHandler.END
        
    except ValueError:
        # Проверяем, не ожидаем ли мы ввод города - если да, завершаем ConversationHandler
        if context.user_data.get('waiting_city_name'):
            return ConversationHandler.END
        
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
    # Проверяем, не ожидаем ли мы ввод города - если да, пропускаем обработку
    if context.user_data.get('waiting_city_name'):
        return ConversationHandler.END
    
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
            
            # Возвращаемся к меню редактирования - отправляем новое сообщение
            await _send_edit_service_menu(update, context, session, service_id)
        
        return ConversationHandler.END
        
    except ValueError:
        # Проверяем, не ожидаем ли мы ввод города - если да, завершаем ConversationHandler
        if context.user_data.get('waiting_city_name'):
            return ConversationHandler.END
        
        await update.message.reply_text("❌ Введите число. Попробуйте снова:")
        return WAITING_EDIT_SERVICE_COOLING


async def edit_service_description_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование описания услуги"""
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
        context.user_data['edit_service_field'] = 'description'
        context.user_data['edit_service_name'] = service.title  # Сохраняем название для генерации
        
        text = f"📝 <b>Изменение описания услуги</b>\n\n"
        text += f"Услуга: <b>{service.title}</b>\n\n"
        if service.description:
            text += f"Текущее описание: {service.description}\n\n"
        text += "Вы можете:\n"
        text += "• Сгенерировать описание с помощью ИИ\n"
        text += "• Ввести описание вручную\n"
        text += "• Удалить описание"
        
        keyboard = [
            [InlineKeyboardButton("✨ Сгенерировать описание с помощью ИИ", callback_data=f"edit_service_generate_description_{service_id}")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")],
            [InlineKeyboardButton("🗑 Удалить описание", callback_data=f"edit_service_delete_description_{service_id}")],
            [InlineKeyboardButton("« Отмена", callback_data=f"edit_service_{service_id}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return WAITING_EDIT_SERVICE_DESCRIPTION


async def edit_service_generate_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерировать описание для редактируемой услуги через ИИ"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем service_id из callback_data: edit_service_generate_description_123
    service_id = int(query.data.split('_')[-1])
    
    # Проверяем, было ли уже сгенерировано описание через ИИ
    with get_session() as session:
        service = get_service_by_id(session, service_id)
        if not service:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        if service.description_ai_generated:
            await query.message.edit_text(
                "❌ Описание для этой услуги уже было сгенерировано через ИИ.\n\n"
                "Вы можете редактировать описание вручную или удалить его.",
                parse_mode='HTML'
            )
            # Возвращаемся к меню редактирования
            await _send_edit_service_menu(update, context, session, service_id)
            return
        
        service_name = service.title
        context.user_data['edit_service_name'] = service_name
    
    # Показываем статус генерации
    text = "✨ <b>Генерируем описание...</b>\n\n"
    text += f"Услуга: <b>{service_name}</b>\n\n"
    text += "Пожалуйста, подождите несколько секунд."
    
    await query.message.edit_text(
        text,
        parse_mode='HTML'
    )
    
    # Получаем количество попыток генерации для вариативности
    generation_count = context.user_data.get('edit_service_description_generation_count', 0)
    
    # Генерируем описание
    from bot.utils.openai_client import generate_service_description
    
    try:
        description = await generate_service_description(service_name, generation_count)
        
        if description:
            # Сохраняем сгенерированное описание во временное хранилище
            context.user_data['edit_service_description_generated'] = description
            context.user_data['edit_service_description_generation_count'] = generation_count + 1
            
            # Проверяем, это новая услуга или редактирование
            is_new_service = context.user_data.get('is_newly_created_service', False) and context.user_data.get('newly_created_service_id') == service_id
            
            # Показываем результат с кнопками действий
            text = f"✨ <b>Описание сгенерировано!</b>\n\n"
            text += f"Услуга: <b>{service_name}</b>\n\n"
            text += f"📝 <b>Описание:</b>\n{description}\n\n"
            text += "Выберите действие:"
            
            # Убираем кнопку "Сгенерировать заново", так как можно сгенерировать только один раз
            if is_new_service:
                # Для новой услуги сохраняем сразу и возвращаемся к меню новой услуги
                keyboard = [
                    [InlineKeyboardButton("✅ Сохранить и продолжить", callback_data=f"edit_service_save_generated_description_{service_id}")],
                    [InlineKeyboardButton("✏️ Заполнить вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("✅ Сохранить", callback_data=f"edit_service_save_generated_description_{service_id}")],
                    [InlineKeyboardButton("✏️ Заполнить вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")],
                    [InlineKeyboardButton("« Назад", callback_data=f"edit_service_description_{service_id}")]
                ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return WAITING_EDIT_SERVICE_DESCRIPTION
        else:
            # Ошибка генерации - НЕ устанавливаем флаг, чтобы можно было попробовать снова
            text = "❌ <b>Не удалось сгенерировать описание</b>\n\n"
            text += "Попробуйте ещё раз или введите описание вручную."
            
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data=f"edit_service_generate_description_{service_id}")],
                [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")],
                [InlineKeyboardButton("« Назад", callback_data=f"edit_service_description_{service_id}")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return WAITING_EDIT_SERVICE_DESCRIPTION
            
    except Exception as e:
        logger.error(f"Error in edit_service_generate_description: {e}", exc_info=True)
        
        # НЕ устанавливаем флаг при ошибке - можно попробовать снова
        text = "❌ <b>Ошибка при генерации описания</b>\n\n"
        text += "Попробуйте ещё раз или введите описание вручную."
        
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data=f"edit_service_generate_description_{service_id}")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")],
            [InlineKeyboardButton("« Назад", callback_data=f"edit_service_description_{service_id}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return WAITING_EDIT_SERVICE_DESCRIPTION


async def edit_service_save_generated_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить сгенерированное описание для редактируемой услуги"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем service_id из callback_data: edit_service_save_generated_description_123
    service_id = int(query.data.split('_')[-1])
    description = context.user_data.get('edit_service_description_generated', '')
    
    if not description:
        await query.message.edit_text("❌ Ошибка: описание не найдено")
        return ConversationHandler.END
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Обновляем описание и устанавливаем флаг, что оно было сгенерировано через ИИ
        update_service(session, service_id, description=description, description_ai_generated=True)
        
        # Показываем краткое уведомление
        await query.answer("✅ Описание успешно обновлено!", show_alert=False)
        
        # Проверяем, это новая услуга или редактирование существующей
        is_new_service = context.user_data.get('is_newly_created_service', False) and context.user_data.get('newly_created_service_id') == service_id
        
        # Очищаем контекст
        context.user_data.pop('edit_service_id', None)
        context.user_data.pop('edit_service_field', None)
        context.user_data.pop('edit_service_name', None)
        context.user_data.pop('edit_service_description_generated', None)
        context.user_data.pop('edit_service_description_generation_count', None)
        
        if is_new_service:
            # Если это новая услуга, возвращаемся к меню новой услуги
            await _show_new_service_menu(update, context, session, service_id, master)
        else:
            # Возвращаемся к меню редактирования (редактируем текущее сообщение)
            await _send_edit_service_menu(update, context, session, service_id)
    
    return ConversationHandler.END


async def edit_service_enter_description_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перейти к ручному вводу описания для редактируемой услуги"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем service_id из callback_data: edit_service_enter_description_manual_123
    service_id = int(query.data.split('_')[-1])
    
    with get_session() as session:
        service = get_service_by_id(session, service_id)
        service_name = service.title if service else "Услуга"
    
    # Сохраняем service_id для receive_edit_service_description
    context.user_data['edit_service_id'] = service_id
    context.user_data['edit_service_field'] = 'description'
    
    # Очищаем сгенерированное описание, если было
    context.user_data.pop('edit_service_description_generated', None)
    context.user_data.pop('edit_service_description_generation_count', None)
    
    text = f"✏️ <b>Введите описание услуги вручную</b>\n\n"
    text += f"Услуга: <b>{service_name}</b>\n\n"
    text += "Введите описание в следующем сообщении (до 500 символов):"
    
    # Проверяем, это новая услуга или редактирование
    is_new_service = context.user_data.get('is_newly_created_service', False) and context.user_data.get('newly_created_service_id') == service_id
    
    if is_new_service:
        # Для новой услуги возвращаемся к меню новой услуги (через генерацию)
        keyboard = [
            [InlineKeyboardButton("« Назад", callback_data=f"new_service_generate_description_{service_id}")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("« Назад", callback_data=f"edit_service_description_{service_id}")]
        ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_EDIT_SERVICE_DESCRIPTION


async def receive_edit_service_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить описание услуги введенное вручную при редактировании"""
    description = update.message.text.strip()
    service_id = context.user_data.get('edit_service_id')
    
    # Проверка длины
    if len(description) > 500:
        await update.message.reply_text(
            "❌ Описание слишком длинное (максимум 500 символов). Попробуйте снова:",
            parse_mode='HTML'
        )
        return WAITING_EDIT_SERVICE_DESCRIPTION
    
    if not service_id:
        await update.message.reply_text("❌ Ошибка: ID услуги не найден")
        return ConversationHandler.END
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await update.message.reply_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Обновляем описание (при ручном вводе сбрасываем флаг генерации через ИИ)
        update_service(session, service_id, description=description, description_ai_generated=False)
        
        # Проверяем, это новая услуга или редактирование существующей
        is_new_service = context.user_data.get('is_newly_created_service', False) and context.user_data.get('newly_created_service_id') == service_id
        
        # Очищаем контекст
        context.user_data.pop('edit_service_id', None)
        context.user_data.pop('edit_service_field', None)
        context.user_data.pop('edit_service_name', None)
        
        # Показываем краткое уведомление
        await update.message.reply_text("✅ Описание успешно обновлено!", parse_mode='HTML')
        
        if is_new_service:
            # Если это новая услуга, возвращаемся к меню новой услуги
            await _show_new_service_menu(update, context, session, service_id, master)
        else:
            # Возвращаемся к меню редактирования
            await _send_edit_service_menu(update, context, session, service_id)
    
    return ConversationHandler.END


async def edit_service_delete_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить описание услуги"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return ConversationHandler.END
        
        # Удаляем описание (устанавливаем пустую строку) и сбрасываем флаг генерации через ИИ
        update_service(session, service_id, description='', description_ai_generated=False)
        
        # Показываем краткое уведомление
        await query.answer("✅ Описание удалено", show_alert=False)
        
        # Очищаем контекст
        context.user_data.pop('edit_service_id', None)
        context.user_data.pop('edit_service_field', None)
        context.user_data.pop('edit_service_name', None)
        
        # Возвращаемся к меню редактирования (редактируем текущее сообщение)
        await _send_edit_service_menu(update, context, session, service_id)
    
    return ConversationHandler.END


async def new_service_generate_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерировать описание для новой услуги через ИИ"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем service_id из callback_data: new_service_generate_description_123
    service_id = int(query.data.split('_')[-1])
    
    # Получаем название услуги и проверяем флаг внутри сессии
    service_name = None
    with get_session() as session:
        service = get_service_by_id(session, service_id)
        if not service:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        # Сохраняем название до закрытия сессии
        service_name = service.title
        
        # Проверяем, было ли уже сгенерировано описание через ИИ
        if service.description_ai_generated:
            master = get_master_by_telegram(session, get_master_telegram_id(update, context))
            await query.message.edit_text(
                "❌ Описание для этой услуги уже было сгенерировано через ИИ.\n\n"
                "Вы можете редактировать описание вручную или удалить его.",
                parse_mode='HTML'
            )
            # Возвращаемся к меню новой услуги
            await _show_new_service_menu(update, context, session, service_id, master)
            return
    
    if not service_name:
        await query.message.edit_text("❌ Ошибка: не удалось получить название услуги")
        return
    
    # Показываем статус генерации
    text = "✨ <b>Генерируем описание...</b>\n\n"
    text += f"Услуга: <b>{service_name}</b>\n\n"
    text += "Пожалуйста, подождите несколько секунд."
    
    await query.message.edit_text(
        text,
        parse_mode='HTML'
    )
    
    # Получаем количество попыток генерации для вариативности
    generation_count = context.user_data.get('new_service_description_generation_count', 0)
    
    # Генерируем описание
    from bot.utils.openai_client import generate_service_description
    
    try:
        description = await generate_service_description(service_name, generation_count)
        
        if description:
            # Сохраняем описание сразу в базу и устанавливаем флаг, что оно было сгенерировано через ИИ
            with get_session() as session:
                update_service(session, service_id, description=description, description_ai_generated=True)
            
            # Показываем результат и возвращаемся к меню новой услуги
            text = f"✨ <b>Описание сгенерировано и сохранено!</b>\n\n"
            text += f"Услуга: <b>{service_name}</b>\n\n"
            text += f"📝 <b>Описание:</b>\n{description}\n\n"
            text += "Что дальше?"
            
            # Получаем информацию о портфолио
            from bot.database.db import get_portfolio_photos, get_portfolio_limit
            with get_session() as session:
                master = get_master_by_telegram(session, get_master_telegram_id(update, context))
                portfolio_photos = get_portfolio_photos(session, service_id)
                portfolio_count, portfolio_max = get_portfolio_limit(session, service_id)
            
            # Убираем кнопку "Сгенерировать другое описание", так как можно сгенерировать только один раз
            keyboard = [
                [InlineKeyboardButton("✏️ Изменить описание", callback_data=f"edit_service_enter_description_manual_{service_id}")],
                [InlineKeyboardButton(f"📸 Добавить портфолио ({portfolio_count}/{portfolio_max})", callback_data=f"service_portfolio_{service_id}")],
                [InlineKeyboardButton("➡️ Продолжить", callback_data=f"service_created_next_{service_id}")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Обновляем счетчик генераций
            context.user_data['new_service_description_generation_count'] = generation_count + 1
        else:
            # Ошибка генерации - НЕ устанавливаем флаг, чтобы можно было попробовать снова
            text = "❌ <b>Не удалось сгенерировать описание</b>\n\n"
            text += "Попробуйте ещё раз или введите описание вручную."
            
            from bot.database.db import get_portfolio_limit
            with get_session() as session:
                portfolio_count, portfolio_max = get_portfolio_limit(session, service_id)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data=f"new_service_generate_description_{service_id}")],
                [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")],
                [InlineKeyboardButton(f"📸 Добавить портфолио ({portfolio_count}/{portfolio_max})", callback_data=f"service_portfolio_{service_id}")],
                [InlineKeyboardButton("➡️ Продолжить", callback_data=f"service_created_next_{service_id}")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        logger.error(f"Error in new_service_generate_description: {e}", exc_info=True)
        
        # НЕ устанавливаем флаг при ошибке - можно попробовать снова
        text = "❌ <b>Ошибка при генерации описания</b>\n\n"
        text += "Попробуйте ещё раз или введите описание вручную."
        
        from bot.database.db import get_portfolio_limit
        with get_session() as session:
            portfolio_count, portfolio_max = get_portfolio_limit(session, service_id)
        
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data=f"new_service_generate_description_{service_id}")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"edit_service_enter_description_manual_{service_id}")],
            [InlineKeyboardButton(f"📸 Добавить портфолио ({portfolio_count}/{portfolio_max})", callback_data=f"service_portfolio_{service_id}")],
            [InlineKeyboardButton("➡️ Продолжить", callback_data=f"service_created_next_{service_id}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def service_created_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать шаг после создания услуги: добавить еще услугу или перейти к расписанию"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[-1])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        service = get_service_by_id(session, service_id)
        
        if not master or not service:
            await query.message.edit_text("❌ Ошибка: услуга не найдена")
            return
        
        # Проверяем прогресс анбординга
        from .onboarding import get_onboarding_progress
        progress_info = get_onboarding_progress(session, master)
        
        text = f"✅ Услуга <b>{service.title}</b> создана!\n\n"
        
        if not progress_info['is_complete']:
            # Если анбординг не завершен, предлагаем перейти к расписанию
            text += "📍 <b>Следующий шаг:</b> Настройка расписания\n\n"
            text += "Установите рабочие часы, чтобы клиенты могли записаться к вам."
            
            keyboard = [
                [InlineKeyboardButton("📅 Настроить расписание", callback_data="master_schedule")],
                [InlineKeyboardButton("➕ Добавить еще услугу", callback_data="add_service")],
                [InlineKeyboardButton("💼 Мои услуги", callback_data="master_services")]
            ]
        else:
            # Если анбординг завершен, предлагаем выбор
            text += "Что вы хотите сделать дальше?"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить еще услугу", callback_data="add_service")],
                [InlineKeyboardButton("📅 Настроить расписание", callback_data="master_schedule")],
                [InlineKeyboardButton("💼 Мои услуги", callback_data="master_services")]
            ]
        
        # Очищаем флаг новой услуги после перехода к следующему шагу
        context.user_data.pop('is_newly_created_service', None)
        context.user_data.pop('newly_created_service_id', None)
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


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

