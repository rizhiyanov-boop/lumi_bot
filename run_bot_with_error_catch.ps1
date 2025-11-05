# Script for starting bot with error display
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Master Bot" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Directory: $scriptDir" -ForegroundColor Yellow
Write-Host ""

# Check Python availability
$pythonPath = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
if (-not $pythonPath) {
    Write-Host "ERROR: Python not found in PATH!" -ForegroundColor Red
    Write-Host "Press any key to exit..."
    Read-Host
    exit 1
}

Write-Host "Python: $pythonPath" -ForegroundColor Cyan
Write-Host ""

# Check if file exists
if (-not (Test-Path "run_master.py")) {
    Write-Host "ERROR: File run_master.py not found!" -ForegroundColor Red
    Write-Host "Press any key to exit..."
    Read-Host
    exit 1
}

Write-Host "Starting bot..." -ForegroundColor Green
Write-Host ""

# Run bot and catch errors
& $pythonPath run_master.py

# If we got here, program finished
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "Program finished with error code: $exitCode" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press Enter to close..." -ForegroundColor Gray
Read-Host
