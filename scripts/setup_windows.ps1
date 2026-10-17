# CHOTU workstation setup + full verification on Windows 11 (PowerShell 5.1+)
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
# Creates .venv (Python 3.12), installs requirements, runs pytest, the firmware
# host tests (MSYS2 g++), and the fleet backend tests.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Python virtual environment" -ForegroundColor Cyan
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -e .

Write-Host "== Unit + end-to-end tests" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "== Firmware logic host tests (g++)" -ForegroundColor Cyan
Push-Location firmware\esp32s3_base_controller\test_host
g++ -std=c++17 -O2 -Wall -Wextra -Werror "-I../lib/chotu_logic/src" test_chotu_logic.cpp -o test_chotu_logic.exe
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "g++ build failed" }
.\test_chotu_logic.exe
$rc = $LASTEXITCODE
Remove-Item test_chotu_logic.exe
Pop-Location
if ($rc -ne 0) { throw "firmware host tests failed" }

Write-Host "== Fleet backend tests" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
& .\.venv\Scripts\python.exe -m pytest backend\tests -q
if ($LASTEXITCODE -ne 0) { throw "backend tests failed" }
Write-Host "All checks passed." -ForegroundColor Green
