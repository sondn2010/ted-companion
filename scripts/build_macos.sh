#!/usr/bin/env bash
set -euo pipefail

echo "====================================================================="
echo "ĐÓNG GÓI ỨNG DỤNG TED THÀNH FILE .APP & .DMG TRÊN MACOS"
echo "====================================================================="
echo "📦 Bộ cài KHÔNG kèm model giọng nói (TTS/STT): người dùng tự chọn & tải trong Cài đặt của app."
echo "💡 STT offline trên macOS cần: brew install whisper-cpp (app tự dò lệnh whisper-cli)."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

APP_NAME="TedCompanion"

# Kiểm tra pack TRƯỚC khi xoá build/dist cũ
# Character Pack: build_macos.sh --pack <tên pack trong docs/UI/characters> [--yes]  (--pack none = 6 con vật mặc định)
if ! python3 scripts/install_character_pack.py "$@"; then
    echo "⛔ Không build: character pack không hợp lệ hoặc đã chọn dừng."
    exit 1
fi

rm -rf build dist
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 -m PyInstaller --clean --noconfirm TedCompanion.spec

echo "✅ Đã tạo thành công gói ứng dụng: dist/${APP_NAME}.app"

if command -v hdiutil >/dev/null 2>&1; then
    echo "📦 Đang tạo thêm bộ cài đặt dist/${APP_NAME}-Installer.dmg..."
    hdiutil create -volname "Ted Companion" -srcfolder "dist/${APP_NAME}.app" -ov -format UDZO "dist/${APP_NAME}-Installer.dmg"
    echo "✅ Đã tạo bộ cài: dist/${APP_NAME}-Installer.dmg"
fi
