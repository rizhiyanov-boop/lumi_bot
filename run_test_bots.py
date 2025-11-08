#!/usr/bin/env python3
"""
Скрипт для запуска тестовых ботов с тестовой БД
Используется для E2E тестирования
"""
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

def main():
    """Запускает тестовые боты с тестовой БД"""
    
    # Загружаем переменные из .env.test
    env_test_path = Path('.env.test')
    if not env_test_path.exists():
        print("[ERROR] Файл .env.test не найден!")
        print("Создайте .env.test на основе tests/e2e/telethon_e2e/EXAMPLE.env.test")
        return 1
    
    # Загружаем переменные окружения из .env.test
    load_dotenv('.env.test')
    
    # Получаем URL тестовой БД
    test_db_url = os.getenv('TEST_DATABASE_URL', 'sqlite:///test_database_e2e.db')
    
    print("=" * 50)
    print("Запуск тестовых ботов для E2E тестов")
    print("=" * 50)
    print()
    print(f"Тестовая БД: {test_db_url}")
    print()
    print("⚠️  ВАЖНО: Установите DATABASE_URL={test_db_url} в .env для тестовых ботов")
    print("   или запустите боты с переменной окружения DATABASE_URL")
    print()
    
    # Устанавливаем переменную окружения для тестовой БД
    env = os.environ.copy()
    env['DATABASE_URL'] = test_db_url
    
    # Проверяем наличие токенов
    master_token = os.getenv('TEST_MASTER_BOT_TOKEN') or os.getenv('BOT_TOKEN')
    client_token = os.getenv('TEST_CLIENT_BOT_TOKEN') or os.getenv('CLIENT_BOT_TOKEN')
    
    if not master_token:
        print("[ERROR] TEST_MASTER_BOT_TOKEN или BOT_TOKEN не установлен!")
        return 1
    
    if not client_token:
        print("[ERROR] TEST_CLIENT_BOT_TOKEN или CLIENT_BOT_TOKEN не установлен!")
        return 1
    
    print("=" * 50)
    print("Запуск мастер-бота...")
    print("=" * 50)
    print()
    
    # Запускаем мастер-бота
    master_process = subprocess.Popen(
        [sys.executable, 'run_master.py'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print(f"Мастер-бот запущен (PID: {master_process.pid})")
    print()
    
    print("=" * 50)
    print("Запуск клиент-бота...")
    print("=" * 50)
    print()
    
    # Запускаем клиент-бота
    client_process = subprocess.Popen(
        [sys.executable, 'run_client.py'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print(f"Клиент-бот запущен (PID: {client_process.pid})")
    print()
    print("=" * 50)
    print("Тестовые боты запущены!")
    print("=" * 50)
    print()
    print("Для остановки нажмите Ctrl+C")
    print()
    
    try:
        # Ждем завершения процессов
        master_process.wait()
        client_process.wait()
    except KeyboardInterrupt:
        print()
        print("Остановка ботов...")
        master_process.terminate()
        client_process.terminate()
        master_process.wait()
        client_process.wait()
        print("Боты остановлены")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

