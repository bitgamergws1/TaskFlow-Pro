@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM Enable ANSI colors on Windows 10+
for /f %%a in ('echo prompt $E^| cmd /q') do set "ESC=%%a"
set "GREEN=%ESC%[32m"
set "CYAN=%ESC%[36m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "DIM=%ESC%[2m"
set "BOLD=%ESC%[1m"
set "NC=%ESC%[0m"

REM Carriage return for overwriting the tip line in-place
for /f %%a in ('copy /Z "%~f0" nul') do set "CR=%%a"

REM Spinner characters
set "SP[0]=/"
set "SP[1]=-"
set "SP[2]=^\"
set "SP[3]=|"

REM Tips shown while install runs
set "T[0]=Break big tasks into 25-min Pomodoro blocks."
set "T[1]=High priority first — your brain is freshest in the morning."
set "T[2]=Name tasks as actions: 'Write report' beats 'Report'."
set "T[3]=A 3-day streak beats a perfect week you never started."
set "T[4]=Less than 2 minutes? Do it now — don't add it to the list."
set "T[5]=Set due dates even for flexible tasks — deadlines create focus."
set "T[6]=Group similar tasks — context-switching kills momentum."
set "T[7]=Complete your hardest task before lunch. Rest feels easy after."
set "T[8]=Pending tasks drain energy even when you're not working on them."
set "T[9]=What gets measured gets done — check analytics weekly."
set "T[10]=Timeboxing beats to-do lists. Schedule the task, not the intent."
set "T[11]=Done is better than perfect. Ship, then refine."
set "T[12]=One task at a time. Multitasking is just expensive task-switching."
set "T[13]=Your future self will thank you for the due date you set today."
set "T[14]=Productivity is not about doing more — it's about what matters."
set "TIP_COUNT=15"

set "DONE_FILE=%TEMP%\taskflow_install.done"
set "EC_FILE=%TEMP%\taskflow_install.ec"
set "LOG_FILE=%TEMP%\taskflow_install.log"

REM ── Banner ─────────────────────────────────────────────────────────────────
echo.
echo %CYAN%%BOLD%
echo   +==========================================+
echo   ^|   TaskFlow Pro -- DevNest Setup (Win)   ^|
echo   +==========================================+
echo %NC%
echo.

REM ── Python check ───────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Python not found.
    echo         Install from https://python.org
    echo         Check "Add Python to PATH" during install.
    pause & exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_FULL=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PY_FULL%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)

if %PY_MAJOR% LSS 3 (
    echo %RED%[ERROR]%NC% Python 3.9+ required. Found %PY_FULL%.
    pause & exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 9 (
    echo %RED%[ERROR]%NC% Python 3.9+ required. Found %PY_FULL%.
    pause & exit /b 1
)

echo %GREEN%[OK]%NC%    Python %PY_FULL%

REM ── Virtual environment ────────────────────────────────────────────────────
if not exist "venv" (
    echo %DIM%       Creating virtual environment...%NC%
    python -m venv venv
    if errorlevel 1 (
        echo %RED%[ERROR]%NC% Failed to create virtual environment.
        pause & exit /b 1
    )
    echo %GREEN%[OK]%NC%    Virtual environment created
) else (
    echo %GREEN%[OK]%NC%    Virtual environment exists
)

call venv\Scripts\activate.bat

echo.
echo %DIM%  Tips will show while we get things ready...%NC%
echo.

REM ── Upgrade pip ────────────────────────────────────────────────────────────
if exist "%DONE_FILE%" del "%DONE_FILE%" >nul 2>&1
if exist "%EC_FILE%"   del "%EC_FILE%"   >nul 2>&1
start /b cmd /c "venv\Scripts\python.exe -m pip install --upgrade pip --quiet > "%LOG_FILE%" 2>&1 & echo %%ERRORLEVEL%% > "%EC_FILE%" & echo 1 > "%DONE_FILE%""
set "STEP_LABEL=Upgrading pip   "
call :tips_wait
set /p _EC=<"%EC_FILE%"
if "!_EC!" NEQ "0" (
    echo %RED%[ERROR]%NC% pip upgrade failed. See %LOG_FILE%
    pause & exit /b 1
)
echo %GREEN%[OK]%NC%    pip up to date

REM ── Install dependencies ───────────────────────────────────────────────────
if exist "requirements.txt" (
    if exist "%DONE_FILE%" del "%DONE_FILE%" >nul 2>&1
    if exist "%EC_FILE%"   del "%EC_FILE%"   >nul 2>&1
    start /b cmd /c "venv\Scripts\python.exe -m pip install --quiet -r requirements.txt > "%LOG_FILE%" 2>&1 & echo %%ERRORLEVEL%% > "%EC_FILE%" & echo 1 > "%DONE_FILE%""
    set "STEP_LABEL=Installing deps "
    call :tips_wait
    set /p _EC=<"%EC_FILE%"
    if "!_EC!" NEQ "0" (
        echo %RED%[ERROR]%NC% Dependency install failed. See %LOG_FILE%
        pause & exit /b 1
    )
    echo %GREEN%[OK]%NC%    Dependencies ready
) else (
    echo %YELLOW%[WARN]%NC%  requirements.txt not found — skipping
)

REM ── tzdata check ───────────────────────────────────────────────────────────
venv\Scripts\python.exe -c "from zoneinfo import ZoneInfo; ZoneInfo('UTC')" >nul 2>&1
if errorlevel 1 (
    if exist "%DONE_FILE%" del "%DONE_FILE%" >nul 2>&1
    if exist "%EC_FILE%"   del "%EC_FILE%"   >nul 2>&1
    start /b cmd /c "venv\Scripts\python.exe -m pip install --quiet tzdata > "%LOG_FILE%" 2>&1 & echo %%ERRORLEVEL%% > "%EC_FILE%" & echo 1 > "%DONE_FILE%""
    set "STEP_LABEL=Installing tz   "
    call :tips_wait
    set /p _EC=<"%EC_FILE%"
    if "!_EC!" NEQ "0" (
        echo %RED%[ERROR]%NC% tzdata install failed. See %LOG_FILE%
        pause & exit /b 1
    )
    echo %GREEN%[OK]%NC%    tzdata installed
) else (
    echo %GREEN%[OK]%NC%    Timezone data
)

REM ── Launch ─────────────────────────────────────────────────────────────────
echo.
echo %GREEN%%BOLD%  All set. Launching TaskFlow Pro...%NC%
echo.

python main.py %*
goto :eof


REM ── Tips spinner subroutine ────────────────────────────────────────────────
REM Waits until %DONE_FILE% appears, spinning tips in the meantime.
:tips_wait
set /a _spin=0
set /a _tip=0
set /a _tick=0

:_spin_loop
if exist "%DONE_FILE%" (
    del "%DONE_FILE%" >nul 2>&1
    REM Clear the tip line
    <nul set /p "=!CR!                                                                                "
    echo.
    goto :eof
)

set /a _sidx=_spin %% 4
set /a _tidx=_tip %% TIP_COUNT
call set "_sc=%%SP[!_sidx!]%%"
call set "_tc=%%T[!_tidx!]%%"

REM Truncate tip to 55 chars so it never wraps to next line
set "_tc_short=!_tc:~0,55!"
<nul set /p "=!CR!  %CYAN%[!_sc!]%NC%  %DIM%!STEP_LABEL!%NC%  !_tc_short!          "

timeout /t 1 /nobreak >nul

set /a _spin+=1
set /a _tick+=1
if !_tick! GEQ 3 (
    set /a _tip+=1
    set /a _tick=0
)
goto _spin_loop
