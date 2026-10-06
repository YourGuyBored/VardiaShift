@echo off
REM =====================================================================
REM  Shiftora - Windows first-time setup (run from source)
REM
REM  Double-click this file. It creates a virtual environment, installs
REM  everything Shiftora needs (including the Windows time-zone database
REM  that prevents the "No time zone found with key UTC" crash), and puts
REM  a Shiftora shortcut on your desktop.
REM
REM  Requirements: Python 3.10+ from https://www.python.org/downloads/
REM  (tick "Add python.exe to PATH" during its install).
REM =====================================================================
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo [2/4] Installing dependencies (this takes a few minutes once)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Installing packages failed. Check your internet connection
    echo and run this file again.
    pause
    exit /b 1
)

echo [3/4] Checking the installation...
python -c "import PySide6, qrcode, openpyxl, zoneinfo; zoneinfo.ZoneInfo('Asia/Manila'); print('All packages OK, time zones OK.')"
if errorlevel 1 (
    echo [ERROR] The check failed. Please report the messages above.
    pause
    exit /b 1
)

echo [4/4] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'Shiftora.lnk')); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0run.py\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\icon.ico'; $s.Save()"
if errorlevel 1 (
    echo [NOTE] Could not create the desktop shortcut, but Shiftora itself
    echo is ready. Start it with: .venv\Scripts\python.exe run.py
) else (
    echo Desktop shortcut created.
)

echo.
echo =====================================================================
echo  SETUP COMPLETE. Double-click the Shiftora desktop shortcut to start.
echo  On first launch, create your administrator account when asked.
echo =====================================================================
pause
