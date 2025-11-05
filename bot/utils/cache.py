"""
Система кэширования для оптимизации производительности
"""
import asyncio
import json
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from functools import wraps

# Простой in-memory кэш
_cache: Dict[str, Dict[str, Any]] = {}

class CacheManager:
    """Менеджер кэша с TTL (Time To Live)"""
    
    @staticmethod
    def get(key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if key not in _cache:
            return None
        
        entry = _cache[key]
        if datetime.now() > entry['expires_at']:
            del _cache[key]
            return None
        
        return entry['value']
    
    @staticmethod
    def set(key: str, value: Any, ttl_seconds: int = 300):
        """Установить значение в кэш"""
        _cache[key] = {
            'value': value,
            'expires_at': datetime.now() + timedelta(seconds=ttl_seconds)
        }
    
    @staticmethod
    def delete(key: str):
        """Удалить значение из кэша"""
        if key in _cache:
            del _cache[key]
    
    @staticmethod
    def clear():
        """Очистить весь кэш"""
        _cache.clear()
    
    @staticmethod
    def cleanup():
        """Очистить истекшие записи"""
        now = datetime.now()
        expired_keys = [
            key for key, entry in _cache.items()
            if now > entry['expires_at']
        ]
        for key in expired_keys:
            del _cache[key]

def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов функций
    
    Args:
        ttl_seconds: Время жизни кэша в секундах
        key_prefix: Префикс для ключа кэша
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Создаем ключ кэша на основе аргументов
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Пытаемся получить из кэша
            cached_result = CacheManager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Выполняем функцию и кэшируем результат
            result = await func(*args, **kwargs)
            CacheManager.set(cache_key, result, ttl_seconds)
            
            return result
        return wrapper
    return decorator

# Специальные кэш-ключи для часто используемых данных
class CacheKeys:
    PARTICIPATION_PRICING = "participation_pricing"
    SERVICES = "services"
    ADDONS = "addons"
    # УДАЛЕНО: LOCATIONS, get_locations_key - старый код для paintball проекта
    
    @staticmethod
    def get_participation_pricing_key(club_id: int, service_code: str) -> str:
        return f"{CacheKeys.PARTICIPATION_PRICING}:{club_id}:{service_code}"
    
    @staticmethod
    def get_services_key(club_id: int) -> str:
        return f"{CacheKeys.SERVICES}:{club_id}"
    
    @staticmethod
    def get_addons_key(service_id: int) -> str:
        return f"{CacheKeys.ADDONS}:{service_id}"

# Периодическая очистка кэша
async def cleanup_cache_task():
    """Задача для периодической очистки кэша"""
    while True:
        try:
            CacheManager.cleanup()
            await asyncio.sleep(60)  # Очищаем каждую минуту
        except Exception:
            await asyncio.sleep(60)
