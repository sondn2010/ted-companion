Set-Location $PSScriptRoot
# Tham so tuy chon: --pack <ten pack trong docs\UI\characters | duong dan | none> [--yes]
& ".\.venv\Scripts\python.exe" "scripts\install_character_pack.py" @args
if ($LASTEXITCODE -ne 0) { exit 1 }
& ".\.venv\Scripts\python.exe" "src\main.py"
