"""Миграция: добавление полей для категорий услуг (эмодзи, предустановленность)"""
import sqlite3
import os
from datetime import datetime

DB_PATH = "database.db"
BACKUP_PATH = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

def migrate():
    """Добавить новые поля в таблицу service_categories"""
    
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
    cursor.execute("PRAGMA table_info(service_categories)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    print(f"[3/3] Проверка и добавление полей...")
    changes_made = False
    
    # Добавляем emoji
    if 'emoji' not in existing_columns:
        print("   + Добавление поля emoji...")
        cursor.execute("""
            ALTER TABLE service_categories 
            ADD COLUMN emoji VARCHAR(10)
        """)
        changes_made = True
        print("   [OK] emoji добавлено")
    else:
        print("   [SKIP] emoji уже существует")
    
    # Добавляем is_predefined
    if 'is_predefined' not in existing_columns:
        print("   + Добавление поля is_predefined...")
        cursor.execute("""
            ALTER TABLE service_categories 
            ADD COLUMN is_predefined BOOLEAN DEFAULT 0
        """)
        cursor.execute("""
            UPDATE service_categories 
            SET is_predefined = 0 
            WHERE is_predefined IS NULL
        """)
        changes_made = True
        print("   [OK] is_predefined добавлено")
    else:
        print("   [SKIP] is_predefined уже существует")
    
    # Добавляем category_key
    if 'category_key' not in existing_columns:
        print("   + Добавление поля category_key...")
        cursor.execute("""
            ALTER TABLE service_categories 
            ADD COLUMN category_key VARCHAR(50)
        """)
        changes_made = True
        print("   [OK] category_key добавлено")
    else:
        print("   [SKIP] category_key уже существует")
    
    conn.commit()
    conn.close()
    
    if changes_made:
        print(f"\n[OK] Миграция завершена успешно!")
        print(f"   Резервная копия: {BACKUP_PATH}")
    else:
        print(f"\n[OK] Все поля уже существуют, миграция не требуется")
        if os.path.exists(BACKUP_PATH):
            os.remove(BACKUP_PATH)
            print(f"   Резервная копия удалена (не нужна)")


if __name__ == '__main__':
    print("=" * 50)
    print("Миграция БД: добавление полей для категорий услуг")
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



