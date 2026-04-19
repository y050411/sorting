@echo off
REM ═══════════════════════════════════════════════════════════
REM   Build Installer for מנהל שירים חכם (Smart Songs Manager)
REM ═══════════════════════════════════════════════════════════
REM
REM   Prerequisites:
REM     1. Python 3.10+ installed and in PATH
REM     2. Run: pip install -r requirements.txt
REM     3. Run: pip install pyinstaller
REM
REM   Usage:
REM     Double-click this file or run from command prompt
REM
REM ═══════════════════════════════════════════════════════════

echo.
echo ══════════════════════════════════════════════════
echo   Building Smart Songs Manager Installer...
echo ══════════════════════════════════════════════════
echo.

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

REM Install PyInstaller
echo [2/3] Installing PyInstaller...
pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    pause
    exit /b 1
)

REM Build the installer
echo [3/3] Building installer...
python build_installer.py
if errorlevel 1 (
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo.
echo ══════════════════════════════════════════════════
echo   Build complete! Check the dist/ folder.
echo ══════════════════════════════════════════════════
echo.
pause
