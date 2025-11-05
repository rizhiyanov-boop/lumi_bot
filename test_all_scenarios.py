"""Автоматическая проверка всех пользовательских сценариев"""
import subprocess
import sys
import os
from pathlib import Path

def main():
    """Запуск всех тестов сценариев"""
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    print("Запуск автоматической проверки всех пользовательских сценариев...")
    print("=" * 60)
    
    # Список тестов для проверки
    test_files = [
        "tests/unit/test_calculator.py",
        "tests/unit/test_database.py", 
        "tests/integration/test_calculator_integration.py",
        "tests/integration/test_calculator_booking_integration.py",
        "tests/e2e/test_calculator_e2e.py",
        "tests/e2e/test_calculator_full_flow.py",
        "tests/e2e/test_user_scenarios.py"
    ]
    
    all_passed = True
    results = {}
    
    for test_file in test_files:
        print(f"\nПроверяем {test_file}...")
        
        cmd = ["venv\\Scripts\\python.exe", "-m", "pytest", test_file, "-v", "--tb=short"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"OK {test_file} - ПРОШЕЛ")
                results[test_file] = "PASSED"
            else:
                print(f"FAIL {test_file} - ПРОВАЛЕН")
                print(f"Ошибка: {result.stderr}")
                results[test_file] = "FAILED"
                all_passed = False
                
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT {test_file} - ТАЙМАУТ")
            results[test_file] = "TIMEOUT"
            all_passed = False
        except Exception as e:
            print(f"ERROR {test_file} - ОШИБКА: {e}")
            results[test_file] = "ERROR"
            all_passed = False
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("ИТОГОВЫЙ ОТЧЕТ:")
    print("=" * 60)
    
    for test_file, status in results.items():
        status_emoji = {
            "PASSED": "OK",
            "FAILED": "FAIL", 
            "TIMEOUT": "TIMEOUT",
            "ERROR": "ERROR"
        }
        print(f"{status_emoji[status]} {test_file}")
    
    if all_passed:
        print("\nВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("Калькулятор полностью функционален")
        print("Все пользовательские сценарии работают")
        print("Система автотестирования настроена")
    else:
        print("\nНЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ!")
        print("Требуется исправление ошибок")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
