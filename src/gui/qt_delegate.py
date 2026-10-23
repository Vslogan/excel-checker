"""Thread-safe UI delegate for PyQt5 GUI and background worker threads."""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox, QWidget


class ThreadSafeUIDelegate(QObject):
    """UIDelegate implementation safely callable from both GUI and worker threads.

    When called from worker threads, signals the GUI thread to display dialogs
    and waits on a threading.Event for the user response, preventing GUI freezes.
    """

    log_requested = pyqtSignal(str)
    input_requested = pyqtSignal(str, str, object, object)  # prompt, default, event, result_box
    message_requested = pyqtSignal(str, str, object)       # title, message, event
    toast_requested = pyqtSignal(str, int, bool, str, str, object)  # content, duration, blocking, screen, pos, event
    clipboard_write_requested = pyqtSignal(str, object)    # content, event

    def __init__(self, parent_widget: Optional[QWidget] = None):
        super().__init__()
        self.parent_widget = parent_widget
        self.clipboard_backup: str = ""

        # Connect internal signals to GUI thread slots
        self.input_requested.connect(self._handle_input_request)
        self.message_requested.connect(self._handle_message_request)
        self.toast_requested.connect(self._handle_toast_request)
        self.clipboard_write_requested.connect(self._handle_clipboard_write_request)
        self.log_requested.connect(self._handle_log_request)

        # External log receiver (e.g. MainWindow.append_log)
        self.on_log_callback: Optional[Callable[[str], None]] = None

    def _is_gui_thread(self) -> bool:
        app = QApplication.instance()
        if not app:
            return True
        return QThread.currentThread() == app.thread()

    def _is_offscreen(self) -> bool:
        return os.environ.get("QT_QPA_PLATFORM") == "offscreen"

    # --- UIDelegate Protocol Methods ---

    def prompt_user(self, prompt: str, default: str = "") -> Optional[str]:
        """Prompt user with text dialog. Thread-safe."""
        if self._is_gui_thread():
            if self._is_offscreen():
                return default or "test_input"
            text, ok = QInputDialog.getText(
                self.parent_widget,
                "用户输入 (User Input)",
                prompt,
                text=default,
            )
            return text if ok else None

        # Called from worker thread: signal GUI thread and wait
        event = threading.Event()
        result_box: List[Optional[str]] = [None]
        self.input_requested.emit(prompt, default, event, result_box)
        event.wait()
        return result_box[0]

    def show_message(self, title: str, message: str) -> None:
        """Display an alert dialog. Thread-safe."""
        if self._is_gui_thread():
            if not self._is_offscreen():
                QMessageBox.information(self.parent_widget, title or "提示", message)
            return

        # Called from worker thread
        event = threading.Event()
        self.message_requested.emit(title or "提示", message, event)
        event.wait()

    def show_toast(
        self,
        content: str,
        duration_ms: int = 2000,
        blocking: bool = False,
        screen: str = "cursor",
        position: str = "bottom_center",
    ) -> None:
        """Display a floating toast notification. Thread-safe."""
        if self._is_gui_thread():
            if not self._is_offscreen():
                from src.gui.toast_window import ToastManager
                from PyQt5.QtCore import QEventLoop

                if blocking:
                    loop = QEventLoop()
                    ToastManager.show(
                        content=content,
                        duration_ms=duration_ms,
                        blocking=True,
                        screen_mode=screen,
                        position_mode=position,
                        on_finished_cb=loop.quit,
                    )
                    loop.exec_()
                else:
                    ToastManager.show(
                        content=content,
                        duration_ms=duration_ms,
                        blocking=False,
                        screen_mode=screen,
                        position_mode=position,
                    )
            return

        # Called from worker thread
        event = threading.Event()
        self.toast_requested.emit(content, duration_ms, blocking, screen, position, event)
        if blocking:
            event.wait()

    def set_clipboard(self, content: str) -> None:
        """Write content to clipboard. Thread-safe."""
        self.clipboard_backup = content
        if self._is_gui_thread():
            clip = QApplication.clipboard()
            if clip:
                clip.setText(content)
            return

        event = threading.Event()
        self.clipboard_write_requested.emit(content, event)
        event.wait()

    def get_clipboard(self) -> str:
        """Read clipboard content. Thread-safe."""
        clip = QApplication.clipboard()
        if clip:
            return clip.text()
        return self.clipboard_backup

    def log(self, message: str) -> None:
        """Append log message. Thread-safe."""
        self.log_requested.emit(message)

    # --- Slots executing on GUI thread ---

    @pyqtSlot(str, str, object, object)
    def _handle_input_request(self, prompt: str, default: str, event: threading.Event, result_box: List[Optional[str]]):
        try:
            if not self._is_offscreen():
                text, ok = QInputDialog.getText(
                    self.parent_widget,
                    "用户输入 (User Input)",
                    prompt,
                    text=default,
                )
                result_box[0] = text if ok else None
            else:
                result_box[0] = default or "test_input"
        except Exception:
            result_box[0] = None
        finally:
            event.set()

    @pyqtSlot(str, str, object)
    def _handle_message_request(self, title: str, message: str, event: threading.Event):
        try:
            if not self._is_offscreen():
                QMessageBox.information(self.parent_widget, title, message)
        finally:
            event.set()

    @pyqtSlot(str, int, bool, str, str, object)
    def _handle_toast_request(
        self,
        content: str,
        duration_ms: int,
        blocking: bool,
        screen: str,
        position: str,
        event: threading.Event,
    ):
        try:
            if not self._is_offscreen():
                from src.gui.toast_window import ToastManager
                if blocking:
                    ToastManager.show(
                        content=content,
                        duration_ms=duration_ms,
                        blocking=True,
                        screen_mode=screen,
                        position_mode=position,
                        on_finished_cb=event.set,
                    )
                else:
                    ToastManager.show(
                        content=content,
                        duration_ms=duration_ms,
                        blocking=False,
                        screen_mode=screen,
                        position_mode=position,
                    )
                    event.set()
            else:
                event.set()
        except Exception:
            event.set()

    @pyqtSlot(str, object)
    def _handle_clipboard_write_request(self, content: str, event: threading.Event):
        try:
            clip = QApplication.clipboard()
            if clip:
                clip.setText(content)
        finally:
            event.set()

    @pyqtSlot(str)
    def _handle_log_request(self, message: str):
        if self.on_log_callback:
            self.on_log_callback(message)


# Backward compatibility alias
QtUIDelegate = ThreadSafeUIDelegate
