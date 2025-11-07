"""Утилиты для работы с внешними API для получения информации о странах и валютах"""
import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# REST Countries API endpoint
REST_COUNTRIES_API_URL = "https://restcountries.com/v3.1/alpha/{code}"


async def get_currency_from_api(country_code: str) -> Optional[Dict[str, str]]:
    """
    Получить валюту для страны из внешнего API
    
    Args:
        country_code: Двухбуквенный код страны (ISO 3166-1 alpha-2)
        
    Returns:
        Словарь с информацией о валюте:
        {
            'currency_code': 'RUB',
            'currency_name': 'Russian ruble',
            'currency_symbol': '₽'
        }
        Или None в случае ошибки
    """
    if not country_code or len(country_code) != 2:
        logger.warning(f"Invalid country code: {country_code}")
        return None
    
    try:
        url = REST_COUNTRIES_API_URL.format(code=country_code.upper())
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # API может вернуть массив или объект
            if isinstance(data, list):
                if not data:
                    logger.warning(f"No data returned for country code: {country_code}")
                    return None
                data = data[0]
            
            # Получаем информацию о валютах
            currencies = data.get('currencies', {})
            
            if not currencies:
                logger.warning(f"No currencies found for country code: {country_code}")
                return None
            
            # Берем первую валюту (обычно это основная валюта страны)
            currency_code = list(currencies.keys())[0]
            currency_info = currencies[currency_code]
            
            result = {
                'currency_code': currency_code,
                'currency_name': currency_info.get('name', ''),
                'currency_symbol': currency_info.get('symbol', '')
            }
            
            logger.info(f"Successfully retrieved currency {currency_code} for country {country_code}")
            return result
            
    except httpx.TimeoutException:
        logger.error(f"Timeout while fetching currency for country code: {country_code}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while fetching currency for country code {country_code}: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error fetching currency for country code {country_code}: {e}", exc_info=True)
        return None

