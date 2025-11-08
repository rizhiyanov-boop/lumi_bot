"""Утилиты для работы с валютами"""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Маппинг кодов стран на коды валют (ISO 4217)
COUNTRY_TO_CURRENCY: Dict[str, str] = {
    # СНГ и Восточная Европа
    'RU': 'RUB',  # Россия - Рубли
    'KZ': 'KZT',  # Казахстан - Тенге
    'BY': 'BYN',  # Беларусь - Белорусские рубли
    'UZ': 'UZS',  # Узбекистан - Сум
    'KG': 'KGS',  # Кыргызстан - Сомы
    'AM': 'AMD',  # Армения - Драм
    'GE': 'GEL',  # Грузия - Лари
    'AZ': 'AZN',  # Азербайджан - Манаты
    'MD': 'MDL',  # Молдова - Лей
    
    # Еврозона
    'LV': 'EUR',  # Латвия - Евро
    'LT': 'EUR',  # Литва - Евро
    'EE': 'EUR',  # Эстония - Евро
    'DE': 'EUR',  # Германия - Евро
    'ES': 'EUR',  # Испания - Евро
    'IT': 'EUR',  # Италия - Евро
    'FR': 'EUR',  # Франция - Евро
    'CY': 'EUR',  # Кипр - Евро
    'GR': 'EUR',  # Греция - Евро
    'NL': 'EUR',  # Нидерланды - Евро
    'FI': 'EUR',  # Финляндия - Евро
    
    # Другие страны Европы
    'GB': 'GBP',  # Великобритания - Фунты стерлингов
    'PL': 'PLN',  # Польша - Злотые
    'CZ': 'CZK',  # Чехия - Кроны
    'CH': 'CHF',  # Швейцария - Франки
    'RS': 'RSD',  # Сербия - Динары
    'NO': 'NOK',  # Норвегия - Кроны
    
    # Азия
    'IL': 'ILS',  # Израиль - Шекели
    'AE': 'AED',  # ОАЭ - Дирхамы
    'TR': 'TRY',  # Турция - Лиры
    'TH': 'THB',  # Таиланд - Бат
    'VN': 'VND',  # Вьетнам - Донги
    'ID': 'IDR',  # Индонезия - Рупии
    
    # Америка и Океания
    'US': 'USD',  # США - Доллары
    'CA': 'CAD',  # Канада - Доллары
    'AU': 'AUD',  # Австралия - Доллары
}

# Символы валют для отображения
CURRENCY_SYMBOLS: Dict[str, str] = {
    # СНГ и Восточная Европа
    'RUB': '₽',   # Рубли
    'BYN': 'Br',  # Белорусские рубли
    'KZT': '₸',   # Тенге
    'UAH': '₴',   # Гривны
    'AMD': '֏',   # Драм
    'AZN': '₼',   # Манаты
    'GEL': '₾',   # Лари
    'KGS': 'с',   # Сомы
    'MDL': 'L',   # Лей
    'UZS': 'so\'m', # Сум
    
    # Еврозона
    'EUR': '€',   # Евро
    
    # Другие страны Европы
    'GBP': '£',   # Фунты стерлингов
    'PLN': 'zł',  # Злотые
    'CZK': 'Kč',  # Чешские кроны
    'CHF': 'Fr',  # Швейцарские франки
    'RSD': 'дин', # Сербские динары
    'NOK': 'kr',  # Норвежские кроны
    
    # Азия
    'ILS': '₪',   # Шекели
    'AED': 'د.إ', # Дирхамы ОАЭ
    'TRY': '₺',   # Лиры
    'THB': '฿',   # Бат
    'VND': '₫',   # Донги
    'IDR': 'Rp',  # Рупии
    
    # Америка и Океания
    'USD': '$',   # Доллары США
    'CAD': 'C$',  # Канадские доллары
    'AUD': 'A$',  # Австралийские доллары
}

# Названия валют на русском языке (родительный падеж)
CURRENCY_NAMES_RU: Dict[str, str] = {
    # СНГ и Восточная Европа
    'RUB': 'руб',
    'BYN': 'бел. руб',
    'KZT': 'тенге',
    'UAH': 'гривен',
    'AMD': 'драм',
    'AZN': 'манат',
    'GEL': 'лари',
    'KGS': 'сом',
    'MDL': 'лей',
    'UZS': 'сум',
    
    # Еврозона
    'EUR': 'евро',
    
    # Другие страны Европы
    'GBP': 'фунтов',
    'PLN': 'злотых',
    'CZK': 'крон',
    'CHF': 'франков',
    'RSD': 'динар',
    'NOK': 'крон',
    
    # Азия
    'ILS': 'шеклей',
    'AED': 'дирхам',
    'TRY': 'лир',
    'THB': 'бат',
    'VND': 'донгов',
    'IDR': 'рупий',
    
    # Америка и Океания
    'USD': 'долларов',
    'CAD': 'долларов',
    'AUD': 'долларов',
}

# Названия валют на русском языке (предложный падеж - "в рублях", "в тенге" и т.д.)
CURRENCY_NAMES_RU_PREPOSITIONAL: Dict[str, str] = {
    # СНГ и Восточная Европа
    'RUB': 'рублях',
    'BYN': 'белорусских рублях',
    'KZT': 'тенге',
    'UAH': 'гривнах',
    'AMD': 'драмах',
    'AZN': 'манатах',
    'GEL': 'лари',
    'KGS': 'сомах',
    'MDL': 'леях',
    'UZS': 'сумах',
    
    # Еврозона
    'EUR': 'евро',
    
    # Другие страны Европы
    'GBP': 'фунтах стерлингов',
    'PLN': 'злотых',
    'CZK': 'кронах',
    'CHF': 'франках',
    'RSD': 'динарах',
    'NOK': 'кронах',
    
    # Азия
    'ILS': 'шекелях',
    'AED': 'дирхамах',
    'TRY': 'лирах',
    'THB': 'батах',
    'VND': 'донгах',
    'IDR': 'рупиях',
    
    # Америка и Океания
    'USD': 'долларах',
    'CAD': 'канадских долларах',
    'AUD': 'австралийских долларах',
}


def get_currency_by_country(country_code: Optional[str]) -> str:
    """
    Получить код валюты по коду страны (синхронная версия)
    Использует статический маппинг как fallback
    
    Args:
        country_code: Двухбуквенный код страны (ISO 3166-1 alpha-2)
        
    Returns:
        Код валюты (ISO 4217), по умолчанию RUB
    """
    if not country_code:
        return 'RUB'
    
    country_code_upper = country_code.upper()
    return COUNTRY_TO_CURRENCY.get(country_code_upper, 'RUB')


async def get_currency_by_country_async(session, country_code: Optional[str]) -> str:
    """
    Получить код валюты по коду страны с проверкой статического маппинга, базы данных и запросом к API
    
    Логика:
    1. Проверяет статический маппинг (самый быстрый способ)
    2. Если нет в статическом маппинге - проверяет базу данных
    3. Если нет в БД - запрашивает из API
    4. Сохраняет результат в БД (для новых валют из API)
    5. Использует RUB как fallback
    
    Args:
        session: SQLAlchemy session
        country_code: Двухбуквенный код страны (ISO 3166-1 alpha-2)
        
    Returns:
        Код валюты (ISO 4217), по умолчанию RUB
    """
    if not country_code:
        return 'RUB'
    
    country_code_upper = country_code.upper()
    
    # Сначала проверяем статический маппинг (самый быстрый способ)
    if country_code_upper in COUNTRY_TO_CURRENCY:
        currency_code = COUNTRY_TO_CURRENCY[country_code_upper]
        logger.debug(f"Currency {currency_code} found in static mapping for country {country_code_upper}")
        return currency_code
    
    # Если нет в статическом маппинге - проверяем базу данных
    from bot.database.models import CountryCurrency
    from bot.database.db import get_or_create_country_currency
    
    country_currency = session.query(CountryCurrency).filter_by(
        country_code=country_code_upper
    ).first()
    
    if country_currency:
        # Есть в базе данных
        logger.debug(f"Currency {country_currency.currency_code} found in DB for country {country_code_upper}")
        return country_currency.currency_code
    
    # Нет в статическом маппинге и в БД - запрашиваем из API
    logger.info(f"Currency not found in static mapping or DB for country {country_code_upper}, fetching from API...")
    
    from bot.utils.country_api import get_currency_from_api
    import asyncio
    
    # Добавляем общий таймаут для всего запроса к API (20 секунд)
    try:
        currency_data = await asyncio.wait_for(
            get_currency_from_api(country_code_upper),
            timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"Timeout while fetching currency from API for {country_code_upper} (exceeded 20 seconds)")
        currency_data = None
    except Exception as e:
        logger.error(f"Error while fetching currency from API for {country_code_upper}: {e}", exc_info=True)
        currency_data = None
    
    if currency_data:
        # Сохраняем в базу данных
        currency_code = currency_data['currency_code']
        
        # Обновляем символы валют, если их еще нет в словаре
        if currency_code not in CURRENCY_SYMBOLS and currency_data.get('currency_symbol'):
            CURRENCY_SYMBOLS[currency_code] = currency_data['currency_symbol']
            logger.info(f"Added currency symbol {currency_data.get('currency_symbol')} for {currency_code}")
        
        # Добавляем название валюты в предложном падеже, если его нет
        if currency_code not in CURRENCY_NAMES_RU_PREPOSITIONAL:
            currency_name = currency_data.get('currency_name', '').lower()
            if currency_name:
                # Используем название из API (на английском, но это лучше чем ничего)
                CURRENCY_NAMES_RU_PREPOSITIONAL[currency_code] = currency_name
                logger.info(f"Added currency name '{currency_name}' for {currency_code}")
            else:
                # Fallback: используем код валюты
                CURRENCY_NAMES_RU_PREPOSITIONAL[currency_code] = currency_code.lower()
        
        # Сохраняем в БД
        from bot.database.db import get_or_create_country_currency
        
        get_or_create_country_currency(
            session,
            country_code=country_code_upper,
            currency_code=currency_code,
            currency_name=currency_data.get('currency_name'),
            currency_symbol=currency_data.get('currency_symbol')
        )
        
        logger.info(f"Currency {currency_code} saved to DB for country {country_code_upper}")
        return currency_code
    
    # API недоступно или ошибка - используем fallback
    logger.warning(f"Could not fetch currency from API for {country_code_upper}, using RUB fallback")
    return 'RUB'


def get_currency_symbol(currency_code: str) -> str:
    """
    Получить символ валюты по коду
    
    Args:
        currency_code: Код валюты (ISO 4217)
        
    Returns:
        Символ валюты, если нет - возвращает код валюты или ₽ как fallback
    """
    if not currency_code:
        return '₽'
    currency_code_upper = currency_code.upper()
    if currency_code_upper in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[currency_code_upper]
    # Если символа нет, возвращаем код валюты
    return currency_code_upper


def format_price(amount: float, currency_code: str = 'RUB', use_symbol: bool = True) -> str:
    """
    Форматировать цену с учетом валюты
    
    Args:
        amount: Сумма
        currency_code: Код валюты (ISO 4217)
        use_symbol: Использовать символ валюты (True) или название (False)
        
    Returns:
        Отформатированная строка с ценой
    """
    # Округляем до целого, если число целое
    if amount % 1 == 0:
        amount_str = str(int(amount))
    else:
        amount_str = f"{amount:.2f}"
    
    if use_symbol:
        symbol = get_currency_symbol(currency_code)
        return f"{amount_str} {symbol}"  # Добавил пробел для лучшей читаемости
    else:
        name = CURRENCY_NAMES_RU.get(currency_code.upper(), currency_code.upper() if currency_code else 'руб')
        return f"{amount_str} {name}"

