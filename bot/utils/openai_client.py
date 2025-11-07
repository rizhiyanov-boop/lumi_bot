"""Утилита для работы с OpenAI API для генерации описаний услуг"""
import logging
import os
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = None

if OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        client = None
else:
    logger.warning("OPENAI_API_KEY not found in environment variables")


async def generate_service_description(service_name: str, retry_count: int = 0) -> Optional[str]:
    """
    Генерирует описание услуги с помощью GPT-4o mini
    
    Args:
        service_name: Название услуги
        retry_count: Количество попыток (для вариативности при повторных генерациях)
    
    Returns:
        Сгенерированное описание или None в случае ошибки
    """
    if not client:
        logger.error("OpenAI client is not initialized")
        return None
    
    # Промпт для генерации описания
    # Добавляем вариативность через разные инструкции для повторных генераций
    variation_instructions = [
        "Акцент на профессиональный подход и качество результата.",
        "Подчеркни удобство и комфорт для клиента.",
        "Сделай акцент на уникальности и индивидуальном подходе.",
        "Выдели преимущества и выгоды для клиента.",
        "Сфокусируйся на результате и положительных эмоциях."
    ]
    
    variation = variation_instructions[retry_count % len(variation_instructions)]
    
    prompt = f"""Создай короткое, продающее описание услуги на русском языке (до 40 слов).

Стиль — лёгкий, дружелюбный, с 1–2 уместными эмодзи.
{variation}
Не указывай цены, контакты, ссылки или упоминания брендов.
Описание должно звучать естественно и привлекательно для клиента.

Услуга: {service_name}

Ответь только описанием услуги, без дополнительных пояснений."""

    try:
        logger.info(f"Generating description for service: {service_name} (attempt {retry_count + 1})")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — профессиональный копирайтер, создающий короткие продающие описания услуг для мастеров красоты и здоровья."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.8 + (retry_count * 0.1),  # Увеличиваем температуру для вариативности
            max_tokens=150,
            timeout=10.0
        )
        
        description = response.choices[0].message.content.strip()
        
        # Очищаем описание от кавычек, если они есть
        description = description.strip('"\'«»')
        
        # Проверяем длину (до 40 слов = примерно 300 символов)
        if len(description) > 300:
            # Обрезаем до 300 символов и добавляем ...
            description = description[:297] + "..."
        
        logger.info(f"Generated description: {description[:50]}...")
        return description
        
    except Exception as e:
        logger.error(f"Error generating service description: {e}", exc_info=True)
        return None

