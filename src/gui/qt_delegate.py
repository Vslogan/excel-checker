"""Qt-native UI delegate for user interaction during workflow execution."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox, QWidget


class QtUIDelegate(QObject):
    """UIDelegate implementation integrating with PyQt5 widgets and clipboard."""

    log_emitted = pyqtSignal(str)

    def __init__(self, parent_widget: Optional[QWidget] = None):
        super().__init__()
        self.parent_widget = parent_widget
        self.clipboard_backup: str = ""

    def prompt_user(self, prompt: str, default: str = "") -> Optional[str]:
        text, ok = QInputDialog.getText(
            self.parent_widget,
            "用户输入 (User Input)",
            prompt,
            text=default,
        )
        if ok:
            return text
        return None

    def show_message(self, title: str, message: str) -> None:
        QMessageBox.information(self.parent_widget, title or "提示", message)

    def set_clipboard(self, content: str) -> None:
        clip = QApplication.clipboard()
        if clip:
            clip.setText(content)
        self.clipboard_backup = content

    def get_clipboard(self) -> str:
        clip = QApplication.clipboard()
        if clip:
            return clip.text()
        return self.clipboard_backup

    def log(self, message: str) -> None:
        self.log_emitted.emit(message)
