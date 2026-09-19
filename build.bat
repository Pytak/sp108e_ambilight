@echo off
setlocal
cd /d "%~dp0"

echo Installing build dependencies...
python -m pip install --quiet pyinstaller mss Pillow
if errorlevel 1 goto :fail

echo Building SP108E_Ambilight.exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name SP108E_Ambilight ^
    --icon icon.ico ^
    --add-data "icon.ico;." ^
    --hidden-import mss.windows ^
    sp108e_ambilight_gui.py
if errorlevel 1 goto :fail

echo.
echo Build complete: dist\SP108E_Ambilight.exe
exit /b 0

:fail
echo.
echo Build failed.
exit /b 1
