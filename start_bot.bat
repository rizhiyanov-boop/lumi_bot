@echo off
chcp 65001 >nul
echo ========================================
echo  Запуск Пейнтбол-бота
echo ========================================
echo.

cd /d "%~dp0"

echo Останавливаю все предыдущие экземпляры...
taskkill /F /IM python.exe 2>nul
timeout /t 3 /nobreak >nul

echo Запускаю бота...
echo.
start /B venv\Scripts\python.exe run.py
echo Бот запущен в фоне!
timeout /t 2 /nobreak >nul

