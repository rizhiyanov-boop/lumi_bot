"""Проверка локаций в базе данных"""
from bot.database.db import get_session, get_all_locations

def main():
    with get_session() as session:
        locations = get_all_locations(session)
        print(f"Найдено локаций: {len(locations)}")
        
        if locations:
            for loc in locations:
                print(f"- ID: {loc.id}, Название: {loc.name}, Активна: {loc.active}")
        else:
            print("Локаций не найдено!")

if __name__ == "__main__":
    main()
