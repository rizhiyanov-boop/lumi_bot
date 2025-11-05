#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для пересоздания базы данных с правильной схемой
"""
import os
import sys

def main():
    print("=" * 60)
    print("Database Migration Script")
    print("=" * 60)
    
    # Проверка наличия старой БД
    db_path = "database.db"
    backup_path = "database.db.backup"
    
    if os.path.exists(db_path):
        print(f"\nFound existing database: {db_path}")
        
        # Создаем backup
        if not os.path.exists(backup_path):
            import shutil
            shutil.copy2(db_path, backup_path)
            print(f"Backup created: {backup_path}")
        else:
            print(f"Backup already exists: {backup_path}")
        
        # Удаляем старую БД (без подтверждения для автоматизации)
        os.remove(db_path)
        print("Old database deleted.")
    else:
        print(f"\nNo existing database found at {db_path}")
    
    # Пересоздаем БД
    print("\nCreating new database with correct schema...")
    try:
        from bot.database.db import init_db
        init_db()
        print("✅ Database created successfully!")
        print("\nYou can now restart the bots.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

