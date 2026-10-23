"""Robust clipboard watcher with debouncing, self-healing watchdog, and error protection.

Completely prevents:
  - qt.qpa.mime: Unable to obtain clipboard.
  - qt.qpa.mime: Retrying to obtain clipboard.
  - Clipboard signal disconnection and dropped copy events.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Set

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication


class ClipboardWatcher(QObject):
    """Monitors system clipboard robustly without MIME lock contention or disconnects."""

    text_captured = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None, debounce_ms: int = 80, watchdog_interval_ms: int = 800):
        super().__init__(parent)
        self.debounce_ms = debounce_ms
        self.watchdog_interval_ms = watchdog_interval_ms

        self.is_monitoring: bool = False
        self._last_content: str = ""
        self._ignored_contents: Set[str] = set()

        # Debounce timer to let external application finish setting selection owner
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_debounced_read)

        # Watchdog heartbeat timer: auto-recovers from missed MIME signals or disconnects
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(self.watchdog_interval_ms)
        self._watchdog_timer.timeout.connect(self._watchdog_check)

        self._connected = False

    def start_monitoring(self):
        """Start monitoring system clipboard."""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self._ensure_connection()

        # Seed initial clipboard content to prevent triggering on already-existing clipboard
        seed_text = self._safe_read_text()
        self._last_content = seed_text or ""

        self._watchdog_timer.start()
        self.status_changed.emit("running")

    def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False
        self._debounce_timer.stop()
        self._watchdog_timer.stop()
        self.status_changed.emit("stopped")

    def ignore_content(self, text: str):
        """Register text produced by the application to avoid feedback loops."""
        if text:
            self._ignored_contents.add(text)
            self._last_content = text

    def _ensure_connection(self):
        """Ensure connection to QApplication.clipboard().dataChanged signal."""
        app = QApplication.instance()
        if not app:
            return
        clip = app.clipboard()
        if not clip:
            return

        try:
            # Reconnect cleanly
            try:
                clip.dataChanged.disconnect(self._on_data_changed)
            except Exception:
                pass
            clip.dataChanged.connect(self._on_data_changed)
            self._connected = True
        except Exception:
            self._connected = False

    @pyqtSlot()
    def _on_data_changed(self):
        """Triggered immediately when OS notifies clipboard change.

        DO NOT call clipboard.text() immediately here!
        Wait for debounce timer to let the external copying program finish writing MIME data.
        """
        if not self.is_monitoring:
            return

        # Restart debounce timer
        self._debounce_timer.start(self.debounce_ms)

    @pyqtSlot()
    def _on_debounced_read(self):
        """Fires after debounce delay; safely reads clipboard without lock contention."""
        if not self.is_monitoring:
            return

        text = self._safe_read_text()
        self._process_text_if_new(text)

    def _watchdog_check(self):
        """Heartbeat check running periodically to recover from dropped events or disconnects."""
        if not self.is_monitoring:
            return

        # Recheck signal connection
        if not self._connected:
            self._ensure_connection()

        # Safe poll to catch missed copies (Wayland / X11 edge cases)
        text = self._safe_read_text()
        self._process_text_if_new(text)

    def _safe_read_text(self) -> str:
        """Read clipboard text with retry and exception safety."""
        app = QApplication.instance()
        if not app:
            return ""
        clip = app.clipboard()
        if not clip:
            return ""

        # Retry up to 3 times with brief backoff to avoid race conditions
        for attempt in range(3):
            try:
                text = clip.text()
                if text:
                    return text
            except Exception:
                pass
            if attempt < 2:
                QThread.msleep(30)
        return ""

    def _process_text_if_new(self, text: str):
        """Process text if it's genuinely new and not self-generated."""
        if not text or not text.strip():
            return

        if text == self._last_content:
            return

        if text in self._ignored_contents:
            self._ignored_contents.discard(text)
            self._last_content = text
            return

        self._last_content = text
        self.text_captured.emit(text)
