#!/usr/bin/env python3
"""
Скрипт для запуска E2E тестов с автоматическим запуском тестовых ботов
"""
import os
import sys
import subprocess
import time
import signal
from pathlib import Path
from dotenv import load_dotenv

def main():
    """Запускает тестовые боты и затем E2E тесты"""
    
    # Загружаем переменные из .env.test
    env_test_path = Path('.env.test')
    if not env_test_path.exists():
        print("[ERROR] Файл .env.test не найден!")
        return 1
    
    load_dotenv('.env.test')
    
    # Получаем URL тестовой БД
    test_db_url = os.getenv('TEST_DATABASE_URL', 'sqlite:///test_database_e2e.db')
    
    # Загружаем все переменные из .env.test ПЕРЕД созданием env
    load_dotenv('.env.test', override=True)
    
    # Создаем окружение с переменными из .env.test
    env = os.environ.copy()
    
    # Устанавливаем тестовую БД
    env['DATABASE_URL'] = test_db_url
    
    # Убеждаемся, что токены установлены (используем тестовые или обычные)
    if 'TEST_MASTER_BOT_TOKEN' in os.environ:
        env['BOT_TOKEN'] = os.environ['TEST_MASTER_BOT_TOKEN']
    if 'TEST_CLIENT_BOT_TOKEN' in os.environ:
        env['CLIENT_BOT_TOKEN'] = os.environ['TEST_CLIENT_BOT_TOKEN']
    
    # Проверяем наличие токенов
    master_token = env.get('BOT_TOKEN') or env.get('TEST_MASTER_BOT_TOKEN')
    client_token = env.get('CLIENT_BOT_TOKEN') or env.get('TEST_CLIENT_BOT_TOKEN')
    
    if not master_token:
        print("[ERROR] TEST_MASTER_BOT_TOKEN или BOT_TOKEN не установлен!")
        return 1
    
    if not client_token:
        print("[ERROR] TEST_CLIENT_BOT_TOKEN или CLIENT_BOT_TOKEN не установлен!")
        return 1
    
    print("=" * 50)
    print("Запуск E2E тестов с тестовыми ботами")
    print("=" * 50)
    print()
    print(f"Тестовая БД: {test_db_url}")
    print(f"Мастер-бот токен: {'Установлен' if master_token else 'НЕ УСТАНОВЛЕН!'}")
    print(f"Клиент-бот токен: {'Установлен' if client_token else 'НЕ УСТАНОВЛЕН!'}")
    print()
    
    # Запускаем мастер-бота
    print("Запуск мастер-бота...")
    master_process = subprocess.Popen(
        [sys.executable, 'run_master.py'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"Мастер-бот запущен (PID: {master_process.pid})")
    
    # Запускаем клиент-бота
    print("Запуск клиент-бота...")
    client_process = subprocess.Popen(
        [sys.executable, 'run_client.py'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"Клиент-бот запущен (PID: {client_process.pid})")
    print()
    
    # Ждем, чтобы боты инициализировались
    print("Ожидание инициализации ботов (20 секунд)...")
    for i in range(20, 0, -1):
        print(f"  Осталось {i} секунд...", end='\r')
        time.sleep(1)
        # Проверяем, что процессы еще запущены
        if master_process.poll() is not None:
            print(f"\n[ERROR] Мастер-бот завершился на {i} секунде!")
            break
        if client_process.poll() is not None:
            print(f"\n[ERROR] Клиент-бот завершился на {i} секунде!")
            break
    print("\n")
    
    # Проверяем, что процессы еще запущены
    if master_process.poll() is not None:
        print("[ERROR] Мастер-бот завершился неожиданно!")
        stdout, stderr = master_process.communicate()
        print("STDOUT:", stdout)
        print("STDERR:", stderr)
        client_process.terminate()
        return 1
    
    if client_process.poll() is not None:
        print("[ERROR] Клиент-бот завершился неожиданно!")
        stdout, stderr = client_process.communicate()
        print("STDOUT:", stdout)
        print("STDERR:", stderr)
        master_process.terminate()
        return 1
    
    print("Боты запущены и работают!")
    print()
    
    # Проверяем вывод ботов (первые строки для диагностики)
    try:
        # Неблокирующая проверка stdout ботов
        import select
        if sys.platform != 'win32':
            # На Unix можно использовать select
            pass
    except:
        pass
    
    # Выводим информацию о процессах
    print(f"Мастер-бот процесс: PID={master_process.pid}, alive={master_process.poll() is None}")
    print(f"Клиент-бот процесс: PID={client_process.pid}, alive={client_process.poll() is None}")
    print()
    
    # Принудительно выводим все в консоль
    sys.stdout.flush()
    sys.stderr.flush()
    
    print("=" * 50)
    print("Запуск E2E тестов...")
    print("=" * 50)
    print()
    
    # Принудительно выводим все в консоль перед запуском тестов
    sys.stdout.flush()
    sys.stderr.flush()
    
    try:
        # Запускаем тесты с явным выводом
        test_process = subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests/e2e/telethon_e2e', '-v', '-m', 'e2e_telethon', '--tb=short', '-s'],
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        
        return test_process.returncode
        
    except KeyboardInterrupt:
        print("\nПрерывание тестов...")
        return 130
    finally:
        # Останавливаем ботов
        print()
        print("Остановка ботов...")
        master_process.terminate()
        client_process.terminate()
        
        # Ждем завершения
        try:
            master_process.wait(timeout=5)
            client_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            master_process.kill()
            client_process.kill()
        
        print("Боты остановлены")


if __name__ == '__main__':
    sys.exit(main())

