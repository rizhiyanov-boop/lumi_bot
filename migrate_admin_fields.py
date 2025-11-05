"""Миграция: добавление полей для админки (подписка, блокировка)"""
import sqlite3
import os
from datetime import datetime

DB_PATH = "database.db"
BACKUP_PATH = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

def migrate():
    """Добавить новые поля в таблицу master_accounts"""
    
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] База данных {DB_PATH} не найдена!")
        print("   Запустите бот - база создастся автоматически.")
        return
    
    # Создаем бэкап
    print(f"[1/3] Создание резервной копии...")
    import shutil
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"[OK] Резервная копия создана: {BACKUP_PATH}")
    
    # Подключаемся к БД
    print(f"[2/3] Подключение к базе данных...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем, какие поля уже существуют
    cursor.execute("PRAGMA table_info(master_accounts)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    print(f"[3/3] Проверка и добавление полей...")
    changes_made = False
    
    # Добавляем subscription_level
    if 'subscription_level' not in existing_columns:
        print("   + Добавление поля subscription_level...")
        cursor.execute("""
            ALTER TABLE master_accounts 
            ADD COLUMN subscription_level VARCHAR(20) DEFAULT 'free'
        """)
        # Устанавливаем дефолтное значение для существующих записей
        cursor.execute("""
            UPDATE master_accounts 
            SET subscription_level = 'free' 
            WHERE subscription_level IS NULL
        """)
        changes_made = True
        print("   [OK] subscription_level добавлено")
    else:
        print("   [SKIP] subscription_level уже существует")
    
    # Добавляем subscription_expires_at
    if 'subscription_expires_at' not in existing_columns:
        print("   + Добавление поля subscription_expires_at...")
        cursor.execute("""
            ALTER TABLE master_accounts 
            ADD COLUMN subscription_expires_at DATETIME
        """)
        changes_made = True
        print("   [OK] subscription_expires_at добавлено")
    else:
        print("   [SKIP] subscription_expires_at уже существует")
    
    # Добавляем is_blocked
    if 'is_blocked' not in existing_columns:
        print("   + Добавление поля is_blocked...")
        cursor.execute("""
            ALTER TABLE master_accounts 
            ADD COLUMN is_blocked BOOLEAN DEFAULT 0
        """)
        # Устанавливаем дефолтное значение для существующих записей
        cursor.execute("""
            UPDATE master_accounts 
            SET is_blocked = 0 
            WHERE is_blocked IS NULL
        """)
        changes_made = True
        print("   [OK] is_blocked добавлено")
    else:
        print("   [SKIP] is_blocked уже существует")
    
    # Добавляем blocked_at
    if 'blocked_at' not in existing_columns:
        print("   + Добавление поля blocked_at...")
        cursor.execute("""
            ALTER TABLE master_accounts 
            ADD COLUMN blocked_at DATETIME
        """)
        changes_made = True
        print("   [OK] blocked_at добавлено")
    else:
        print("   [SKIP] blocked_at уже существует")
    
    # Добавляем block_reason
    if 'block_reason' not in existing_columns:
        print("   + Добавление поля block_reason...")
        cursor.execute("""
            ALTER TABLE master_accounts 
            ADD COLUMN block_reason TEXT
        """)
        changes_made = True
        print("   [OK] block_reason добавлено")
    else:
        print("   [SKIP] block_reason уже существует")
    
    conn.commit()
    conn.close()
    
    if changes_made:
        print(f"\n[OK] Миграция завершена успешно!")
        print(f"   Резервная копия: {BACKUP_PATH}")
    else:
        print(f"\n[OK] Все поля уже существуют, миграция не требуется")
        # Удаляем бэкап если ничего не изменилось
        if os.path.exists(BACKUP_PATH):
            os.remove(BACKUP_PATH)
            print(f"   Резервная копия удалена (не нужна)")


if __name__ == '__main__':
    print("=" * 50)
    print("Миграция БД: добавление полей для админки")
    print("=" * 50)
    print()
    
    try:
        migrate()
    except Exception as e:
        print(f"\n[ERROR] Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n[WARNING] Если что-то пошло не так, восстановите из резервной копии: {BACKUP_PATH}")
    
    print("\n" + "=" * 50)
