#!/usr/bin/env python3
"""Запуск тестового мастер-бота с переменными из .env.test"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def main():
    # Переходим в корень проекта
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    os.chdir(project_root)
    
    # Добавляем корень проекта в sys.path для импорта модулей
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Загружаем .env.test
    env_test_path = project_root / '.env.test'
    if not env_test_path.exists():
        print("[ERROR] Файл .env.test не найден в корне репозитория.")
        input("Нажмите Enter для выхода...")
        return 1
    
    load_dotenv(env_test_path)
    
    # Проверяем токен
    test_token = os.getenv('TEST_MASTER_BOT_TOKEN')
    if not test_token:
        print("[ERROR] TEST_MASTER_BOT_TOKEN не задан в .env.test")
        input("Нажмите Enter для выхода...")
        return 1
    
    # Устанавливаем переменные окружения
    os.environ['BOT_TOKEN'] = test_token
    
    test_db_url = os.getenv('TEST_DATABASE_URL', 'sqlite:///test_database_e2e.db')
    os.environ['DATABASE_URL'] = test_db_url
    
    print("[INFO] DATABASE_URL=", test_db_url)
    print("[INFO] BOT_TOKEN установлен.")
    print("[INFO] Запуск мастер-бота...")
    print()
    
    # Запускаем бота
    try:
        from bot.main_master import main as run_master
        run_master()
    except KeyboardInterrupt:
        print("\n[INFO] Остановка бота...")
        return 0
    except Exception as e:
        print(f"\n[ERROR] Ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()
        input("\nНажмите Enter для выхода...")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

