@echo off
setlocal enabledelayedexpansion
title Eval-DAG Startup
cd /d "%~dp0"

echo ============================================================
echo  Eval-DAG Startup Script
echo ============================================================
echo.

:: ── 1. Check .env and OPENAI_API_KEY ─────────────────────────────────────────
echo [1/5] Checking .env file...
if not exist ".env" (
    echo.
    echo  ERROR: .env file not found at project root.
    echo  Create it with:  OPENAI_API_KEY=sk-proj-...
    echo.
    pause & exit /b 1
)
set "API_KEY="
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="OPENAI_API_KEY" set "API_KEY=%%B"
)
if "%API_KEY%"=="" (
    echo.
    echo  ERROR: OPENAI_API_KEY is not set in .env
    echo  Open .env and add:  OPENAI_API_KEY=sk-proj-...
    echo.
    pause & exit /b 1
)
echo  OK - OPENAI_API_KEY found ^(starts with: %API_KEY:~0,12%...^)

:: ── 2. Check Python ───────────────────────────────────────────────────────────
echo.
echo [2/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: python not found. Install Python 3.11+ and add to PATH.
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  OK - Python %PYVER%

:: ── 3. Check Node / npm ───────────────────────────────────────────────────────
echo.
echo [3/5] Checking Node.js / npm...

:: Use "where" to locate npm.cmd — works reliably on Windows without output capture issues
where npm >nul 2>&1
if errorlevel 1 (
    echo  ERROR: npm not found. Install Node.js ^(https://nodejs.org^) and add to PATH.
    pause & exit /b 1
)

:: Use node.exe (plain binary, not a .cmd) to get the version safely
for /f "tokens=1" %%V in ('node --version 2^>^&1') do set NODEVER=%%V
echo  OK - Node.js %NODEVER% ^(npm ready^)

:: ── 4. Install dependencies if needed ────────────────────────────────────────
echo.
echo [4/5] Checking dependencies...

python -c "import eval_dag" >nul 2>&1
if errorlevel 1 (
    echo  Python package not installed - running pip install -e . ...
    python -m pip install -e . --quiet
    if errorlevel 1 (
        echo  ERROR: pip install failed. Check pyproject.toml or try manually.
        pause & exit /b 1
    )
    echo  OK - Python package installed.
) else (
    echo  OK - Python package already installed.
)

if not exist "frontend\node_modules" (
    echo  node_modules missing - running npm install ^(may take a minute^)...
    cd frontend
    call npm install --silent
    if errorlevel 1 (
        echo  ERROR: npm install failed.
        pause & exit /b 1
    )
    cd ..
    echo  OK - npm packages installed.
) else (
    echo  OK - node_modules present.
)

:: ── 5. Kill any stale processes on ports 8000 and 5173 ───────────────────────
echo.
echo [5/5] Freeing ports 8000 and 5173...

:: Kill all python.exe processes first — uvicorn's reloader spawns child
:: processes that survive port-based kills and keep holding the port.
powershell -NonInteractive -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1

:: Also kill any node processes on 5173
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":5173 "') do (
    if not "%%P"=="0" taskkill /PID %%P /F >nul 2>&1
)

:: Brief pause so the OS reclaims ports before we try to bind them
timeout /t 2 /nobreak >nul
echo  OK - Ports cleared.

:: ── Launch servers ────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Starting servers...
echo  Backend  -^> http://localhost:8000
echo  Frontend -^> http://localhost:5173
echo ============================================================
echo.

start "Eval-DAG Backend" cmd /k "cd /d "%~dp0api" && echo. && echo  [Backend] FastAPI starting on http://localhost:8000 && echo. && uvicorn main:app --reload --port 8000"
timeout /t 2 /nobreak >nul

start "Eval-DAG Frontend" cmd /k "cd /d "%~dp0frontend" && echo. && echo  [Frontend] Vite dev server starting on http://localhost:5173 && echo. && npm run dev"
timeout /t 4 /nobreak >nul

:: Open browser
start "" "http://localhost:5173"

echo  Both servers are starting in their own windows.
echo  Browser opening at http://localhost:5173
echo.
echo  To stop: close the "Eval-DAG Backend" and "Eval-DAG Frontend" windows.
echo.
pause
