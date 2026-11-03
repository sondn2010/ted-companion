"""Mixin chip loại vấn đề của UntangleDialog (nhãn/số lượng đổi theo engine, nhớ lựa chọn cuối mỗi engine trong KV)."""

import logging
from typing import Optional

from PySide6.QtWidgets import QPushButton

from src.core.i18n import tr
from src.core.idea_untangle.untangle_problem_kinds_by_engine import DEFAULT_KIND, kind_i18n_key, kinds_for, normalize_kind
from src.ui.button_text_escape import btn_text

logger = logging.getLogger("ted")
LAST_KIND_KV_PREFIX = "untangle_last_kind:"


class UntangleKindChipsMixin:
    def _refresh_kinds(self, preselect: Optional[str] = None) -> None:
        while self.kind_row.count():   # gỡ cả chip lẫn stretch cũ
            item = self.kind_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.kind_buttons = {}
        saved = self._kv.get(LAST_KIND_KV_PREFIX + self._engine) if self._kv else None
        self._kind = normalize_kind(self._engine, preselect or self._kind_if_valid() or saved or DEFAULT_KIND)
        for kind in kinds_for(self._engine):
            btn = QPushButton(btn_text(tr(kind_i18n_key(kind))))
            btn.setCheckable(True)
            btn.setChecked(kind == self._kind)
            btn.clicked.connect(lambda _=False, k=kind: self._select_kind(k))
            self.kind_row.addWidget(btn)
            self.kind_buttons[kind] = btn
        self.kind_row.addStretch()

    def _kind_if_valid(self) -> Optional[str]:
        return self._kind if self._kind in kinds_for(self._engine) and self._kind != DEFAULT_KIND else None

    def _select_kind(self, kind: str) -> None:
        self._kind = kind
        for k, btn in self.kind_buttons.items():
            btn.setChecked(k == kind)
        if self._kv:
            try:
                self._kv.set(LAST_KIND_KV_PREFIX + self._engine, kind)
            except Exception:
                logger.exception("Gỡ Rối: không lưu được loại vấn đề")

