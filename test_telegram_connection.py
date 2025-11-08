#!/usr/bin/env python3
"""Тестовый скрипт для проверки подключения к Telegram API"""
import os
import asyncio
import httpx
import socket
from bot.config import BOT_TOKEN

class IPv4Resolver:
    """DNS resolver, который возвращает только IPv4 адреса"""
    def __init__(self, family=socket.AF_INET):
        self.family = family
    
    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        """Разрешает hostname только в IPv4 адреса"""
        # Принудительно используем IPv4
        addrinfo = await asyncio.get_event_loop().getaddrinfo(
            host, port, family=socket.AF_INET, type=socket.SOCK_STREAM
        )
        return addrinfo

async def test_connection():
    """Тестирует подключение к Telegram API"""
    print(f"Тестируем подключение к Telegram API...")
    print(f"Токен: {BOT_TOKEN[:10]}...")
    
    # Пытаемся подключиться через IPv4
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    
    try:
        # Используем HTTP/1.1 и увеличенные таймауты
        # Патч getaddrinfo уже применен, поэтому будет использоваться только IPv4
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=60.0, read=90.0, write=60.0, pool=60.0),
            http2=False,  # Отключаем HTTP/2
        ) as client:
            print("Отправляем запрос через IPv4 (патч getaddrinfo применен)...")
            response = await client.get(url)
            print(f"Статус: {response.status_code}")
            print(f"Ответ: {response.text[:200]}...")
            
            if response.status_code == 200:
                print("✅ Подключение работает через IPv4!")
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
    # Устанавливаем приоритет IPv4 на уровне системы
    os.environ.setdefault("PREFER_IPV4", "1")
    
    # Патч для принудительного использования IPv4
    original_getaddrinfo = socket.getaddrinfo
    
    def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        """Переопределяем getaddrinfo для использования только IPv4"""
        if family == socket.AF_UNSPEC or family == 0:
            family = socket.AF_INET
        elif family == socket.AF_INET6:
            family = socket.AF_INET
        return original_getaddrinfo(host, port, family, type, proto, flags)
    
    # Применяем патч для socket.getaddrinfo
    socket.getaddrinfo = getaddrinfo_ipv4_only
    
    # Патч для asyncio.getaddrinfo (если доступен)
    if hasattr(asyncio, 'getaddrinfo'):
        original_asyncio_getaddrinfo = asyncio.getaddrinfo
        
        async def asyncio_getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
            """Асинхронная версия getaddrinfo для использования только IPv4"""
            if family == socket.AF_UNSPEC or family == 0:
                family = socket.AF_INET
            elif family == socket.AF_INET6:
                family = socket.AF_INET
            return await original_asyncio_getaddrinfo(host, port, family, type, proto, flags)
        
        asyncio.getaddrinfo = asyncio_getaddrinfo_ipv4_only
        print("[INFO] Применен патч IPv4 для socket и asyncio")
    else:
        print("[INFO] Применен патч IPv4 для socket")
    
    result = asyncio.run(test_connection())
    exit(0 if result else 1)

