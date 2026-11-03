"""Hỏi tên người dùng lần đầu mở app (mỗi máy 1 người). "Để sau" → lần mở sau hỏi lại, tạm gọi là "bạn"."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from src.config import USER_NAME_MAX_LEN, settings
from src.core.i18n import tr


class UserNameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("user_name_dialog_title"))
        self.txt_name = QLineEdit()
        self.txt_name.setMaxLength(USER_NAME_MAX_LEN)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_later = buttons.addButton(tr("user_name_dialog_later"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        btn_later.clicked.connect(self.reject)
        self.txt_name.textChanged.connect(lambda text: self.btn_ok.setEnabled(bool(text.strip())))
        self.btn_ok.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("user_name_dialog_prompt")))
        layout.addWidget(self.txt_name)
        layout.addWidget(buttons)

    def accept(self) -> None:
        settings.set_user_name(self.txt_name.text())
        if settings.user_name:
            settings.save()
        super().accept()


def ask_user_name_if_missing(parent=None) -> None:
    if settings.user_name:
        return
    UserNameDialog(parent).exec()
