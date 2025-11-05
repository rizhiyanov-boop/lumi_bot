"""
Утилиты для защиты от спама и дебаунсинга
"""
import asyncio
from typing import Dict, Any, Callable
from datetime import datetime, timedelta
from functools import wraps

# Словарь для хранения последних действий пользователей
_user_last_action: Dict[int, datetime] = {}
_user_processing: Dict[int, bool] = {}

def debounce(seconds: float = 0.5):
    """
    Декоратор для защиты от спама - блокирует повторные вызовы в течение указанного времени
    
    Args:
        seconds: Минимальный интервал между вызовами в секундах
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            now = datetime.now()
            
            # Проверяем, не обрабатывается ли уже запрос от этого пользователя
            if _user_processing.get(user_id, False):
                await update.callback_query.answer("⏳ Обрабатываю предыдущий запрос...")
                return
            
            # Проверяем дебаунс
            last_action = _user_last_action.get(user_id)
            if last_action and (now - last_action).total_seconds() < seconds:
                await update.callback_query.answer("⏳ Слишком быстро! Подождите немного...")
                return
            
            # Устанавливаем флаг обработки
            _user_processing[user_id] = True
            _user_last_action[user_id] = now
            
            try:
                result = await func(update, context, *args, **kwargs)
                return result
            finally:
                # Снимаем флаг обработки
                _user_processing[user_id] = False
                
        return wrapper
    return decorator

def rate_limit(max_calls: int = 10, window_seconds: int = 60):
    """
    Декоратор для ограничения частоты вызовов
    
    Args:
        max_calls: Максимальное количество вызовов
        window_seconds: Окно времени в секундах
    """
    _user_calls: Dict[int, list] = {}
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            now = datetime.now()
            
            # Очищаем старые вызовы
            if user_id in _user_calls:
                _user_calls[user_id] = [
                    call_time for call_time in _user_calls[user_id]
                    if (now - call_time).total_seconds() < window_seconds
                ]
            else:
                _user_calls[user_id] = []
            
            # Проверяем лимит
            if len(_user_calls[user_id]) >= max_calls:
                await update.callback_query.answer(
                    f"🚫 Слишком много запросов! Попробуйте через {window_seconds} секунд.",
                    show_alert=True
                )
                return
            
            # Добавляем текущий вызов
            _user_calls[user_id].append(now)
            
            return await func(update, context, *args, **kwargs)
            
        return wrapper
    return decorator

async def show_typing_indicator(update, context, duration: float = 1.0):
    """Показать индикатор печати"""
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        await asyncio.sleep(duration)
    except Exception:
        pass  # Игнорируем ошибки индикатора печати
