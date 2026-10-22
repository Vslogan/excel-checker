"""Optional pyperclip adapter for the command-line watcher."""

from __future__ import annotations

from typing import Any

from .errors import ClipboardError


class PyperclipAdapter:
    """Read/write plain-text clipboard contents via the optional pyperclip package."""

    def __init__(self) -> None:
        try:
            import pyperclip
        except ImportError as exc:
            raise ClipboardError(
                "缺少可选依赖 pyperclip；请执行 pip install 'excel-checker[system-clipboard]'"
            ) from exc
        self._pyperclip: Any = pyperclip

    def read_text(self) -> str:
        try:
            return self._pyperclip.paste()
        except Exception as exc:
            raise ClipboardError(f"读取系统剪切板失败：{exc}") from exc

    def write_text(self, text: str) -> None:
        try:
            self._pyperclip.copy(text)
        except Exception as exc:
            raise ClipboardError(f"写入系统剪切板失败：{exc}") from exc
