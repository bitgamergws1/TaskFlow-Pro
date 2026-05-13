@echo off
chcp 65001 >nul 2>&1
REM run.bat — TaskFlow Pro setup & launch (Windows)

echo.
echo  +==========================================+
echo  ^|   TaskFlow Pro -- DevNest Setup (Win)   ^|
echo  +==========================================+
echo.

REM ── Python check ──────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    echo Tip: check "Add Python to PATH" during install.
    pause & exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_FULL=%%v
for /f "tokens=1,2 delims=." %%a in ("%PY_FULL%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo [ERROR] Python 3.9+ required. You have %PY_FULL%.
    pause & exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 9 (
    echo [ERROR] Python 3.9+ required. You have %PY_FULL%.
    pause & exit /b 1
)
echo [OK] Python %PY_FULL% found

REM ── Virtual environment ────────────────────────────────────────────────────
if not exist "venv" (
    echo [..] Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

REM ── Install dependencies ───────────────────────────────────────────────────
echo [..] Installing dependencies...
venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
echo [OK] Dependencies ready

REM ── tzdata check (Windows has no built-in IANA tz data — always needed) ────
echo [..] Checking timezone data...
venv\Scripts\python.exe -c "from zoneinfo import ZoneInfo; ZoneInfo('UTC')" >nul 2>&1
if errorlevel 1 (
    echo [!!] tzdata missing -- installing...
    venv\Scripts\python.exe -m pip install --quiet tzdata
    echo [OK] tzdata installed
) else (
    echo [OK] Timezone data OK
)

echo.
echo [>>] Launching TaskFlow Pro...
echo.
python main.py %*
