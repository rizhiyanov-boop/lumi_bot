"""
Система мониторинга производительности бота
"""
import time
import asyncio
import logging
from typing import Dict, Any
from functools import wraps
from datetime import datetime, timedelta

# Логгер для производительности
perf_logger = logging.getLogger('bot.performance')

# Метрики производительности
_metrics = {
    'total_requests': 0,
    'slow_requests': 0,
    'error_requests': 0,
    'avg_response_time': 0.0,
    'max_response_time': 0.0,
    'requests_by_handler': {},
    'response_times': []
}

def track_performance(handler_name: str = None):
    """
    Декоратор для отслеживания производительности обработчиков
    
    Args:
        handler_name: Имя обработчика для статистики
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            start_time = time.time()
            handler = handler_name or func.__name__
            
            try:
                result = await func(update, context, *args, **kwargs)
                
                # Записываем успешное выполнение
                response_time = time.time() - start_time
                _record_metric(handler, response_time, success=True)
                
                return result
                
            except Exception as e:
                # Записываем ошибку
                response_time = time.time() - start_time
                _record_metric(handler, response_time, success=False, error=str(e))
                
                # Логируем ошибку
                perf_logger.error(f"Error in {handler}: {e}")
                raise
                
        return wrapper
    return decorator

def _record_metric(handler: str, response_time: float, success: bool, error: str = None):
    """Записать метрику производительности"""
    global _metrics
    
    _metrics['total_requests'] += 1
    
    if not success:
        _metrics['error_requests'] += 1
    
    # Обновляем время ответа
    _metrics['response_times'].append(response_time)
    
    # Ограничиваем размер списка времен ответа
    if len(_metrics['response_times']) > 1000:
        _metrics['response_times'] = _metrics['response_times'][-500:]
    
    # Обновляем среднее время ответа
    _metrics['avg_response_time'] = sum(_metrics['response_times']) / len(_metrics['response_times'])
    
    # Обновляем максимальное время ответа
    if response_time > _metrics['max_response_time']:
        _metrics['max_response_time'] = response_time
    
    # Медленные запросы (>1 секунды)
    if response_time > 1.0:
        _metrics['slow_requests'] += 1
    
    # Статистика по обработчикам
    if handler not in _metrics['requests_by_handler']:
        _metrics['requests_by_handler'][handler] = {
            'count': 0,
            'total_time': 0.0,
            'errors': 0
        }
    
    _metrics['requests_by_handler'][handler]['count'] += 1
    _metrics['requests_by_handler'][handler]['total_time'] += response_time
    
    if not success:
        _metrics['requests_by_handler'][handler]['errors'] += 1

def get_performance_stats() -> Dict[str, Any]:
    """Получить статистику производительности"""
    global _metrics
    
    # Рассчитываем статистику по обработчикам
    handler_stats = {}
    for handler, stats in _metrics['requests_by_handler'].items():
        handler_stats[handler] = {
            'count': stats['count'],
            'avg_time': stats['total_time'] / stats['count'] if stats['count'] > 0 else 0,
            'errors': stats['errors'],
            'error_rate': stats['errors'] / stats['count'] if stats['count'] > 0 else 0
        }
    
    return {
        'total_requests': _metrics['total_requests'],
        'slow_requests': _metrics['slow_requests'],
        'error_requests': _metrics['error_requests'],
        'avg_response_time': round(_metrics['avg_response_time'], 3),
        'max_response_time': round(_metrics['max_response_time'], 3),
        'error_rate': _metrics['error_requests'] / _metrics['total_requests'] if _metrics['total_requests'] > 0 else 0,
        'slow_request_rate': _metrics['slow_requests'] / _metrics['total_requests'] if _metrics['total_requests'] > 0 else 0,
        'handlers': handler_stats
    }

def reset_metrics():
    """Сбросить метрики производительности"""
    global _metrics
    _metrics = {
        'total_requests': 0,
        'slow_requests': 0,
        'error_requests': 0,
        'avg_response_time': 0.0,
        'max_response_time': 0.0,
        'requests_by_handler': {},
        'response_times': []
    }

async def log_performance_stats():
    """Периодически логировать статистику производительности"""
    while True:
        try:
            await asyncio.sleep(300)  # Каждые 5 минут
            
            stats = get_performance_stats()
            if stats['total_requests'] > 0:
                perf_logger.info(f"Performance stats: {stats}")
                
        except Exception as e:
            perf_logger.error(f"Error logging performance stats: {e}")
            await asyncio.sleep(60)

def get_slow_handlers(threshold: float = 0.5) -> Dict[str, float]:
    """Получить список медленных обработчиков"""
    slow_handlers = {}
    
    for handler, stats in _metrics['requests_by_handler'].items():
        avg_time = stats['total_time'] / stats['count'] if stats['count'] > 0 else 0
        if avg_time > threshold:
            slow_handlers[handler] = round(avg_time, 3)
    
    return slow_handlers
