# Скрипт для запуска бота с проверкой и остановкой старых процессов
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Текущая директория: $scriptDir" -ForegroundColor Green
Write-Host "Проверяю запущенные процессы бота..." -ForegroundColor Yellow

# Останавливаем все процессы Python
$processes = Get-Process python -ErrorAction SilentlyContinue
if ($processes) {
    Write-Host "Останавливаю старые процессы Python..." -ForegroundColor Yellow
    $processes | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Проверяем, что все остановлено
$remaining = Get-Process python -ErrorAction SilentlyContinue
if ($remaining) {
    Write-Host "Ошибка: Не удалось остановить все процессы!" -ForegroundColor Red
    Write-Host "Нажмите любую клавишу для выхода..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "Запускаю мастер-бот..." -ForegroundColor Green
$pythonPath = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
if (-not $pythonPath) {
    Write-Host "Ошибка: Python не найден!" -ForegroundColor Red
    Write-Host "Нажмите любую клавишу для выхода..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "Используется Python: $pythonPath" -ForegroundColor Cyan
Write-Host "Запускаю бота в новом окне..." -ForegroundColor Yellow
Start-Process -FilePath $pythonPath -ArgumentList "run_master.py" -WorkingDirectory $scriptDir -WindowStyle Normal -NoNewWindow:$false
Write-Host "Бот запущен в новом окне." -ForegroundColor Green
Write-Host ""
Write-Host "Если окно закрылось сразу - проверьте ошибки выше или запустите вручную:" -ForegroundColor Yellow
Write-Host "  python run_master.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "Нажмите любую клавишу для закрытия этого окна..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

