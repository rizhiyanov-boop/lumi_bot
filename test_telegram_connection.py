#!/usr/bin/env python3
"""Тестовый скрипт для проверки подключения к Telegram API"""
import os
import asyncio
import httpx
from bot.config import BOT_TOKEN

async def test_connection():
    """Тестирует подключение к Telegram API"""
    print(f"Тестируем подключение к Telegram API...")
    print(f"Токен: {BOT_TOKEN[:10]}...")
    
    # Пытаемся подключиться через IPv4
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    
    try:
        # Используем HTTP/1.1 и увеличенные таймауты
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0),
            http2=False  # Отключаем HTTP/2
        ) as client:
            print("Отправляем запрос...")
            response = await client.get(url)
            print(f"Статус: {response.status_code}")
            print(f"Ответ: {response.text}")
            
            if response.status_code == 200:
                print("✅ Подключение работает!")
                return True
            else:
                print(f"❌ Ошибка: {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Устанавливаем приоритет IPv4
    os.environ.setdefault("PREFER_IPV4", "1")
    
    result = asyncio.run(test_connection())
    exit(0 if result else 1)

