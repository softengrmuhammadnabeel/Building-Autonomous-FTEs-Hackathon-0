@echo off
REM ── Odoo Docker Management Script ──────────────────────────────────
REM Gold Tier AI Employee - Windows Batch Script
REM
REM Usage: odoo-start.bat [start^|stop^|restart^|logs^|status^|clean]
REM ─────────────────────────────────────────────────────────────────────

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if "%1"=="" goto start
if /i "%1"=="start"    goto start
if /i "%1"=="stop"     goto stop
if /i "%1"=="restart"  goto restart
if /i "%1"=="logs"     goto logs
if /i "%1"=="status"   goto status
if /i "%1"=="clean"    goto clean
if /i "%1"=="health"   goto health

:start
echo.
echo ========================================
echo   Starting Odoo (Community Edition)
echo ========================================
echo.
echo   Web UI:  http://localhost:8069
echo   DB:      localhost:5432 (odoo/odoo)
echo   Admin:   admin / admin
echo.
docker compose up -d
echo.
echo Waiting for Odoo to initialize (~60 seconds)...
echo.
:wait_loop
timeout /t 5 /nobreak >nul
docker compose ps --format json 2>nul | findstr "healthy" >nul
if %errorlevel%==0 (
    echo   Odoo is READY!
    echo   Open: http://localhost:8069
    goto health
)
echo   Still starting...
goto wait_loop

:stop
echo.
echo ========================================
echo   Stopping Odoo Services
echo ========================================
echo.
docker compose down
echo.
echo Done.
goto :eof

:restart
call :stop
call :start
goto :eof

:logs
echo.
echo ========================================
echo   Odoo Logs (Ctrl+C to exit)
echo ========================================
echo.
docker compose logs -f
goto :eof

:status
echo.
echo ========================================
echo   Odoo Service Status
echo ========================================
echo.
docker compose ps
goto :eof

:clean
echo.
echo ========================================
echo   CLEANING — This will DELETE all data!
echo ========================================
echo.
set /p confirm="Are you sure? Type YES to confirm: "
if /i not "%confirm%"=="YES" (
    echo Cancelled.
    goto :eof
)
echo.
docker compose down -v
echo.
echo All Odoo data and containers removed.
goto :eof

:health
echo.
echo ========================================
echo   Odoo Health Check
echo ========================================
echo.
docker compose run --rm odoo-healthcheck
goto :eof
