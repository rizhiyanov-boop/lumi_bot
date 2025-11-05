@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo Запуск Lumi Beauty Bots
echo ========================================
echo.

cd /d %~dp0

REM Закрываем все процессы Python
echo [1/3] Закрытие всех процессов Python...
powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.Path -like '*Python310*'} | Stop-Process -Force" 2>nul
timeout /t 1 /nobreak >nul
echo OK - все процессы Python закрыты
echo.

REM Определяем путь к Python
set PYTHON_CMD=
if exist "C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe" (
    set PYTHON_CMD=C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe
) else (
    REM Пробуем через Python Launcher
    where py >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3.10
    ) else (
        REM Пробуем просто python из PATH
        where python >nul 2>&1
        if %errorlevel% equ 0 (
            set PYTHON_CMD=python
        ) else (
            echo [ERROR] Python 3.10 не найден!
            echo Установите Python 3.10 или укажите путь в скрипте
            pause
            exit /b 1
        )
    )
)
echo [2/3] Python найден: %PYTHON_CMD%
echo.

REM Запускаем оба бота в отдельных окнах
echo [3/3] Запуск ботов...
echo   - Мастер-бот...
start "Lumi Master Bot" powershell -NoExit -Command "cd '%~dp0'; & '%PYTHON_CMD%' run_master.py"

timeout /t 2 /nobreak >nul 2>&1

echo   - Клиент-бот...
start "Lumi Client Bot" powershell -NoExit -Command "cd '%~dp0'; & '%PYTHON_CMD%' run_client.py"

echo.
echo ========================================
echo Оба бота запущены в отдельных окнах!
echo ========================================
timeout /t 3 /nobreak >nul 2>&1

