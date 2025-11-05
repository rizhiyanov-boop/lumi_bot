@echo off
echo Manual Installation Script
echo ========================
echo.

REM Прямой путь к Python 3.10
set PYTHON=C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe

if not exist "%PYTHON%" (
    echo ERROR: Python 3.10 not found at %PYTHON%
    echo.
    echo Please update the PYTHON variable in this script with your Python path
    echo Or run manually: pip install -r requirements.txt
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
echo.

echo Step 1: Upgrading pip...
"%PYTHON%" -m pip install --upgrade pip
echo.

echo Step 2: Installing dependencies...
"%PYTHON%" -m pip install python-telegram-bot==22.5
"%PYTHON%" -m pip install sqlalchemy==2.0.44
"%PYTHON%" -m pip install python-dotenv==1.0.0
"%PYTHON%" -m pip install qrcode==8.2
"%PYTHON%" -m pip install pillow==12.0.0

echo.
echo Installation complete!
echo.
echo Next steps:
echo 1. Make sure .env file exists with bot tokens
echo 2. Run start_master.bat
echo 3. Run start_client.bat
echo.
pause

