@echo off
echo =====================================================================
echo DONG GOI UNG DUNG TED THANH FILE .EXE TREN WINDOWS
echo =====================================================================
echo Bo cai KHONG kem model giong noi (TTS/STT). Nguoi dung tu chon va tai
echo giong doc / mo hinh nhan giong noi ngay trong Cai dat cua app.
cd /d "%~dp0.."

rem Character Pack: build_windows.bat --pack ^<ten pack trong docs\UI\characters^> [--yes]  (--pack none = 6 con vat mac dinh)
rem Kiem tra pack TRUOC khi xoa build/dist cu
python scripts\install_character_pack.py %*
if errorlevel 1 (
    echo [DUNG] Khong build: character pack khong hop le hoac da chon dung.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m PyInstaller --clean --noconfirm TedCompanion.spec

echo.
echo [HOAN TAT] File chay .exe da duoc tao tai: dist\TedCompanion.exe
pause
