"""Интеграция с API ЮKassa для приема платежей"""
import requests
import uuid
import logging
from typing import Optional, Dict, Any
from bot.config import (
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_API_URL,
    PREMIUM_PRICE,
    PREMIUM_DURATION_DAYS
)

logger = logging.getLogger(__name__)


def create_payment(
    amount: float,
    description: str,
    return_url: str,
    master_id: int,
    subscription_type: str = 'premium'
) -> Optional[Dict[str, Any]]:
    """
    Создать платеж в ЮKassa
    
    Args:
        amount: Сумма платежа
        description: Описание платежа
        return_url: URL для возврата пользователя после оплаты
        master_id: ID мастера
        subscription_type: Тип подписки (premium, basic, etc.)
    
    Returns:
        Словарь с данными платежа или None в случае ошибки
    """
    if not YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SECRET_KEY not configured")
        return None
    
    # Генерируем уникальный ключ идемпотентности
    idempotence_key = str(uuid.uuid4())
    
    # Подготовка данных для запроса
    payment_data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,  # Автоматическое списание после оплаты
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "description": description[:128],  # Максимум 128 символов
        "metadata": {
            "master_id": str(master_id),
            "subscription_type": subscription_type
        }
    }
    
    try:
        # Аутентификация через Basic Auth (shop_id:secret_key)
        auth = (YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        
        headers = {
            "Idempotence-Key": idempotence_key,
            "Content-Type": "application/json"
        }
        
        logger.info(f"Creating payment for master {master_id}, amount: {amount} RUB")
        
        response = requests.post(
            YOOKASSA_API_URL,
            json=payment_data,
            auth=auth,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            payment = response.json()
            logger.info(f"Payment created successfully: {payment.get('id')}")
            return payment
        else:
            logger.error(f"Failed to create payment: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        return None


def get_payment_status(payment_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить статус платежа по ID
    
    Args:
        payment_id: ID платежа от ЮKassa
    
    Returns:
        Словарь с данными платежа или None в случае ошибки
    """
    if not YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SECRET_KEY not configured")
        return None
    
    try:
        auth = (YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        
        response = requests.get(
            f"{YOOKASSA_API_URL}/{payment_id}",
            auth=auth,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to get payment status: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting payment status: {e}", exc_info=True)
        return None


def create_premium_payment(master_id: int, return_url: str) -> Optional[Dict[str, Any]]:
    """
    Создать платеж для премиум подписки
    
    Args:
        master_id: ID мастера
        return_url: URL для возврата после оплаты
    
    Returns:
        Словарь с данными платежа или None в случае ошибки
    """
    description = f"Премиум подписка на {PREMIUM_DURATION_DAYS} дней"
    return create_payment(
        amount=PREMIUM_PRICE,
        description=description,
        return_url=return_url,
        master_id=master_id,
        subscription_type='premium'
    )

