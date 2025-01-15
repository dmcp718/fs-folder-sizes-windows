@echo off
echo Cleaning previous builds...
rmdir /s /q build dist
echo.

echo Building executable...
pyinstaller --clean ^
    --onefile ^
    --name folder-sizes ^
    --console ^
    folder_sizes.py

echo.
echo Build complete. Executable is in dist\folder-sizes.exe
