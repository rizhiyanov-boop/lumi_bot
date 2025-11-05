"""RBAC утилиты и декораторы"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from bot.database.db import get_session, is_superadmin, get_user_club_roles
from bot.database.models import RoleType


def require_superadmin(func):
    """Декоратор для суперадмина"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        import logging
        logger = logging.getLogger(__name__)
        
        user = update.effective_user
        if not user:
            logger.warning(f"[RBAC] require_superadmin: No user in update for {func.__name__}")
            return
        
        logger.info(f"[RBAC] require_superadmin check for user_id={user.id} in {func.__name__}")
        
        if not is_superadmin(user.id):
            logger.warning(f"[RBAC] User {user.id} is NOT superadmin, blocking access to {func.__name__}")
            if update.callback_query:
                await update.callback_query.answer("❌ Только для суперадмина", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Только для суперадмина")
            return
        
        logger.info(f"[RBAC] User {user.id} IS superadmin, allowing access to {func.__name__}")
        return await func(update, context)
    return wrapper


def require_role(required_role: RoleType):
    """Декоратор для проверки роли в рамках клуба.
    Ожидает, что context.user_data['club_id'] установлен ранее (например, через /start с deep-link).
    Для совместимости, если club_id нет, будет использовать club_id=1 (дефолт).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not user:
                return
            if is_superadmin(user.id):
                return await func(update, context)
            club_id = context.user_data.get('club_id') or 1
            with get_session() as session:
                roles = get_user_club_roles(session, user.id, club_id)
                if not any(r.role == required_role and r.active for r in roles):
                    if update.callback_query:
                        await update.callback_query.answer("❌ Недостаточно прав", show_alert=True)
                    elif update.message:
                        await update.message.reply_text("❌ Недостаточно прав")
                    return
            return await func(update, context)
        return wrapper
    return decorator


def require_any_role(*required_roles: RoleType):
    """Декоратор для проверки нескольких ролей (ИЛИ).
    Пользователь должен иметь хотя бы одну из указанных ролей.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not user:
                return
            # Superadmin всегда имеет доступ
            if is_superadmin(user.id):
                return await func(update, context)
            club_id = context.user_data.get('club_id') or 1
            with get_session() as session:
                roles = get_user_club_roles(session, user.id, club_id)
                has_required_role = any(
                    r.role in required_roles and r.active 
                    for r in roles
                )
                if not has_required_role:
                    if update.callback_query:
                        await update.callback_query.answer("❌ Недостаточно прав", show_alert=True)
                    elif update.message:
                        await update.message.reply_text("❌ Недостаточно прав")
                    return
            return await func(update, context)
        return wrapper
    return decorator


