"""Утилиты для определения города по геолокации"""
import logging
import requests
from typing import Optional, Dict, Tuple, List, Any

logger = logging.getLogger(__name__)

# Кэш для переводов названий городов (чтобы не делать лишние запросы)
CITY_NAME_CACHE = {}


def get_city_from_location(latitude: float, longitude: float) -> Optional[Dict[str, str]]:
    """
    Определить город по координатам используя Nominatim API
    
    Args:
        latitude: Широта
        longitude: Долгота
    
    Returns:
        Dict с ключами: name_ru, name_local, name_en, country_code, latitude, longitude
        или None, если не удалось определить
        
    Note:
        latitude и longitude в возвращаемом словаре - это координаты центра города
    """
    try:
        # Используем Nominatim API (OpenStreetMap) - бесплатный и не требует API ключа
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': latitude,
            'lon': longitude,
            'format': 'json',
            'accept-language': 'ru,en',  # Приоритет русскому и английскому
            'addressdetails': 1
        }
        
        headers = {
            'User-Agent': 'LumiBot/1.0'  # Требуется Nominatim
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if not data or 'address' not in data:
            logger.warning(f"Could not get address from Nominatim for {latitude}, {longitude}")
            return None
        
        address = data.get('address', {})
        
        # Определяем название города
        # В разных странах город может быть в разных полях
        city_name = (
            address.get('city') or 
            address.get('town') or 
            address.get('village') or 
            address.get('municipality') or
            address.get('city_district') or
            address.get('county')
        )
        
        if not city_name:
            logger.warning(f"Could not find city name in address: {address}")
            return None
        
        # Получаем страну
        country = address.get('country', '')
        country_code = address.get('country_code', '').upper()
        
        # Получаем координаты центра города (если есть)
        lat = float(data.get('lat', latitude))
        lon = float(data.get('lon', longitude))
        
        # Определяем названия на разных языках
        # Для русскоязычных стран используем русское название как основное
        name_ru = city_name
        name_local = city_name
        name_en = city_name
        
        # Пытаемся получить английское название через дополнительный запрос
        if country_code in ['RU', 'BY', 'KZ', 'UA', 'KG', 'TJ', 'UZ', 'TM', 'MD', 'AM', 'AZ', 'GE']:
            # Для стран СНГ русское название - основное
            name_ru = city_name
            name_local = city_name
            
            # Пробуем получить английское название
            try:
                en_response = requests.get(
                    url,
                    params={
                        'lat': latitude,
                        'lon': longitude,
                        'format': 'json',
                        'accept-language': 'en',
                        'addressdetails': 1
                    },
                    headers=headers,
                    timeout=10
                )
                if en_response.status_code == 200:
                    en_data = en_response.json()
                    en_address = en_data.get('address', {})
                    name_en = (
                        en_address.get('city') or 
                        en_address.get('town') or 
                        en_address.get('village') or 
                        en_address.get('municipality') or
                        city_name
                    )
            except Exception as e:
                logger.warning(f"Could not get English name for city: {e}")
                name_en = city_name
        else:
            # Для других стран местное название - основное, русское и английское одинаковые
            name_local = city_name
            name_ru = city_name
            name_en = city_name
        
        return {
            'name_ru': name_ru,
            'name_local': name_local,
            'name_en': name_en,
            'country_code': country_code,
            'latitude': lat,
            'longitude': lon
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting city from location: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_city_from_location: {e}", exc_info=True)
        return None


def normalize_city_name(name: str) -> str:
    """Нормализовать название города (убрать лишние пробелы, привести к нужному формату)"""
    return name.strip()


def search_city_by_name(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Поиск города по названию используя Nominatim API (forward geocoding)
    
    Args:
        query: Название города для поиска
        limit: Максимальное количество результатов
    
    Returns:
        Список словарей с информацией о городах:
        [{
            'name_ru': str,
            'name_local': str,
            'name_en': str,
            'country_code': str,
            'latitude': float,
            'longitude': float,
            'display_name': str  # Полное название для отображения
        }, ...]
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': limit,
            'addressdetails': 1,
            'accept-language': 'ru,en',
            'type': 'city',  # Ищем только города
            'featuretype': 'city,town,village'  # Типы населенных пунктов
        }
        
        headers = {
            'User-Agent': 'LumiBot/1.0'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if not data or not isinstance(data, list):
            logger.warning(f"No results found for city query: {query}")
            return []
        
        results = []
        for item in data:
            address = item.get('address', {})
            
            # Определяем название города и его тип
            city_name = None
            city_type = None
            
            if address.get('city'):
                city_name = address.get('city')
                city_type = 'city'
            elif address.get('town'):
                city_name = address.get('town')
                city_type = 'town'
            elif address.get('village'):
                city_name = address.get('village')
                city_type = 'village'
            elif address.get('municipality'):
                city_name = address.get('municipality')
                city_type = 'municipality'
            elif address.get('city_district'):
                city_name = address.get('city_district')
                city_type = 'city_district'
            
            if not city_name:
                continue
            
            country_code = address.get('country_code', '').upper()
            country = address.get('country', '')
            
            # Получаем координаты
            lat = float(item.get('lat', 0))
            lon = float(item.get('lon', 0))
            
            # Получаем полное название для отображения
            display_name = item.get('display_name', city_name)
            
            # Определяем названия на разных языках
            name_ru = city_name
            name_local = city_name
            name_en = city_name
            
            # Для стран СНГ пытаемся получить английское название
            if country_code in ['RU', 'BY', 'KZ', 'UA', 'KG', 'TJ', 'UZ', 'TM', 'MD', 'AM', 'AZ', 'GE']:
                # Для стран СНГ русское название - основное
                name_ru = city_name
                name_local = city_name
                # Английское название может быть в display_name или нужно искать отдельно
                # Пока используем русское название
                name_en = city_name
            else:
                # Для других стран местное название - основное
                name_local = city_name
                name_ru = city_name
                name_en = city_name
            
            results.append({
                'name_ru': name_ru,
                'name_local': name_local,
                'name_en': name_en,
                'country_code': country_code,
                'country': country,
                'latitude': lat,
                'longitude': lon,
                'display_name': display_name,
                'city_type': city_type  # Тип населенного пункта
            })
        
        logger.info(f"Found {len(results)} cities for query '{query}'")
        return results
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching city by name: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in search_city_by_name: {e}", exc_info=True)
        return []

