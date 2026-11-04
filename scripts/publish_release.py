#!/usr/bin/env python3
"""
Script tự động đóng gói và tạo tệp phân phối Release cho Ted Companion:
1. Đọc phiên bản hoặc nhận từ tham số CLI.
2. (Tùy chọn) Chạy PyInstaller để build binary sạch vào thư mục dist/.
3. Tính mã băm SHA256 và dung lượng file thực thi.
4. Sinh file version.json và copy binary vào thư mục dist_release/.
5. (Mới) Tự động upload file cài đặt và version.json lên MinIO Storage.
6. In ra thông tin và đường dẫn tải công khai.
"""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Đảm bảo import được các module từ src/ khi chạy độc lập
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Load biến môi trường từ .env (hỗ trợ .env trong ted-companion hoặc thư mục gốc)
try:
    from dotenv import load_dotenv

    env_candidates = [
        ROOT_DIR / ".env",
        ROOT_DIR.parent / ".env",
    ]
    for env_path in env_candidates:
        if env_path.exists():
            load_dotenv(env_path, override=False)
except ImportError:
    pass

try:
    from src.core.version_config import APP_VERSION, DEFAULT_UPDATE_URL
except ImportError:
    APP_VERSION = "1.5.1"
    DEFAULT_UPDATE_URL = "https://file5.bkglobal.vn/techbkglobal/release/version.json"


class UploadProgress:
    """Theo dõi tiến độ tải tệp lên MinIO."""

    def __init__(self, filename: str):
        self.filename = filename
        self.total = 0
        self.current = 0

    def set_meta(self, object_name: str, total_length: int):
        self.total = total_length
        self.current = 0

    def update(self, length: int):
        self.current += length
        if self.total > 0:
            pct = (self.current / self.total) * 100
            cur_mb = self.current / (1024 * 1024)
            tot_mb = self.total / (1024 * 1024)
            print(f"\r   ⏳ Đang tải lên {self.filename}: {pct:5.1f}% [{cur_mb:.2f} / {tot_mb:.2f} MB]", end="", flush=True)
        else:
            cur_mb = self.current / (1024 * 1024)
            print(f"\r   ⏳ Đang tải lên {self.filename}: {cur_mb:.2f} MB", end="", flush=True)


def compute_sha256(file_path: Path) -> str:
    """Tính mã băm SHA256 dạng hex cho file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while chunk := fh.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def get_minio_config() -> dict | None:
    """Đọc và chuẩn hóa cấu hình kết nối MinIO từ biến môi trường."""
    endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
    access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
    secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
    bucket_name = os.getenv("MINIO_BUCKET_NAME", "techbkglobal").strip()
    prefix = os.getenv("MINIO_PREFIX", "release").strip().strip("/")
    public_url = os.getenv("MINIO_PUBLIC_URL", "").strip().rstrip("/")

    # Nếu không có access_key hoặc endpoint thì coi như chưa cấu hình
    if not endpoint or not access_key:
        return None

    # Tự động chuẩn hóa endpoint (loại bỏ http:// hoặc https://)
    secure_env = os.getenv("MINIO_SECURE", "").strip().lower()
    if endpoint.startswith("https://"):
        endpoint = endpoint[8:]
        secure = True
    elif endpoint.startswith("http://"):
        endpoint = endpoint[7:]
        secure = False
    elif secure_env in ("false", "0", "no"):
        secure = False
    else:
        # Mặc định bật HTTPS nếu không chỉ định rõ
        secure = True

    endpoint = endpoint.rstrip("/")

    # Tính URL tải công khai nếu chưa chỉ định MINIO_PUBLIC_URL
    if not public_url:
        protocol = "https" if secure else "http"
        if prefix:
            public_url = f"{protocol}://{endpoint}/{bucket_name}/{prefix}"
        else:
            public_url = f"{protocol}://{endpoint}/{bucket_name}"

    return {
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket": bucket_name,
        "prefix": prefix,
        "secure": secure,
        "public_url": public_url,
    }


def create_release_manifest(
    version: str,
    binary_path: Path,
    url_base: str,
    changelog: str = "",
    platform_key: str = "windows",
) -> dict:
    """Tạo cấu trúc dict chuẩn cho file version.json."""
    ext = binary_path.suffix or (".exe" if platform_key == "windows" else ".zip")
    release_filename = f"TedCompanion-{version}-{platform_key}{ext}"
    clean_url_base = url_base.rstrip("/")
    download_url = f"{clean_url_base}/{release_filename}"

    sha256_hash = compute_sha256(binary_path)
    file_size = binary_path.stat().st_size

    return {
        "version": version,
        "release_date": datetime.now().strftime("%Y-%m-%d"),
        "changelog": changelog or f"Bản cập nhật Ted Companion v{version}",
        "platforms": {
            platform_key: {
                "url": download_url,
                "sha256": sha256_hash,
                "size": file_size,
            }
        },
    }


def run_build(platform_key: str) -> Path:
    """Chạy lệnh đóng gói PyInstaller theo hệ điều hành."""
    spec_path = ROOT_DIR / "TedCompanion.spec"
    if not spec_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file spec: {spec_path}")

    print("🚀 Đang chạy PyInstaller để đóng gói ứng dụng...")
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_path)]
    subprocess.run(cmd, cwd=ROOT_DIR, check=True)

    if platform_key == "windows":
        binary = ROOT_DIR / "dist" / "TedCompanion.exe"
    else:
        binary = ROOT_DIR / "dist" / "TedCompanion.app"
    if not binary.exists():
        raise FileNotFoundError(f"Build xong nhưng không thấy file tại: {binary}")
    return binary


def upload_release_to_minio(
    binary_path: Path,
    version_file: Path,
    minio_cfg: dict,
) -> bool:
    """Tải file thực thi và manifest version.json lên máy chủ MinIO."""
    try:
        from minio import Minio
        from minio.error import S3Error
    except ImportError:
        print("\n❌ Lỗi: Thư viện 'minio' chưa được cài đặt.")
        print("👉 Vui lòng chạy lệnh sau để cài đặt: pip install minio")
        return False

    endpoint = minio_cfg["endpoint"]
    bucket = minio_cfg["bucket"]
    prefix = minio_cfg["prefix"]
    secure = minio_cfg["secure"]

    print("\n" + "-" * 70)
    print("📡 ĐANG KẾT NỐI VÀ TẢI LÊN MÁY CHỦ MINIO")
    print("-" * 70)
    print(f"• Máy chủ MinIO:    {endpoint} (HTTPS: {'Bật' if secure else 'Tắt'})")
    print(f"• Bucket:           {bucket}")
    print(f"• Prefix / Thư mục: {prefix or '(gốc)'}")

    try:
        client = Minio(
            endpoint=endpoint,
            access_key=minio_cfg["access_key"],
            secret_key=minio_cfg["secret_key"],
            secure=secure,
        )

        # Kiểm tra sự tồn tại của bucket
        if not client.bucket_exists(bucket):
            print(f"ℹ️  Bucket '{bucket}' chưa tồn tại trên MinIO. Đang tiến hành tạo bucket...")
            client.make_bucket(bucket)
            print(f"✅ Đã tạo thành công bucket '{bucket}'.")

        # Xác định key của các file trên S3/MinIO
        binary_obj_name = f"{prefix}/{binary_path.name}".lstrip("/") if prefix else binary_path.name
        version_obj_name = f"{prefix}/{version_file.name}".lstrip("/") if prefix else version_file.name

        # 1. Tải file binary lên MinIO
        print(f"\n1️⃣  Đang tải file cài đặt: {binary_path.name}")
        progress = UploadProgress(binary_path.name)
        client.fput_object(
            bucket_name=bucket,
            object_name=binary_obj_name,
            file_path=str(binary_path),
            content_type="application/octet-stream",
            progress=progress,
        )
        print(f"\n   ✅ Đã tải xong: {binary_obj_name}")

        # 2. Tải file version.json lên MinIO (Cache-Control: no-cache để app luôn nhận bản mới)
        print(f"2️⃣  Đang tải file manifest: {version_file.name}")
        client.fput_object(
            bucket_name=bucket,
            object_name=version_obj_name,
            file_path=str(version_file),
            content_type="application/json",
            metadata={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
        print(f"   ✅ Đã tải xong: {version_obj_name}")

        return True

    except S3Error as err:
        print(f"\n❌ Lỗi MinIO S3 API: {err}")
        return False
    except Exception as err:
        print(f"\n❌ Lỗi khi tải lên MinIO: {err}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Tạo bản Release và publish lên MinIO cho Ted Companion")
    parser.add_argument("pos_version", nargs="?", default=None, help=f"Số phiên bản phát hành (Mặc định: {APP_VERSION})")
    parser.add_argument("--version", "-v", default="", help=f"Số phiên bản phát hành (Mặc định: {APP_VERSION})")
    parser.add_argument(
        "--url-base",
        default="",
        help="Đường dẫn thư mục chứa file tải trên web/VPS (Mặc định: lấy từ MINIO_PUBLIC_URL hoặc DEFAULT_UPDATE_URL)",
    )
    parser.add_argument("--changelog", default="", help="Nội dung thay đổi / ghi chú bản phát hành")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Bỏ qua bước chạy PyInstaller, dùng file có sẵn trong dist/",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Bỏ qua bước tải file lên MinIO",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="Chỉ định đường dẫn file .env cần nạp",
    )
    parser.add_argument(
        "--platform",
        default="windows" if sys.platform == "win32" else "macos",
        choices=["windows", "macos"],
        help="Nền tảng đích",
    )

    args = parser.parse_args()

    # Nạp env file tùy chọn nếu có
    if args.env_file:
        custom_env = Path(args.env_file)
        if custom_env.exists():
            load_dotenv(custom_env, override=True)

    # Ưu tiên pos_version trước, sau đó tới --version, cuối cùng là APP_VERSION mặc định
    version = (args.pos_version or args.version or APP_VERSION).strip()
    platform_key = args.platform

    # Lấy cấu hình MinIO
    minio_cfg = get_minio_config()

    # Xác định url_base cho download link trong manifest
    if args.url_base:
        url_base = args.url_base.strip()
    elif minio_cfg and minio_cfg.get("public_url"):
        url_base = minio_cfg["public_url"]
    else:
        default_dir = DEFAULT_UPDATE_URL.rsplit("/", 1)[0]
        url_base = default_dir

    # 1. Chạy đóng gói hoặc kiểm tra binary đã có
    if not args.skip_build:
        binary_path = run_build(platform_key)
    else:
        if platform_key == "windows":
            binary_path = ROOT_DIR / "dist" / "TedCompanion.exe"
        else:
            binary_path = ROOT_DIR / "dist" / "TedCompanion.app"
        if not binary_path.exists():
            print(f"❌ Lỗi: Không tìm thấy file nhị phân tại {binary_path}. Hãy chạy không kèm --skip-build.")
            sys.exit(1)

    # 2. Chuẩn bị thư mục xuất bản dist_release/
    out_dir = ROOT_DIR / "dist_release"
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = binary_path.suffix or (".exe" if platform_key == "windows" else ".zip")
    target_binary = out_dir / f"TedCompanion-{version}-{platform_key}{ext}"
    shutil.copy2(binary_path, target_binary)

    # 3. Tạo version.json
    manifest = create_release_manifest(
        version=version,
        binary_path=target_binary,
        url_base=url_base,
        changelog=args.changelog,
        platform_key=platform_key,
    )
    version_file = out_dir / "version.json"
    version_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # In kết quả tạo bản build
    print("\n" + "=" * 70)
    print("🎉 ĐÃ ĐÓNG GÓI BẢN PHÁT HÀNH THÀNH CÔNG!")
    print("=" * 70)
    print(f"• Phiên bản:        v{version}")
    print(f"• File thực thi:    {target_binary.name} ({target_binary.stat().st_size:,} bytes)")
    print(f"• SHA256:           {manifest['platforms'][platform_key]['sha256']}")
    print(f"• File manifest:    {version_file}")
    print(f"• URL tải bản cài:  {manifest['platforms'][platform_key]['url']}")

    # 4. Tải lên MinIO nếu có cấu hình và không bị bỏ qua
    uploaded_minio = False
    if args.skip_upload:
        print("\n⚠️  Đã chọn --skip-upload: Bỏ qua bước tải lên MinIO.")
    elif not minio_cfg:
        print("\n" + "!" * 70)
        print("⚠️  CHƯA CẤU HÌNH MINIO STORAGE HOẶC THIẾU THÔNG TIN XÁC THỰC!")
        print("   File build và version.json đã được lưu tại thư mục dist_release/.")
        print("   Để tự động upload lên MinIO:")
        print("   1. Mở file '.env' trong thư mục ted-companion (tham khảo ted-companion/.env.example)")
        print("   2. Điền MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET_NAME")
        print("   3. Chạy lại release.bat")
        print("!" * 70)
    else:
        uploaded_minio = upload_release_to_minio(
            binary_path=target_binary,
            version_file=version_file,
            minio_cfg=minio_cfg,
        )

    # 5. In kết luận và hướng dẫn
    print("\n" + "=" * 70)
    if uploaded_minio:
        clean_pub = minio_cfg['public_url'].rstrip('/')
        print("🚀 PHÁT HÀNH THÀNH CÔNG LÊN MINIO!")
        print(f"• Đường dẫn version.json: {clean_pub}/version.json")
        print(f"• Đường dẫn file cài đặt: {manifest['platforms'][platform_key]['url']}")
    else:
        print("👉 HƯỚNG DẪN TẢI LÊN MÁY CHỦ THỦ CÔNG (NẾU KHÔNG DÙNG MINIO):")
        print(f"   scp -r dist_release/* user@your-vps-ip:/var/www/ted-updates/")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
