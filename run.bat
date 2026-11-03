@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
rem Tham so tuy chon: --pack ^<ten pack trong docs\UI\characters ^| duong dan ^| none^> [--yes]
python scripts\install_character_pack.py %*
if errorlevel 1 (
    pause
    exit /b 1
)
python src\main.py
