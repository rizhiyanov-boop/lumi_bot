"""Утилиты для имперсонации мастера администратором"""
from telegram import Update
from telegram.ext import ContextTypes


def get_master_telegram_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получить Telegram ID мастера с учетом имперсонации.
    Если админ работает от лица мастера, возвращает Telegram ID мастера.
    Иначе возвращает Telegram ID текущего пользователя.
    """
    user = update.effective_user
    
    # Проверяем, активна ли имперсонация
    if context.user_data.get('impersonating') and 'impersonated_master_telegram_id' in context.user_data:
        return context.user_data['impersonated_master_telegram_id']
    
    # Обычный режим - возвращаем ID текущего пользователя
    return user.id


def is_impersonating(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, активна ли имперсонация"""
    return context.user_data.get('impersonating', False)


def get_impersonation_banner(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Получить баннер имперсонации для отображения в интерфейсе"""
    if not is_impersonating(context):
        return ""
    
    master_name = context.user_data.get('impersonated_master_name', 'мастера')
    return f"\n\n🎭 <i>Режим администратора: работаете от лица {master_name}</i>"

