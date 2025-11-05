#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт проверки всех зависимостей проекта Lumi Beauty
"""
import sys
import os

# Устанавливаем UTF-8 для консоли Windows
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")

def check_python_version():
    """Проверка версии Python"""
    print("Python version check...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        print(f"   [OK] Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   [ERROR] Python {version.major}.{version.minor}.{version.micro} - требуется 3.10+")
        return False

def check_module(module_name, package_name=None):
    """Проверка наличия модуля"""
    if package_name is None:
        package_name = module_name
    
    try:
        __import__(module_name)
        print(f"   [OK] {package_name}")
        return True
    except ImportError:
        print(f"   [ERROR] {package_name} - NOT INSTALLED")
        return False

def check_required_modules():
    """Проверка всех требуемых модулей"""
    print("\nChecking required modules...")
    
    modules = [
        ("telegram", "python-telegram-bot"),
        ("sqlalchemy", "sqlalchemy"),
        ("dotenv", "python-dotenv"),
        ("qrcode", "qrcode"),
        ("PIL", "pillow"),
    ]
    
    all_ok = True
    for module, package in modules:
        if not check_module(module, package):
            all_ok = False
    
    return all_ok

def check_qr_dependencies():
    """Проверка зависимостей для генерации QR"""
    print("\nChecking QR code dependencies...")
    
    try:
        import qrcode
        print("   [OK] qrcode module")
        
        import qrcode.constants
        print("   [OK] qrcode.constants")
        
        from PIL import Image
        print("   [OK] PIL.Image")
        
        from io import BytesIO
        print("   [OK] io.BytesIO")
        
        # Проверка создания QR-кода
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data("test")
        qr.make(fit=True)
        img = qr.make_image(fill_color="#000000", back_color="#ffffff")
        print("   [OK] QR code generation works!")
        
        return True
    except Exception as e:
        print(f"   [ERROR] {e}")
        return False

def check_file(file_path, required=False):
    """Проверка наличия файла"""
    import os
    exists = os.path.exists(file_path)
    status = "[OK]" if exists else ("[WARNING]" if not required else "[ERROR]")
    req_text = " (required)" if required else " (optional)"
    print(f"   {status} {file_path}{req_text}")
    return exists

def check_config_files():
    """Проверка конфигурационных файлов"""
    print("\nChecking configuration...")
    
    import os
    
    env_exists = check_file(".env", required=True)
    
    if env_exists:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            
            # Проверка переменных окружения
            required_vars = ["BOT_TOKEN", "CLIENT_BOT_TOKEN"]
            optional_vars = ["CLIENT_BOT_USERNAME", "DATABASE_URL", "SUPER_ADMINS"]
            
            print("\n   Environment variables:")
            all_ok = True
            for var in required_vars:
                value = os.getenv(var)
                if value:
                    print(f"   [OK] {var}")
                else:
                    print(f"   [ERROR] {var} - NOT SET (required!)")
                    all_ok = False
            
            for var in optional_vars:
                value = os.getenv(var)
                if value:
                    print(f"   [OK] {var}")
                else:
                    print(f"   [WARNING] {var} - not set (optional)")
            
            return all_ok
        except Exception as e:
            print(f"   [ERROR] Failed to read .env: {e}")
            return False
    else:
        return False

def check_database():
    """Проверка базы данных"""
    print("\nChecking database...")
    
    try:
        from bot.database.db import init_db, engine
        from bot.database.models import Base
        
        # Проверка инициализации
        print("   [OK] Database modules imported")
        
        # Проверка создания таблиц
        Base.metadata.create_all(bind=engine)
        print("   [OK] Database tables checked/created")
        
        return True
    except Exception as e:
        print(f"   [ERROR] Database error: {e}")
        return False

def check_logo_file():
    """Проверка файла логотипа"""
    print("\nChecking additional files...")
    
    logo_exists = check_file("logo.png", required=False)
    
    if not logo_exists:
        print("   [WARNING] logo.png not found - QR codes will be without logo")
    
    return True

def main():
    """Главная функция"""
    print("=" * 60)
    print("DEPENDENCY CHECK - Lumi Beauty Project")
    print("=" * 60)
    
    results = []
    
    # Проверки
    results.append(("Python версия", check_python_version()))
    results.append(("Модули", check_required_modules()))
    results.append(("QR-зависимости", check_qr_dependencies()))
    results.append(("Конфигурация", check_config_files()))
    results.append(("База данных", check_database()))
    results.append(("Доп. файлы", check_logo_file()))
    
    # Итоги
    print("\n" + "=" * 60)
    print("CHECK RESULTS:")
    print("=" * 60)
    
    all_ok = True
    for name, result in results:
        status = "[OK]" if result else "[ERROR]"
        print(f"{status:10} - {name}")
        if not result:
            all_ok = False
    
    print("=" * 60)
    
    if all_ok:
        print("\n[SUCCESS] All checks passed! Project is ready to run.")
        return 0
    else:
        print("\n[ERROR] Issues found. Install missing dependencies:")
        print("   pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())

