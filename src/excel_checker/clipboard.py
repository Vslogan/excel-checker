"""Background polling clipboard monitor, independent of any GUI toolkit."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from .dispatcher import ProcessOutcome, RuleDispatcher
from .interfaces import ClipboardReadPort
from .parsing import parse_clipboard_text
from .repository import RuleRepository

logger = logging.getLogger(__name__)


class ClipboardMonitor:
    def __init__(
        self,
        clipboard: ClipboardReadPort,
        repository: RuleRepository,
        dispatcher: RuleDispatcher,
        *,
        interval_seconds: float = 0.25,
        ignore_initial_clipboard: bool = True,
        on_result: Callable[[ProcessOutcome], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_config_error: Callable[[dict[Any, str]], None] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.clipboard = clipboard
        self.repository = repository
        self.dispatcher = dispatcher
        self.interval_seconds = interval_seconds
        self.ignore_initial_clipboard = ignore_initial_clipboard
        self.on_result = on_result
        self.on_error = on_error
        self.on_config_error = on_config_error
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_text: str | None = None
        self._has_seen_clipboard = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="excel-checker-clipboard", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float | None = 3.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            if not thread.is_alive():
                self._thread = None
        elif thread is None:
            self._thread = None

    def reset_payload_cache(self) -> None:
        """Allow a frontend clipboard-change event to reprocess identical text."""
        self._last_text = None
        self._has_seen_clipboard = True

    def mark_payload_seen(self, text: str) -> None:
        """Record a payload written by the app so it is not handled as a new copy."""
        self._last_text = text
        self._has_seen_clipboard = True

    def poll_once(self) -> ProcessOutcome | None:
        changed = self.repository.reload_if_changed()
        if changed and self.on_config_error:
            self.on_config_error(self.repository.errors)

        text = self.clipboard.read_text()
        if text is None:
            if not self._has_seen_clipboard:
                # A missing clipboard at startup is the baseline too; the first
                # actual copied text after that is a change and should run.
                self._has_seen_clipboard = True
                self._last_text = None
            return None
        if not isinstance(text, str):
            raise TypeError("clipboard adapter must return text or None")

        if not self._has_seen_clipboard:
            self._has_seen_clipboard = True
            self._last_text = text
            if self.ignore_initial_clipboard:
                return None
        elif text == self._last_text:
            return None
        else:
            self._last_text = text

        outcome = self.dispatcher.process(parse_clipboard_text(text), self.repository.rules)
        if self.on_result is not None:
            self.on_result(outcome)
        return outcome

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # noqa: BLE001 - isolate one bad clipboard read/action
                if self.on_error is not None:
                    try:
                        self.on_error(exc)
                    except Exception:  # an error callback must not kill polling
                        logger.exception("Clipboard monitor error callback failed")
            self._stop_event.wait(self.interval_seconds)
