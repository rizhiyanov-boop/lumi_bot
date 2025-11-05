@echo off
echo Starting Master Bot...
cd /d %~dp0

REM Используем Python 3.10 напрямую
set PYTHON_CMD=
if exist "C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe" (
    set PYTHON_CMD=C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe
) else (
    REM Пробуем через Python Launcher
    set PYTHON_CMD=py -3.10
)

%PYTHON_CMD% run_master.py

pause

