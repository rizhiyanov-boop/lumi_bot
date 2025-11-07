# Скрипт для остановки всех процессов бота
Write-Host "Останавливаю все процессы Python..."
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$processes = Get-Process python -ErrorAction SilentlyContinue
if ($processes) {
    Write-Host "Предупреждение: Остались процессы Python:"
    $processes | Format-Table Id, ProcessName, StartTime
} else {
    Write-Host "Все процессы Python остановлены."
}







