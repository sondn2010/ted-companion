"""QPushButton/QCheckBox/QRadioButton/QAction/QMenu coi '&' là mnemonic → cần '&&' để hiển thị đúng ký tự '&'."""


def btn_text(text: str) -> str:
    """Escape '&' thành '&&' cho text nút lấy từ i18n (không sửa chuỗi i18n gốc)."""
    return text.replace("&", "&&")
