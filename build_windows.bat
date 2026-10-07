@echo off
REM =====================================================================
REM  VardiaShift - Windows build script
REM
REM  Builds a distributable folder:  dist\VardiaShift\VardiaShift.exe
REM
REM  Requirements: Python 3.10+ on PATH.
REM  Run this file by double-clicking it or from a terminal:
REM      build_windows.bat
REM =====================================================================
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/ and retry.
    pause
    exit /b 1
)

echo [1/4] Creating build environment...
if not exist .build-venv (
    python -m venv .build-venv
)
call .build-venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo [3/4] Building VardiaShift.exe with PyInstaller...
pyinstaller --noconfirm VardiaShift.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. See the output above.
    pause
    exit /b 1
)

echo [4/4] Packaging release zip...
if exist "dist\VardiaShift-Windows-x64.zip" del "dist\VardiaShift-Windows-x64.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\VardiaShift' -DestinationPath 'dist\VardiaShift-Windows-x64.zip'"

echo.
echo =====================================================================
echo  BUILD COMPLETE
echo.
echo  Executable folder : dist\VardiaShift\VardiaShift.exe
echo  Release zip       : dist\VardiaShift-Windows-x64.zip
echo.
echo  Share the zip file. Users extract it and run VardiaShift.exe -
echo  no Python installation required.
echo =====================================================================
pause
