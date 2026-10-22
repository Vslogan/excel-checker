"""Helpers for turning clipboard text into a rectangular table."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

Table = list[list[str]]


def parse_clipboard_text(text: str) -> Table:
    """Parse Excel/Sheets plain-text clipboard data.

    Spreadsheet applications conventionally copy cells as tab-separated rows
    with CRLF line endings and one final line break. A single ordinary text
    value is deliberately treated as a 1x1 table for compatibility with apps
    that do not expose a table clipboard format.
    """
    if not isinstance(text, str):
        raise TypeError("clipboard text must be a string")

    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    # Let csv.reader consume the final terminator itself; a second final line
    # break then remains an explicit blank row instead of being discarded.
    if normalized == "":
        return [[""]]
    try:
        rows = [
            list(row) for row in csv.reader(io.StringIO(normalized, newline=""), delimiter="\t")
        ]
        return [row if row else [""] for row in rows]
    except csv.Error as exc:
        raise ValueError(f"clipboard TSV parse failed: {exc}") from exc


def rectangular_dimensions(table: Sequence[Sequence[object]]) -> tuple[int, int] | None:
    """Return (rows, columns), or None for an empty/ragged table."""
    if not table:
        return None
    width = len(table[0])
    if width == 0 or any(len(row) != width for row in table):
        return None
    return len(table), width
