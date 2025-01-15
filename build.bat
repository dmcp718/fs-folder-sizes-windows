@echo off
echo Cleaning previous builds...
rmdir /s /q build dist
del /f /q folder-sizes.spec
echo.

echo Building executable...
pyinstaller --clean ^
    --onefile ^
    --name folder-sizes ^
    --console ^
    --noconfirm ^
    folder_sizes.py

echo.
echo Build complete. Executable is in dist\folder-sizes.exe
