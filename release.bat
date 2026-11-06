@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo =======================================================
echo        TED COMPANION - QUY TRINH DONG GOI ^& RELEASE
echo =======================================================
echo.

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

if "%~1"=="" (
    set /p "INPUT_VER=Nhap version can release (Enter de dung mac dinh): "
)

if not "%INPUT_VER%"=="" (
    "%PYTHON_CMD%" scripts\publish_release.py %INPUT_VER%
) else (
    "%PYTHON_CMD%" scripts\publish_release.py %*
)

if errorlevel 1 (
    echo.
    echo [LOI] Qua trinh release gap loi!
    echo.
    pause
    exit /b 1
)

echo.
echo [HOAN TAT] Qua trinh dong goi va publish da ket thuc!
echo.
pause
