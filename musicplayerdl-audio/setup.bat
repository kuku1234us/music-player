@echo off
echo MusicPlayerDL Chrome Extension Setup
echo ===================================
echo.

REM This setup registers the musicplayerdl:// protocol handler for the CURRENT USER (HKCU),
REM so it does NOT require administrator privileges.

REM Allow passing the exe path as the first argument. Otherwise default to ..\dist\MusicPlayer.exe
set EXE_PATH=%~1
if "%EXE_PATH%"=="" (
    set EXE_PATH=%~dp0..\dist\MusicPlayer.exe
)

if not exist "%EXE_PATH%" (
    echo Error: MusicPlayer.exe not found at:
    echo   %EXE_PATH%
    echo.
    echo Fix:
    echo - Build the app to create dist\MusicPlayer.exe, OR
    echo - Re-run this script with the full path to MusicPlayer.exe as the first argument.
    echo.
    pause
    exit /b 1
)

echo Registering protocol handler (musicplayerdl://) for current user...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\register_protocol.ps1" -ExecutablePath "%EXE_PATH%"
if %errorLevel% neq 0 (
    echo Error: Failed to register the protocol handler.
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
echo 3. Click "Load unpacked" and select the musicplayerdl-audio folder
echo.
pause

