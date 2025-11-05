@echo off
echo ============================================================
echo Lumi Beauty - Dependency Check
echo ============================================================
echo.

REM Ищем Python
set PYTHON_CMD=
if exist "C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe" (
    set PYTHON_CMD=C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe
) else if exist "C:\Python310\python.exe" (
    set PYTHON_CMD=C:\Python310\python.exe
) else (
    echo [ERROR] Python 3.10 not found!
    echo.
    echo Please update the script with your Python path
    pause
    exit /b 1
)

echo Running dependency check...
echo.
%PYTHON_CMD% check_dependencies.py

echo.
echo ============================================================
echo If any errors found, run:
echo   install_dependencies.bat
echo ============================================================
echo.
pause

