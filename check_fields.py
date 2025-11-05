"""Проверка полей в базе данных"""
from bot.database.db import get_session, get_all_locations, get_fields_by_location

def main():
    with get_session() as session:
        locations = get_all_locations(session)
        print(f"Найдено локаций: {len(locations)}")
        
        for loc in locations:
            print(f"\nЛокация: {loc.name} (ID: {loc.id})")
            fields = get_fields_by_location(session, loc.id)
            print(f"  Найдено полей: {len(fields)}")
            
            if fields:
                for field in fields:
                    print(f"  - ID: {field.id}, Название: {field.name}, Цена: {field.price_per_hour}")
            else:
                print("  Полей не найдено!")

if __name__ == "__main__":
    main()
