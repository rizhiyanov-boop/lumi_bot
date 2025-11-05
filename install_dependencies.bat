@echo off
echo Installing dependencies...
cd /d %~dp0

echo Checking Python...

REM Ищем Python 3.10 (наиболее надежный способ)
set PYTHON_CMD=
if exist "C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe" (
    set PYTHON_CMD=C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe
    echo Found Python 3.10
) else if exist "C:\Python310\python.exe" (
    set PYTHON_CMD=C:\Python310\python.exe
    echo Found Python 3.10 in C:\Python310
) else (
    echo Searching for Python in common locations...
    REM Попробуем найти Python через where
    for /f "delims=" %%i in ('where python 2^>nul') do (
        set PYTHON_CMD=%%i
        echo Found Python at: %%i
        goto :found
    )
    
    echo.
    echo ERROR: Python not found!
    echo.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    echo Or install dependencies manually:
    echo   py -3.10 -m pip install -r requirements.txt
    echo   (if you have Python Launcher installed)
    pause
    exit /b 1
)

:found
echo Using: %PYTHON_CMD%
%PYTHON_CMD% --version
if errorlevel 1 (
    echo ERROR: Python found but cannot execute!
    pause
    exit /b 1
)

echo.
echo Installing packages from requirements.txt...
echo.
%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip!
    pause
    exit /b 1
)

%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies!
    echo Please check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo All dependencies installed successfully!
echo.
echo Next steps:
echo 1. Create .env file with your bot tokens
echo 2. Run start_master.bat (Terminal 1)
echo 3. Run start_client.bat (Terminal 2)
echo.
pause

