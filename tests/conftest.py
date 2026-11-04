"""
`settings` và `db` là singleton tạo lúc import → phải trỏ TED_HOME vào thư mục tạm
TRƯỚC khi bất kỳ module `src.*` nào được import, để test không bao giờ chạm ~/.ted thật.
"""

import os
import tempfile

os.environ["TED_HOME"] = tempfile.mkdtemp(prefix="ted-test-home-")
# Test luôn chạy với 6 con vật mặc định, dù máy dev đang cài Character Pack trong assets/character_pack
os.environ["TED_CHARACTER_PACK_DIR"] = tempfile.mkdtemp(prefix="ted-test-no-pack-")
# Test cũng không nạp 36 nhân vật bundle mở khoá dần trong assets/unlockable_skin_packs
os.environ["TED_UNLOCKABLE_SKIN_PACKS_DIR"] = tempfile.mkdtemp(prefix="ted-test-no-unlockables-")

import src.core.python315_lazy_import_workaround  # noqa: E402,F401  (phải đứng trước PySide6)

import pytest  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402


@pytest.fixture
def memory_engine():
    import src.core.models  # noqa: F401  (đăng ký bảng vào metadata)

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()
