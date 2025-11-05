"""Обработчики для админ-панели"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from bot.database.db import (
    get_session,
    is_superadmin,
    get_master_stats,
    get_masters_paginated,
    get_master_by_id,
    get_blocked_masters,
    block_master,
    unblock_master,
    delete_master,
    update_master_subscription,
    get_services_by_master,
    get_work_periods,
    get_bookings_for_master,
    get_master_clients_count
)
from datetime import datetime

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_DELETE_CONFIRM = 1
WAITING_BLOCK_REASON = 2
WAITING_SEARCH_QUERY = 3


def require_superadmin(func):
    """Декоратор для проверки прав суперадмина"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            logger.warning(f"[ADMIN] No user in update for {func.__name__}")
            return
        
        logger.info(f"[ADMIN] Checking admin rights for user_id={user.id} in {func.__name__}")
        
        if not is_superadmin(user.id):
            logger.warning(f"[ADMIN] User {user.id} is NOT superadmin, blocking access to {func.__name__}")
            if update.callback_query:
                await update.callback_query.answer("❌ Только для администратора", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Только для администратора")
            return
        
        logger.info(f"[ADMIN] User {user.id} IS superadmin, allowing access to {func.__name__}")
        return await func(update, context)
    return wrapper


@require_superadmin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная админ-панель"""
    logger.info(f"[ADMIN] admin_panel called, update_id={update.update_id}")
    query = update.callback_query
    if query:
        await query.answer()
    
    try:
        with get_session() as session:
            stats = get_master_stats(session)
    except Exception as e:
        logger.error(f"[ADMIN] Error getting stats: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text(f"❌ Ошибка при получении статистики: {str(e)}")
        return
    
    text = f"""🔧 <b>Админ-панель</b>

📊 <b>Статистика:</b>
👥 Мастеров: {stats['active_masters']} (всего: {stats['total_masters']}, заблокировано: {stats['blocked_masters']})
👤 Клиентов: {stats['total_clients']}
📋 Активных записей: {stats['active_bookings']}

💳 <b>Подписки:</b>
🆓 Бесплатно: {stats['subscriptions']['free']}
📦 Базовый: {stats['subscriptions']['basic']}
⭐ Премиум: {stats['subscriptions']['premium']}

Выберите действие:"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Список мастеров", callback_data="admin_masters_list_1")],
        [InlineKeyboardButton("🚫 Заблокированные", callback_data="admin_blocked_masters")],
        [InlineKeyboardButton("🔍 Поиск мастера", callback_data="admin_search_master")],
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


@require_superadmin
async def admin_masters_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список мастеров с пагинацией"""
    query = update.callback_query
    await query.answer()
    
    # Формат: admin_masters_list_1 (страница)
    page = int(query.data.split('_')[3]) if len(query.data.split('_')) > 3 else 1
    
    with get_session() as session:
        masters, total = get_masters_paginated(session, page=page, per_page=10, include_blocked=True)
        
        # Извлекаем данные внутри сессии
        masters_data = []
        for master in masters:
            services_count = len(get_services_by_master(session, master.id))
            clients_count = get_master_clients_count(session, master.id)
            
            masters_data.append({
                'id': master.id,
                'name': master.name,
                'telegram_id': master.telegram_id,
                'subscription': master.subscription_level,
                'is_blocked': master.is_blocked,
                'services_count': services_count,
                'clients_count': clients_count
            })
    
    text = f"📋 <b>Список мастеров</b>\n\n"
    text += f"Страница {page} из {(total + 9) // 10}\n\n"
    
    if not masters_data:
        text += "Мастеров не найдено."
    else:
        for master_info in masters_data:
            status_emoji = "🚫" if master_info['is_blocked'] else "✅"
            sub_emoji = {"free": "🆓", "basic": "📦", "premium": "⭐"}.get(master_info['subscription'], "❓")
            
            text += f"{status_emoji} <b>{master_info['name']}</b> {sub_emoji}\n"
            text += f"   ID: {master_info['id']} | TG: {master_info['telegram_id']}\n"
            text += f"   Услуг: {master_info['services_count']} | Клиентов: {master_info['clients_count']}\n\n"
    
    keyboard = []
    for master_info in masters_data:
        keyboard.append([
            InlineKeyboardButton(
                f"{'🚫' if master_info['is_blocked'] else '✅'} {master_info['name']}",
                callback_data=f"admin_master_detail_{master_info['id']}"
            )
        ])
    
    # Пагинация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"admin_masters_list_{page - 1}"))
    if page * 10 < total:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"admin_masters_list_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 В админ-панель", callback_data="admin_panel")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_superadmin
async def admin_master_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная информация о мастере"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_id(session, master_id)
        
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        # Извлекаем все данные внутри сессии
        services = get_services_by_master(session, master.id)
        work_periods = get_work_periods(session, master.id)
        bookings = get_bookings_for_master(session, master.id)
        clients_count = get_master_clients_count(session, master.id)
        
        # Извлекаем все необходимые атрибуты в обычные переменные
        master_name = master.name
        master_telegram_id = master.telegram_id
        master_created_at = master.created_at
        subscription_level = master.subscription_level
        is_blocked = master.is_blocked
        blocked_at = master.blocked_at
        block_reason = master.block_reason
        
        # Будущие записи
        now = datetime.utcnow()
        future_bookings = [b for b in bookings if b.start_dt > now]
        
        sub_emoji = {"free": "🆓", "basic": "📦", "premium": "⭐"}.get(subscription_level, "❓")
        sub_name = {"free": "Бесплатно", "basic": "Базовый", "premium": "Премиум"}.get(subscription_level, "Неизвестно")
        
        text = f"""👤 <b>Информация о мастере</b>

📛 <b>Имя:</b> {master_name}
🆔 <b>ID:</b> {master_id}
📱 <b>Telegram ID:</b> {master_telegram_id}
💳 <b>Подписка:</b> {sub_emoji} {sub_name}
📅 <b>Создан:</b> {master_created_at.strftime('%d.%m.%Y %H:%M')}

📊 <b>Статистика:</b>
💼 Услуг: {len(services)}
👥 Клиентов: {clients_count}
📅 Периодов расписания: {len(work_periods)}
📋 Будущих записей: {len(future_bookings)}

"""
        
        if is_blocked:
            text += f"🚫 <b>Статус:</b> Заблокирован\n"
            if blocked_at:
                text += f"📅 Заблокирован: {blocked_at.strftime('%d.%m.%Y %H:%M')}\n"
            if block_reason:
                text += f"📝 Причина: {block_reason}\n"
        else:
            text += "✅ <b>Статус:</b> Активен\n"
    
    keyboard = []
    
    # Кнопки управления
    if is_blocked:
        keyboard.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"admin_unblock_{master_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"admin_block_{master_id}")])
    
    keyboard.append([InlineKeyboardButton("💳 Изменить подписку", callback_data=f"admin_change_sub_{master_id}")])
    keyboard.append([InlineKeyboardButton("🗑️ Удалить мастера", callback_data=f"admin_delete_confirm_{master_id}")])
    keyboard.append([InlineKeyboardButton("🎭 Войти от лица мастера", callback_data=f"admin_impersonate_{master_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад к списку", callback_data="admin_masters_list_1")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_superadmin
async def admin_block_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заблокировать мастера"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_id(session, master_id)
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        is_blocked = master.is_blocked
        master_name = master.name
    
    if is_blocked:
        await query.answer("⚠️ Мастер уже заблокирован", show_alert=True)
        await admin_master_detail(update, context)
        return
    
    # Запрашиваем причину блокировки
    context.user_data['admin_block_master_id'] = master_id
    
    await query.message.edit_text(
        f"🚫 <b>Блокировка мастера</b>\n\n"
        f"Мастер: <b>{master_name}</b>\n\n"
        f"Введите причину блокировки (или отправьте \"-\" для пропуска):",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f"admin_master_detail_{master_id}")
        ]])
    )
    
    return WAITING_BLOCK_REASON


@require_superadmin
async def admin_block_reason_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получена причина блокировки"""
    reason = update.message.text.strip()
    if reason == "-":
        reason = None
    
    master_id = context.user_data.pop('admin_block_master_id', None)
    
    if not master_id:
        await update.message.reply_text("❌ Ошибка: не найден ID мастера")
        return ConversationHandler.END
    
    with get_session() as session:
        success = block_master(session, master_id, reason)
        
        if success:
            master = get_master_by_id(session, master_id)
            master_name = master.name if master else "Неизвестно"
            await update.message.reply_text(
                f"✅ Мастер <b>{master_name}</b> заблокирован",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ К списку мастеров", callback_data="admin_masters_list_1")
                ]])
            )
        else:
            await update.message.reply_text("❌ Ошибка при блокировке мастера")
    
    return ConversationHandler.END


@require_superadmin
async def admin_unblock_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разблокировать мастера"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        success = unblock_master(session, master_id)
        
        if success:
            master = get_master_by_id(session, master_id)
            master_name = master.name if master else "Неизвестно"
            await query.answer(f"✅ Мастер {master_name} разблокирован", show_alert=True)
            await admin_master_detail(update, context)
        else:
            await query.answer("❌ Ошибка при разблокировке", show_alert=True)


@require_superadmin
async def admin_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления мастера"""
    query = update.callback_query
    if not query:
        logger.error("[ADMIN] admin_delete_confirm called without callback_query")
        return
    
    try:
        await query.answer()
        
        # Парсим master_id из callback_data: admin_delete_confirm_{master_id}
        parts = query.data.split('_')
        if len(parts) < 4:
            logger.error(f"[ADMIN] Invalid callback_data format: {query.data}")
            await query.message.edit_text("❌ Ошибка: неверный формат данных")
            return
        
        master_id = int(parts[3])
        logger.info(f"[ADMIN] Delete confirmation requested for master_id={master_id}")
        
        with get_session() as session:
            master = get_master_by_id(session, master_id)
            if not master:
                logger.warning(f"[ADMIN] Master {master_id} not found")
                await query.message.edit_text("❌ Мастер не найден")
                return
            
            # Извлекаем имя до закрытия сессии
            master_name = master.name
            
            # Подсчитываем что будет удалено
            services_count = len(get_services_by_master(session, master.id))
            work_periods_count = len(get_work_periods(session, master.id))
            bookings_count = len(get_bookings_for_master(session, master.id))
            clients_count = get_master_clients_count(session, master.id)
        
        text = f"""⚠️ <b>ВНИМАНИЕ! Удаление мастера</b>

Мастер: <b>{master_name}</b>

При удалении будут удалены ВСЕ данные:
❌ Профиль мастера
❌ Услуги ({services_count})
❌ Расписание ({work_periods_count} периодов)
❌ Бронирования ({bookings_count})
❌ Связи с клиентами ({clients_count})

⚠️ Это действие НЕОБРАТИМО!

Мастер сможет заново зарегистрироваться через /start.

Вы уверены?"""
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Да, удалить", callback_data=f"admin_delete_execute_{master_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"admin_master_detail_{master_id}")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"[ADMIN] Delete confirmation message sent for master_id={master_id}")
        
    except Exception as e:
        logger.error(f"[ADMIN] Error in admin_delete_confirm: {e}", exc_info=True)
        try:
            await query.message.edit_text(f"❌ Ошибка: {str(e)}")
        except:
            pass


@require_superadmin
async def admin_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение удаления мастера"""
    query = update.callback_query
    await query.answer()
    
    try:
        master_id = int(query.data.split('_')[3])
        logger.info(f"[ADMIN] Delete execution requested for master_id={master_id}")
        
        master_name = None
        with get_session() as session:
            master = get_master_by_id(session, master_id)
            if not master:
                logger.warning(f"[ADMIN] Master {master_id} not found for deletion")
                await query.message.edit_text("❌ Мастер не найден")
                return
            
            # Сохраняем имя ДО удаления (внутри сессии)
            master_name = str(master.name)  # Преобразуем в строку на всякий случай
            logger.info(f"[ADMIN] Deleting master {master_id} ({master_name})")
            
            # Вызываем удаление (внутри той же сессии)
            success = delete_master(session, master_id)
            
            if success:
                logger.info(f"[ADMIN] Master {master_id} ({master_name}) deleted successfully")
            else:
                logger.error(f"[ADMIN] Failed to delete master {master_id}")
        
        # После закрытия сессии используем сохраненное имя
        if success and master_name:
            await query.message.edit_text(
                f"✅ Мастер <b>{master_name}</b> и все его данные удалены.\n\n"
                f"Мастер может заново зарегистрироваться через /start.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ К списку мастеров", callback_data="admin_masters_list_1")
                ]])
            )
        else:
            await query.message.edit_text(
                "❌ Ошибка при удалении мастера",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data=f"admin_master_detail_{master_id}")
                ]])
            )
            
    except Exception as e:
        logger.error(f"[ADMIN] Error in admin_delete_execute: {e}", exc_info=True)
        try:
            await query.message.edit_text(
                f"❌ Ошибка при удалении: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="admin_masters_list_1")
                ]])
            )
        except:
            pass


@require_superadmin
async def admin_change_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить подписку мастера"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_id(session, master_id)
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        subscription_level = master.subscription_level
        master_name = master.name
        current_sub = {"free": "🆓 Бесплатно", "basic": "📦 Базовый", "premium": "⭐ Премиум"}.get(subscription_level, "Неизвестно")
    
    text = f"""💳 <b>Изменение подписки</b>

Мастер: <b>{master_name}</b>
Текущая подписка: {current_sub}

Выберите новую подписку:"""
    
    keyboard = [
        [InlineKeyboardButton("🆓 Бесплатно", callback_data=f"admin_set_sub_{master_id}_free")],
        [InlineKeyboardButton("📦 Базовый", callback_data=f"admin_set_sub_{master_id}_basic")],
        [InlineKeyboardButton("⭐ Премиум", callback_data=f"admin_set_sub_{master_id}_premium")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"admin_master_detail_{master_id}")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_superadmin
async def admin_set_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить подписку"""
    query = update.callback_query
    await query.answer()
    
    # Формат: admin_set_sub_123_free
    parts = query.data.split('_')
    master_id = int(parts[3])
    sub_level = parts[4]
    
    with get_session() as session:
        success = update_master_subscription(session, master_id, sub_level)
        
        if success:
            master = get_master_by_id(session, master_id)
            sub_name = {"free": "🆓 Бесплатно", "basic": "📦 Базовый", "premium": "⭐ Премиум"}.get(sub_level, "Неизвестно")
            await query.answer(f"✅ Подписка изменена на {sub_name}", show_alert=True)
            await admin_master_detail(update, context)
        else:
            await query.answer("❌ Ошибка при изменении подписки", show_alert=True)


@require_superadmin
async def admin_blocked_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список заблокированных мастеров"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        blocked = get_blocked_masters(session)
        
        if not blocked:
            text = "🚫 <b>Заблокированные мастера</b>\n\nЗаблокированных мастеров нет."
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
        else:
            text = f"🚫 <b>Заблокированные мастера ({len(blocked)})</b>\n\n"
            
            blocked_data = []
            for master in blocked:
                blocked_data.append({
                    'id': master.id,
                    'name': master.name,
                    'blocked_at': master.blocked_at,
                    'block_reason': master.block_reason
                })
            
            for master_data in blocked_data:
                if master_data['blocked_at']:
                    blocked_date = master_data['blocked_at'].strftime('%d.%m.%Y')
                else:
                    blocked_date = "Неизвестно"
                
                text += f"🚫 <b>{master_data['name']}</b>\n"
                text += f"   ID: {master_data['id']} | Заблокирован: {blocked_date}\n"
                if master_data['block_reason']:
                    text += f"   Причина: {master_data['block_reason']}\n"
                text += "\n"
            
            keyboard = []
            for master_data in blocked_data:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🚫 {master_data['name']}",
                        callback_data=f"admin_master_detail_{master_data['id']}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@require_superadmin
async def admin_search_master_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало поиска мастера"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "🔍 <b>Поиск мастера</b>\n\n"
        "Введите имя мастера или Telegram ID для поиска:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")
        ]])
    )
    
    return WAITING_SEARCH_QUERY


@require_superadmin
async def admin_search_master_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Результат поиска мастера"""
    search_query = update.message.text.strip()
    
    with get_session() as session:
        masters, total = get_masters_paginated(session, page=1, per_page=10, include_blocked=True, search_query=search_query)
        
        if not masters:
            await update.message.reply_text(
                f"❌ Мастера по запросу \"{search_query}\" не найдены.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
                ]])
            )
            return ConversationHandler.END
        
        # Извлекаем данные внутри сессии
        masters_data = []
        for master in masters:
            masters_data.append({
                'id': master.id,
                'name': master.name,
                'telegram_id': master.telegram_id,
                'subscription': master.subscription_level,
                'is_blocked': master.is_blocked
            })
        
        text = f"🔍 <b>Результаты поиска</b>\n\n"
        text += f"Найдено: {total}\n\n"
        
        for master_info in masters_data:
            status_emoji = "🚫" if master_info['is_blocked'] else "✅"
            sub_emoji = {"free": "🆓", "basic": "📦", "premium": "⭐"}.get(master_info['subscription'], "❓")
            text += f"{status_emoji} <b>{master_info['name']}</b> {sub_emoji}\n"
            text += f"   ID: {master_info['id']} | TG: {master_info['telegram_id']}\n\n"
        
        keyboard = []
        for master_info in masters_data:
            keyboard.append([
                InlineKeyboardButton(
                    f"{'🚫' if master_info['is_blocked'] else '✅'} {master_info['name']}",
                    callback_data=f"admin_master_detail_{master_info['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return ConversationHandler.END


@require_superadmin
async def admin_impersonate_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Войти от лица мастера (имперсонация)"""
    query = update.callback_query
    await query.answer()
    
    master_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_id(session, master_id)
        if not master:
            await query.message.edit_text("❌ Мастер не найден")
            return
        
        # Сохраняем ID админа и мастера для имперсонации
        master_name = master.name
        context.user_data['impersonating'] = True
        context.user_data['impersonated_master_id'] = master.id
        context.user_data['impersonated_master_telegram_id'] = master.telegram_id
        context.user_data['impersonated_master_name'] = master_name
        context.user_data['admin_id'] = update.effective_user.id
    
    await query.message.edit_text(
        f"🎭 <b>Имперсонация активирована</b>\n\n"
        f"Вы работаете от лица мастера: <b>{master_name}</b>\n\n"
        f"Теперь вы можете использовать команды мастера.\n"
        f"Для выхода используйте /stop_impersonation или вернитесь в админ-панель.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 В админ-панель", callback_data="admin_panel")
        ]])
    )


@require_superadmin
async def admin_stop_impersonation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановить имперсонацию"""
    query = update.callback_query if hasattr(update, 'callback_query') and update.callback_query else None
    
    if 'impersonating' not in context.user_data:
        if query:
            await query.answer("⚠️ Имперсонация не активна", show_alert=True)
        elif update.message:
            await update.message.reply_text("⚠️ Имперсонация не активна")
        return
    
    master_id = context.user_data.pop('impersonated_master_id', None)
    context.user_data.pop('impersonating', None)
    context.user_data.pop('impersonated_master_telegram_id', None)
    context.user_data.pop('admin_id', None)
    
    if query:
        await query.answer("✅ Имперсонация остановлена", show_alert=True)
        await admin_panel(update, context)
    elif update.message:
        await update.message.reply_text(
            "✅ Имперсонация остановлена",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Админ-панель", callback_data="admin_panel")
            ]])
        )


# ConversationHandler для админки
def create_admin_conversation_handler():
    """Создать ConversationHandler для админки"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_block_master, pattern=r'^admin_block_\d+$'),
            CallbackQueryHandler(admin_search_master_start, pattern='^admin_search_master$'),
        ],
        states={
            WAITING_BLOCK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_reason_received)],
            WAITING_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_search_master_result)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_panel, pattern='^admin_panel$'),
            MessageHandler(filters.COMMAND, admin_panel),
        ],
        name="admin_conversation"
    )
