"""Table data parser for clipboard content.

Handles TSV (tab-separated) copied from Excel/WPS/Spreadsheets, CSV,
and plain text fallback.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class TableData:
    """Represents tabular data parsed from clipboard."""
    raw_text: str
    grid: List[List[str]] = field(default_factory=list)
    rows: int = 0
    cols: int = 0

    @classmethod
    def from_text(cls, text: Optional[str]) -> "TableData":
        if not text:
            return cls(raw_text="", grid=[], rows=0, cols=0)

        raw = text
        # Strip single trailing newline commonly appended by Excel/OS copy
        cleaned = raw
        if cleaned.endswith("\r\n"):
            cleaned = cleaned[:-2]
        elif cleaned.endswith("\n") or cleaned.endswith("\r"):
            cleaned = cleaned[:-1]

        if not cleaned:
            return cls(raw_text=raw, grid=[[""]], rows=1, cols=1)

        # Parse using TSV first if tabs exist, or CSV-like if tabs or standard spreadsheet format
        grid: List[List[str]] = []

        if "\t" in cleaned:
            # Excel clipboard format: tab-separated columns, newline-separated rows
            try:
                reader = csv.reader(io.StringIO(cleaned), delimiter="\t")
                grid = [list(row) for row in reader]
            except Exception:
                lines = cleaned.splitlines()
                grid = [line.split("\t") for line in lines]
        else:
            # No tabs present
            lines = cleaned.splitlines()
            if len(lines) <= 1:
                # Pure single-line text -> 1x1 table
                grid = [[cleaned]]
            else:
                # Multi-line text: each line is treated as 1 row with 1 column
                grid = [[line] for line in lines]

        # Calculate dimensions
        rows = len(grid)
        cols = max((len(r) for r in grid), default=0) if rows > 0 else 0

        # Normalize grid so every row has `cols` elements
        for r in grid:
            if len(r) < cols:
                r.extend([""] * (cols - len(r)))

        return cls(raw_text=raw, grid=grid, rows=rows, cols=cols)

    def get_cell(self, row: int, col: int, default: str = "") -> str:
        """Get cell content by 0-based index."""
        if 0 <= row < self.rows:
            row_data = self.grid[row]
            if 0 <= col < len(row_data):
                return row_data[col]
        return default

    def matches_size(self, expected_rows: int, expected_cols: int) -> bool:
        """Check if table size matches expected dimensions.

        Note: When expected size is 1x1, standard plain text is also compatible.
        """
        if self.rows == expected_rows and self.cols == expected_cols:
            return True

        # Special compatibility rule:
        # If expected is 1x1 and the content is plain text (even if multi-line without tabs),
        # treat the entire content as a 1x1 table cell (0, 0).
        if expected_rows == 1 and expected_cols == 1:
            if "\t" not in self.raw_text:
                return True

        return False

    def to_tsv(self) -> str:
        """Convert table data to TSV string."""
        lines = []
        for row in self.grid:
            lines.append("\t".join(row))
        return "\r\n".join(lines)

    def to_csv(self) -> str:
        """Convert table data to CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        for row in self.grid:
            writer.writerow(row)
        return output.getvalue().rstrip("\r\n")

    @classmethod
    def from_csv_string(cls, csv_str: str) -> "TableData":
        """Parse a CSV formatted string into TableData."""
        if not csv_str:
            return cls(raw_text="", grid=[], rows=0, cols=0)
        try:
            reader = csv.reader(io.StringIO(csv_str))
            grid = [list(row) for row in reader]
        except Exception:
            lines = csv_str.splitlines()
            grid = [line.split(",") for line in lines]
        rows = len(grid)
        cols = max((len(r) for r in grid), default=0) if rows > 0 else 0
        for r in grid:
            if len(r) < cols:
                r.extend([""] * (cols - len(r)))
        return cls(raw_text=csv_str, grid=grid, rows=rows, cols=cols)
