"""Удаление аккаунта мастера"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    delete_master,
    get_services_by_master,
    get_work_periods,
    get_bookings_for_master,
    get_master_clients_count
)
from bot.utils.impersonation import get_master_telegram_id, is_impersonating

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
from .common import WAITING_DELETE_CONFIRM, WAITING_DELETE_FINAL


async def show_delete_account_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать опцию удаления аккаунта в настройках"""
    query = update.callback_query
    if query:
        await query.answer()
    
    text = "⚙️ <b>Настройки</b>\n\n"
    text += "• Профиль\n"
    text += "• Подписка\n"
    text += "• Удалить аккаунт\n"
    
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="master_profile")],
        [InlineKeyboardButton("💎 Подписка", callback_data="master_premium")],
        [InlineKeyboardButton("🗑️ Удалить аккаунт", callback_data="delete_account_start")],
        [InlineKeyboardButton("« Назад", callback_data="master_menu")]
    ]
    
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


async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать процесс удаления аккаунта (первый шаг - предупреждение)"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, не находится ли мастер в режиме имперсонации
    if is_impersonating(context):
        await query.message.edit_text(
            "❌ Вы не можете удалить аккаунт во время имперсонации суперадмином.\n\n"
            "Попросите администратора отключить режим имперсонации.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data="master_profile")
            ]])
        )
        return ConversationHandler.END
    
    user = update.effective_user
    
    with get_session() as session:
        master = get_master_by_telegram(session, user.id)
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return ConversationHandler.END
        
        # Подсчитываем, что будет удалено
        services_count = len(get_services_by_master(session, master.id, active_only=False))
        work_periods_count = len(get_work_periods(session, master.id))
        bookings_count = len(get_bookings_for_master(session, master.id))
        clients_count = get_master_clients_count(session, master.id)
        
        # Сохраняем данные в контекст для следующих шагов
        context.user_data['delete_master_id'] = master.id
        context.user_data['delete_services_count'] = services_count
        context.user_data['delete_work_periods_count'] = work_periods_count
        context.user_data['delete_bookings_count'] = bookings_count
        context.user_data['delete_clients_count'] = clients_count
        context.user_data['delete_master_name'] = master.name
        
        text = f"""⚠️ <b>ВНИМАНИЕ! Удаление аккаунта</b>

При удалении вашего аккаунта будут удалены <b>ВСЕ</b> ваши данные:

❌ Ваш профиль
❌ Услуги ({services_count})
❌ Расписание ({work_periods_count} периодов)
❌ Бронирования ({bookings_count})
❌ Связи с клиентами ({clients_count})

<b>⚠️ Это действие НЕОБРАТИМО!</b>

Вы больше не сможете войти в ваш аккаунт. Однако вы сможете зарегистрироваться заново через /start.

<b>Вы действительно хотите продолжить?</b>"""
        
        keyboard = [
            [InlineKeyboardButton("⚠️ Да, я хочу удалить аккаунт", callback_data="delete_account_confirm_intent")],
            [InlineKeyboardButton("❌ Отмена", callback_data="master_profile")]
        ]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"[MASTER_DELETE] Delete confirmation step 1 requested for master_id={context.user_data['delete_master_id']}, user_id={user.id}")
        
        return WAITING_DELETE_CONFIRM


async def delete_account_confirm_intent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Второй шаг подтверждения удаления аккаунта (дополнительное подтверждение)"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    master_id = context.user_data.get('delete_master_id')
    master_name = context.user_data.get('delete_master_name', 'Мастер')
    services_count = context.user_data.get('delete_services_count', 0)
    work_periods_count = context.user_data.get('delete_work_periods_count', 0)
    bookings_count = context.user_data.get('delete_bookings_count', 0)
    clients_count = context.user_data.get('delete_clients_count', 0)
    
    if not master_id:
        logger.error(f"[MASTER_DELETE] Master ID not found in context for user {user.id}")
        await query.message.edit_text(
            "❌ Ошибка: ID аккаунта не найден",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data="master_profile")
            ]])
        )
        return ConversationHandler.END
    
    logger.info(f"[MASTER_DELETE] Delete confirmation step 2 requested for master_id={master_id}, user_id={user.id}")
    
    text = f"""🚨 <b>ПОСЛЕДНЕЕ ПОДТВЕРЖДЕНИЕ</b>

Вы собираетесь удалить аккаунт <b>"{master_name}"</b>.

<b>Будут удалены:</b>
❌ Ваш профиль
❌ {services_count} услуг
❌ {work_periods_count} периодов расписания
❌ {bookings_count} бронирований
❌ {clients_count} связей с клиентами

<b>⚠️ Это действие НЕОБРАТИМО!</b>

После удаления вы не сможете восстановить данные. Вы сможете зарегистрироваться заново, но все ваши данные будут потеряны.

<b>Вы абсолютно уверены, что хотите удалить аккаунт?</b>"""
    
    keyboard = [
        [InlineKeyboardButton("🗑️ ДА, УДАЛИТЬ АККАУНТ", callback_data="delete_account_confirm")],
        [InlineKeyboardButton("❌ Отмена", callback_data="delete_account_cancel")]
    ]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_DELETE_FINAL


async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финальное подтверждение и выполнение удаления аккаунта"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    try:
        master_id = context.user_data.get('delete_master_id')
        master_name = context.user_data.get('delete_master_name')
        
        if not master_id:
            logger.error(f"[MASTER_DELETE] Master ID not found in context for user {user.id}")
            await query.message.edit_text(
                "❌ Ошибка: ID аккаунта не найден",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_profile")
                ]])
            )
            return ConversationHandler.END
        
        logger.info(f"[MASTER_DELETE] Delete execution requested for master_id={master_id}, user_id={user.id}")
        
        with get_session() as session:
            # Еще раз проверяем, что мастер существует
            master = session.query(__import__('bot.database.models', fromlist=['MasterAccount']).MasterAccount).filter_by(id=master_id).first()
            
            if not master:
                logger.warning(f"[MASTER_DELETE] Master {master_id} not found during deletion")
                await query.message.edit_text(
                    "❌ Аккаунт не найден",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("« Назад", callback_data="master_profile")
                    ]])
                )
                return ConversationHandler.END
            
            # Выполняем каскадное удаление
            success = delete_master(session, master_id)
        
        if success:
            logger.info(f"[MASTER_DELETE] Master {master_id} ({master_name}) deleted successfully, user_id={user.id}")
            
            text = f"""✅ <b>Ваш аккаунт удален</b>

Ваш профиль и все данные успешно удалены из системы.

Спасибо, что использовали наш сервис! 👋

Если вы передумаете, вы сможете зарегистрироваться заново через /start."""
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Начать заново", callback_data="restart_after_delete")
                ]])
            )
            
            # Очищаем данные удаления из контекста
            context.user_data.pop('delete_master_id', None)
            context.user_data.pop('delete_services_count', None)
            context.user_data.pop('delete_work_periods_count', None)
            context.user_data.pop('delete_bookings_count', None)
            context.user_data.pop('delete_clients_count', None)
            context.user_data.pop('delete_master_name', None)
        else:
            logger.error(f"[MASTER_DELETE] Failed to delete master {master_id}, user_id={user.id}")
            
            await query.message.edit_text(
                "❌ Ошибка при удалении аккаунта. Пожалуйста, попробуйте позже или свяжитесь с поддержкой.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_profile")
                ]])
            )
    
    except Exception as e:
        logger.error(f"[MASTER_DELETE] Error in delete_account_confirm: {e}", exc_info=True)
        try:
            await query.message.edit_text(
                f"❌ Ошибка при удалении аккаунта: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_profile")
                ]])
            )
        except:
            pass
    
    return ConversationHandler.END


async def delete_account_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить удаление аккаунта"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Очищаем данные удаления из контекста
    context.user_data.pop('delete_master_id', None)
    context.user_data.pop('delete_services_count', None)
    context.user_data.pop('delete_work_periods_count', None)
    context.user_data.pop('delete_bookings_count', None)
    context.user_data.pop('delete_clients_count', None)
    context.user_data.pop('delete_master_name', None)
    
    text = "❌ Удаление аккаунта отменено.\n\n"
    text += "Ваш аккаунт остался неизменным."
    
    keyboard = [[InlineKeyboardButton("« Вернуться в профиль", callback_data="master_profile")]]
    
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
    
    return ConversationHandler.END


async def restart_after_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезагрузить приложение после удаления (эквивалент /start)"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Очищаем весь контекст пользователя
    context.user_data.clear()
    
    # Импортируем start_master для повторной регистрации
    from bot.handlers.master.menu import start_master
    
    # Вызываем start_master как будто это была команда /start
    await start_master(update, context)
