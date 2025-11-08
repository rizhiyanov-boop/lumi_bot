"""Скрипт для генерации Telethon StringSession для E2E тестов"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv
import os
import sys

# Настройка кодировки для Windows консоли
if sys.platform == 'win32':
    try:
        import codecs
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

# Загружаем переменные окружения
load_dotenv(".env.test")

api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
api_hash = os.environ.get("TELEGRAM_API_HASH", "")

if not api_id or not api_hash:
    print("ERROR: TELEGRAM_API_ID и TELEGRAM_API_HASH должны быть в .env.test")
    exit(1)

async def main():
    print("=" * 50)
    print("Создание сессии Telethon...")
    print("=" * 50)
    
    # Получаем телефон из аргументов или спрашиваем
    if len(sys.argv) > 1:
        phone = sys.argv[1]
    else:
        phone = input("Введите номер телефона (с кодом страны, например +79991234567): ")
    
    # Создаем клиент с новой сессией
    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    
    try:
        print(f"\nОтправка кода на {phone}...")
        await client.connect()
        
        if not await client.is_user_authorized():
            # Отправляем код
            await client.send_code_request(phone)
            
            # Запрашиваем код
            code = input("Введите код из Telegram: ")
            
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                # Если включена двухфакторная аутентификация
                password = input("Введите пароль двухфакторной аутентификации: ")
                await client.sign_in(password=password)
        
        # Получаем строку сессии
        session_string = client.session.save()
        
        print("\n" + "=" * 50)
        print("Сессия успешно создана!")
        print("=" * 50)
        print("\nДобавь эту строку в .env.test:")
        print(f"TELETHON_TEST_SESSION={session_string}")
        print("\nСкопируй строку выше и добавь в .env.test")
        print("=" * 50)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

