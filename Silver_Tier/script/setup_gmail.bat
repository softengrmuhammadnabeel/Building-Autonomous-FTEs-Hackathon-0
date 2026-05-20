@echo off
REM Gmail Watcher Setup Script for Windows
REM This script installs dependencies and guides you through OAuth setup

echo ======================================
echo Gmail Watcher Setup
echo ======================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.13+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Installing Python dependencies...
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo Dependencies installed successfully!
echo.

echo [2/4] Checking credentials.json...
echo Script directory: %~dp0
echo Parent directory: %~dp0..
echo.

REM Check multiple possible locations for credentials
set CREDENTIALS_PATH=
set FOUND=0

REM Location 1: Parent directory\gmail_credentials\credentials.json
if exist "%~dp0..\gmail_credentials\credentials.json" (
    set CREDENTIALS_PATH=%~dp0..\gmail_credentials\credentials.json
    set FOUND=1
    echo Found: %~dp0..\gmail_credentials\credentials.json
)

REM Location 2: Parent directory\credentials.json
if exist "%~dp0..\credentials.json" (
    set CREDENTIALS_PATH=%~dp0..\credentials.json
    set FOUND=1
    echo Found: %~dp0..\credentials.json
)

REM Location 3: Parent directory\gmail_credentials\client_secret.json
if exist "%~dp0..\gmail_credentials\client_secret.json" (
    set CREDENTIALS_PATH=%~dp0..\gmail_credentials\client_secret.json
    set FOUND=1
    echo Found: %~dp0..\gmail_credentials\client_secret.json
)

REM Location 4: Script directory\gmail_credentials\credentials.json
if exist "%~dp0gmail_credentials\credentials.json" (
    set CREDENTIALS_PATH=%~dp0gmail_credentials\credentials.json
    set FOUND=1
    echo Found: %~dp0gmail_credentials\credentials.json
)

REM Location 5: Script directory\credentials.json
if exist "%~dp0credentials.json" (
    set CREDENTIALS_PATH=%~dp0credentials.json
    set FOUND=1
    echo Found: %~dp0credentials.json
)

if %FOUND%==0 (
    echo.
    echo ERROR: No credentials file found!
    echo.
    echo Searched locations:
    echo   1. %~dp0..\gmail_credentials\credentials.json
    echo   2. %~dp0..\credentials.json
    echo   3. %~dp0..\gmail_credentials\client_secret.json
    echo   4. %~dp0gmail_credentials\credentials.json
    echo   5. %~dp0credentials.json
    echo.
    echo Please:
    echo   1. Download credentials.json from Google Cloud Console
    echo   2. Rename it to 'credentials.json' if it has a different name
    echo   3. Place it in: %~dp0..\gmail_credentials\credentials.json
    echo.
    
    REM Check if parent gmail_credentials folder exists
    if exist "%~dp0..\gmail_credentials" (
        echo Parent gmail_credentials folder exists. Contents:
        dir "%~dp0..\gmail_credentials"
    ) else (
        echo Parent gmail_credentials folder does NOT exist at: %~dp0..\gmail_credentials
        echo.
        echo Create this folder and place credentials.json inside it.
    )
    
    pause
    exit /b 1
)

echo.
echo Using credentials: %CREDENTIALS_PATH%
echo.

echo [3/4] First-time OAuth Authorization
echo ======================================
echo The script will now open your browser to authorize the app with Gmail.
echo.
echo Steps:
echo 1. Select your Google account
echo 2. Click "Allow" to grant read-only access
echo 3. Copy the authorization code if prompted
echo.
echo Note: Token will be saved in the same folder as credentials.json
echo.
pause

REM Run the Gmail watcher in auth-only mode
echo [4/4] Starting OAuth flow...
python "%~dp0gmail_watcher.py" --vault "%~dp0..\AI_Employee_Vault" --credentials "%CREDENTIALS_PATH%" --once

if errorlevel 1 (
    echo.
    echo ERROR: OAuth flow failed.
    echo Please check your credentials.json file and try again.
    pause
    exit /b 1
)

echo.
echo ======================================
echo Setup Complete!
echo ======================================
echo.
echo To run the Gmail Watcher:
echo   python gmail_watcher.py --vault "S:\Personal AI Employee\Autonomous FTEs\AI_Employee_Vault" --credentials "%CREDENTIALS_PATH%"
echo.
echo The watcher will:
echo   - Check for unread important emails every 2 minutes
echo   - Create action files in Needs_Action folder
echo   - Log all activity to Logs folder
echo.
pause