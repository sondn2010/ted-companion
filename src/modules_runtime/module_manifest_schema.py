"""Schema `module.yaml`: manifest được validate chặt (extra=forbid) để lỗi gõ sai không bị bỏ qua."""

import os
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SLUG = r"^[a-z0-9_-]{1,32}$"


class ModuleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_SLUG)
    name: str
    icon: str = ""
    engine: Literal["work", "coach"]
    connection: str
    enabled: bool = False
    order: int = 100
    # learner_id đi vào đường dẫn file trên server (skill progress) → bắt buộc slug
    learner_id: Optional[str] = Field(default=None, pattern=_SLUG)
    prompts: dict[str, str] = Field(default_factory=dict)   # chỉ work: key -> đường dẫn md tương đối
    settings: dict[str, Any] = Field(default_factory=dict)  # chỉ work: WorkSettings validate ở phase 04/05
    module_dir: Optional[Path] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _check_engine_rules(self):
        if self.engine == "coach":
            if not self.learner_id:
                raise ValueError("module coach bắt buộc có learner_id")
            if self.prompts or self.settings:
                raise ValueError("module coach không được khai báo prompts/settings (Hermes quyết định nội dung)")
        return self

    def prompt_path(self, key: str) -> Optional[Path]:
        """Đường dẫn tuyệt đối tới prompt md; None nếu thiếu key/thư mục hoặc thoát khỏi module_dir."""
        rel = self.prompts.get(key)
        if not rel or self.module_dir is None:
            return None
        # normcase tránh lệch hoa/thường & tên 8.3 trên Windows (PyInstaller _MEIPASS)
        base = Path(os.path.normcase(os.path.realpath(self.module_dir)))
        resolved = Path(os.path.normcase(os.path.realpath(self.module_dir / rel)))
        return resolved if resolved.is_relative_to(base) else None
