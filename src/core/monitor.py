"""Clipboard monitor for detecting copied tabular data and triggering workflows."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from src.core.config_model import RuleConfig
from src.core.context import UIDelegate
from src.core.engine import WorkflowEngine, WorkflowExecutionResult
from src.core.table_parser import TableData


class ClipboardMonitor:
    """Monitors clipboard content and dispatches matched events to WorkflowEngine."""

    def __init__(
        self,
        engine: WorkflowEngine,
        ui_delegate: Optional[UIDelegate] = None,
        poll_interval: float = 0.5,
    ):
        self.engine = engine
        self.ui_delegate = ui_delegate
        self.poll_interval = poll_interval

        self.is_running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._last_content: str = ""
        self._ignore_contents: set[str] = set()

        # Callbacks
        self.on_matched: Optional[Callable[[RuleConfig, TableData, WorkflowExecutionResult], None]] = None
        self.on_ignored: Optional[Callable[[TableData, str], None]] = None
        self.on_status_change: Optional[Callable[[bool], None]] = None

    def ignore_content(self, text: str) -> None:
        """Mark text to be ignored on next clipboard capture to prevent feedback loops."""
        self._ignore_contents.add(text)
        self._last_content = text

    def handle_new_text(self, text: str) -> Optional[WorkflowExecutionResult]:
        """Core handler for intercepted clipboard text."""
        if not text or not text.strip():
            return None

        if text == self._last_content:
            return None

        if text in self._ignore_contents:
            self._ignore_contents.discard(text)
            self._last_content = text
            return None

        self._last_content = text

        table = TableData.from_text(text)

        # Check hot reload for configs
        self.engine.check_hot_reload()

        rule = self.engine.find_matching_rule(table)
        if not rule:
            if self.on_ignored:
                self.on_ignored(table, f"无匹配规则 (尺寸: {table.rows}x{table.cols})")
            return None

        # Execute rule
        result = self.engine.execute_rule(rule, table, ui_delegate=self.ui_delegate)
        if self.on_matched:
            self.on_matched(rule, table, result)

        return result

    def start_polling(self, get_clipboard_fn: Callable[[], str]) -> None:
        """Start monitoring using background thread polling."""
        if self.is_running:
            return

        self.is_running = True
        if self.on_status_change:
            self.on_status_change(True)

        def _loop():
            while self.is_running:
                try:
                    current_text = get_clipboard_fn()
                    if current_text and current_text != self._last_content:
                        self.handle_new_text(current_text)
                except Exception as e:
                    if self.ui_delegate:
                        self.ui_delegate.log(f"[Monitor Exception] {e}")
                time.sleep(self.poll_interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_polling(self) -> None:
        """Stop background polling thread."""
        self.is_running = False
        if self.on_status_change:
            self.on_status_change(False)
