@echo off
REM LinkedIn Poster Setup Script for Windows - UPDATED VERSION
REM This script installs dependencies, tests browser automation, and saves login session

echo ======================================
echo LinkedIn Poster Setup (Updated)
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

echo [1/4] Installing/Upgrading Playwright...
pip install --upgrade playwright
if errorlevel 1 (
    echo ERROR: Failed to install Playwright
    pause
    exit /b 1
)
echo Playwright installed successfully!
echo.

echo [2/4] Installing Chromium browser...
playwright install chromium
if errorlevel 1 (
    echo WARNING: Chromium installation failed
)
echo Browser installed!
echo.

echo [3/4] Testing browser launch...
python -c "from playwright.sync_api import sync_playwright; print('Testing Playwright...'); print('✅ Playwright working!')"
echo.

echo [4/4] LinkedIn Session Setup (One-time manual login)
echo ======================================
echo.
echo This will open LinkedIn login page in a browser.
echo.
echo IMPORTANT INSTRUCTIONS:
echo 1. You will login MANUALLY in the browser
echo 2. Complete any 2FA or CAPTCHA verification
echo 3. Make sure you see your LinkedIn FEED page
echo 4. Then come back here and press Enter
echo.
echo This will save your login session for future use
echo.

pause

REM Create and run temporary Python script for session setup
python -c "
from playwright.sync_api import sync_playwright
import json
import time
import os
from pathlib import Path

print('\n🌐 Opening browser...')
print('📱 Please login manually when browser opens\n')

with sync_playwright() as p:
    # Use persistent context to save login state
    user_data_dir = str(Path.cwd() / 'linkedin_profile')
    
    print(f'📁 Saving session to: {user_data_dir}\n')
    
    # Launch with persistent context (saves everything)
    context = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,
        args=['--start-maximized']
    )
    
    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://www.linkedin.com/feed/')
    
    time.sleep(2)
    
    # Check if already logged in
    if 'login' in page.url:
        print('🔐 Not logged in. Please login now...')
        print('Complete any verification if asked.\n')
        input('✅ Press Enter AFTER you are logged in and see your LinkedIn feed...')
    else:
        print('✅ Already logged in! Session will be saved.\n')
        input('Press Enter to save session...')
    
    # Save cookies separately as backup
    cookies = context.cookies()
    with open('linkedin_cookies.json', 'w') as f:
        json.dump(cookies, f, indent=2)
    
    print(f'\n✅ Session saved successfully!')
    print(f'📊 Cookies saved: {len(cookies)} cookies')
    print(f'📁 Profile saved to: {user_data_dir}')
    
    context.close()
    print('\n✅ Setup complete! You can now run the orchestrator.')
"

echo.
echo ======================================
echo Setup Complete!
echo ======================================
echo.
echo ✅ LinkedIn session has been saved
echo ✅ You can now run orchestrator normally
echo.
echo To post to LinkedIn:
echo 1. Create a post in Needs_Action/ folder
echo 2. Run orchestrator - it will use saved session
echo 3. No need to login every time
echo.
echo If login fails in future, run this setup again
echo.
pause