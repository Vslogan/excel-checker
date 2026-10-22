"""Ports implemented by the CLI, Qt frontend, or tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class InteractionPort(Protocol):
    def prompt(self, message: str) -> str | None:
        """Ask the user for text; return None when the prompt is cancelled."""

    def notify(self, message: str) -> None:
        """Show a non-blocking or modal message to the user."""


class ClipboardReadPort(Protocol):
    def read_text(self) -> str | None:
        """Return plain text from the clipboard, or None when unavailable."""


class ClipboardWritePort(Protocol):
    def write_text(self, text: str) -> None:
        """Replace the clipboard contents with plain text."""


class ClipboardPort(ClipboardReadPort, ClipboardWritePort, Protocol):
    """A clipboard adapter that can both monitor and write clipboard text."""


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: Any


class HttpClientPort(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Any,
        timeout_ms: float,
    ) -> HttpResponse:
        """Perform one synchronous HTTP request and return its decoded body."""
