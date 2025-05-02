@echo off
echo YouTubeMaster Chrome Extension Setup
echo ===================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: This script must be run as administrator.
    echo Please right-click on this file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

REM Check if YouTubeMaster.exe exists
set EXE_PATH=D:\projects\youtube-master\dist\YouTubeMaster.exe
if not exist "%EXE_PATH%" (
    echo Error: YouTubeMaster.exe not found at %EXE_PATH%
    echo Please build the application first or update the path in this script.
    echo.
    pause
    exit /b 1
)

echo Installing protocol handler...
regedit /s "%~dp0register_protocol.reg"
if %errorLevel% neq 0 (
    echo Error: Failed to import registry entries.
    echo.
    pause
    exit /b 1
)

echo.
echo Setup completed successfully!
echo.
echo Chrome Extension Installation Instructions:
echo 1. Open Chrome and go to chrome://extensions/
echo 2. Enable "Developer mode" (toggle in the top-right)
echo 3. Click "Load unpacked" and select the youtube-master-extension folder
echo 4. Right-click on YouTube videos to access "Video YouTubeMaster" and "Audio YouTubeMaster" options
echo.
pause 