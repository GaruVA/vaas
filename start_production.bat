@echo off
setlocal EnableDelayedExpansion
title VAAS - Vehicle Attendance and Analytics System

:: ═══════════════════════════════════════════════════════════════════════════════
:: VAAS Windows Production Launcher
:: Double-click this file (or run from CMD) to start the system.
:: ═══════════════════════════════════════════════════════════════════════════════

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo.
echo  ██╗   ██╗ █████╗  █████╗ ███████╗
echo  ██║   ██║██╔══██╗██╔══██╗██╔════╝
echo  ██║   ██║███████║███████║███████╗
echo  ╚██╗ ██╔╝██╔══██║██╔══██║╚════██║
echo   ╚████╔╝ ██║  ██║██║  ██║███████║
echo    ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
echo  Vehicle Attendance and Analytics System
echo  ─────────────────────────────────────────────
echo.

:: ── Step 1: Verify Python ────────────────────────────────────────────────────
echo [1/7] Checking Python installation ...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python is not installed or not on PATH.
    echo  Download from https://www.python.org/downloads/ (version 3.11+^)
    echo  Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo         %%v found.

:: ── Step 2: Virtual environment ──────────────────────────────────────────────
echo [2/7] Setting up virtual environment ...
if not exist "%ROOT%venv\Scripts\activate.bat" (
    echo         Creating venv\ ...
    python -m venv venv
    if errorlevel 1 (
        echo  ERROR: Failed to create virtual environment.
        pause & exit /b 1
    )
    echo         venv created.
) else (
    echo         venv already exists.
)

call "%ROOT%venv\Scripts\activate.bat"
if errorlevel 1 (
    echo  ERROR: Could not activate virtual environment.
    pause & exit /b 1
)

:: ── Step 3: Install / update dependencies ────────────────────────────────────
echo [3/7] Installing / verifying dependencies ...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  ERROR: pip install failed.  Check your internet connection or
    echo  review the error above, then re-run this script.
    pause & exit /b 1
)
echo         All packages OK.

:: ── Step 4: Bootstrap .env ───────────────────────────────────────────────────
echo [4/7] Checking environment configuration ...
if not exist "%ROOT%.env" (
    echo.
    echo  ┌─────────────────────────────────────────────────────────────┐
    echo  │  FIRST-RUN SETUP                                            │
    echo  │  .env file not found — creating from .env.example          │
    echo  └─────────────────────────────────────────────────────────────┘
    copy /Y "%ROOT%.env.example" "%ROOT%.env" >nul
    echo.
    echo  IMPORTANT: You must now edit .env before VAAS can start.
    echo.
    echo  Minimum required changes:
    echo    1. VAAS_SECRET_KEY  — generate with:
    echo         python -c "import secrets; print(secrets.token_hex(32^)^)"
    echo       Then paste the result after VAAS_SECRET_KEY= in .env
    echo.
    echo    2. VAAS_ARDUINO_PORT — set to your Arduino COM port (e.g. COM4^)
    echo.
    echo    3. VAAS_CAM_A / VAAS_CAM_B — set your webcam indices
    echo       Run this to discover them:
    echo         python -c "import cv2; [print(i,cv2.VideoCapture(i).isOpened()) for i in range(4)]"
    echo.
    echo  Opening .env in Notepad now.  Save and close Notepad, then
    echo  re-run this script to start VAAS.
    echo.
    notepad "%ROOT%.env"
    echo  Re-run start_production.bat after saving your changes.
    pause & exit /b 0
)

:: Check that VAAS_SECRET_KEY has been changed from the placeholder
findstr /C:"CHANGE_ME" "%ROOT%.env" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  ERROR: VAAS_SECRET_KEY is still set to the placeholder value.
    echo  Edit .env and replace the VAAS_SECRET_KEY line with a real secret.
    echo.
    echo  Generate one now by running:
    echo    python -c "import secrets; print(secrets.token_hex(32^)^)"
    echo.
    notepad "%ROOT%.env"
    pause & exit /b 1
)
echo         .env loaded and VAAS_SECRET_KEY is set.

:: ── Step 5: Seed database on first run ───────────────────────────────────────
echo [5/7] Checking database ...
if not exist "%ROOT%data\vaas.db" (
    echo         No database found — running first-time seed ...
    echo.
    echo  You will be prompted to set the admin password.
    echo  The manager and operator passwords are auto-generated and shown once.
    echo  Copy them somewhere safe before continuing.
    echo.
    python scripts\seed_db.py
    if errorlevel 1 (
        echo  ERROR: Database seed failed.
        pause & exit /b 1
    )
    echo.
    echo  ─────────────────────────────────────────────────────────────────
) else (
    echo         vaas.db found — skipping seed.
)

:: ── Step 6: Arduino auto-discovery ───────────────────────────────────────────
echo [6/7] Detecting Arduino COM port ...
python scripts\find_arduino.py --quiet
if errorlevel 1 (
    echo.
    echo  WARNING: No Arduino was detected on any COM port.
    echo  VAAS will start in software-only mode ^(barrier commands will be
    echo  logged but the servo will not move^).
    echo.
    echo  To fix: plug in the Arduino, then re-run this script.
    echo  If the board IS connected, check Device Manager ^> Ports ^(COM ^& LPT^)
    echo  and set VAAS_ARDUINO_PORT manually in .env.
    echo.
    echo  Continuing in 5 seconds ...
    timeout /t 5 /nobreak >nul
) else (
    :: Read the updated port back out of .env for the startup banner
    for /f "tokens=2 delims==" %%p in ('findstr /B "VAAS_ARDUINO_PORT" "%ROOT%.env"') do (
        set "DETECTED_PORT=%%p"
    )
    echo         Arduino detected on !DETECTED_PORT! — .env updated.
)

:: ── Step 7: Validate config then start Waitress ───────────────────────────────
echo [7/7] Starting VAAS server ...
python serve.py --check-env
if errorlevel 1 (
    echo.
    echo  Configuration errors detected (see above^).
    echo  Edit .env to fix them, then re-run this script.
    pause & exit /b 1
)

echo.
echo  ─────────────────────────────────────────────────────────────────
echo   VAAS is starting.  Open your browser to:
echo     http://localhost:5000
echo.
echo   Press Ctrl+C to stop the server gracefully.
echo  ─────────────────────────────────────────────────────────────────
echo.

python serve.py

:: If serve.py exits for any reason, pause so the window doesn't disappear
if errorlevel 1 (
    echo.
    echo  VAAS exited with an error.  Review the output above.
    pause
)
endlocal
