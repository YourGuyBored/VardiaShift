@echo off
REM =====================================================================
REM  Shiftora - Windows build script
REM
REM  Builds a distributable folder:  dist\Shiftora\Shiftora.exe
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

echo [3/4] Building Shiftora.exe with PyInstaller...
pyinstaller --noconfirm Shiftora.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. See the output above.
    pause
    exit /b 1
)

echo [4/4] Packaging release zip...
if exist "dist\Shiftora-Windows-x64.zip" del "dist\Shiftora-Windows-x64.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Shiftora' -DestinationPath 'dist\Shiftora-Windows-x64.zip'"

echo.
echo =====================================================================
echo  BUILD COMPLETE
echo.
echo  Executable folder : dist\Shiftora\Shiftora.exe
echo  Release zip       : dist\Shiftora-Windows-x64.zip
echo.
echo  Share the zip file. Users extract it and run Shiftora.exe -
echo  no Python installation required.
echo =====================================================================
pause
