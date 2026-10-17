@echo off
REM Launch the CHOTU digital twin with the live HUD window (Windows).
REM   scripts\run_sim.bat            -> room seed 2025
REM   scripts\run_sim.bat 7          -> room seed 7
REM   scripts\run_sim.bat fleet      -> 4 robots / 4 rooms dashboard
cd /d "%~dp0\.."
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
if /I "%1"=="fleet" (
    %PY% bot_simulation\run_simulation.py --fleet 4
) else if "%1"=="" (
    %PY% bot_simulation\run_simulation.py --seed 2025
) else (
    %PY% bot_simulation\run_simulation.py --seed %1
)
