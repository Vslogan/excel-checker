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


class TableData:
    """Represents tabular data parsed from clipboard."""

    def __init__(
        self,
        raw_text: Any = "",
        grid: Optional[List[List[str]]] = None,
        rows: Optional[int] = None,
        cols: Optional[int] = None,
    ):
        if isinstance(raw_text, (list, tuple)):
            rows_list = raw_text
            self.grid = [[str(cell) for cell in row] for row in rows_list]
            self.rows = len(self.grid)
            self.cols = max((len(r) for r in self.grid), default=0) if self.rows > 0 else 0
            for r in self.grid:
                if len(r) < self.cols:
                    r.extend([""] * (self.cols - len(r)))
            self.raw_text = "\n".join("\t".join(r) for r in self.grid)
        else:
            self.raw_text = str(raw_text or "")
            self.grid = list(grid or [])
            self.rows = rows if rows is not None else len(self.grid)
            self.cols = cols if cols is not None else (
                max((len(r) for r in self.grid), default=0) if self.rows > 0 else 0
            )

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

    def matches_size(
        self,
        expected_rows: int,
        expected_cols: int,
        fuzzy_row: bool = False,
        fuzzy_col: bool = False,
    ) -> bool:
        """Check if table size matches expected dimensions.

        Args:
            expected_rows: Expected number of rows (or <= 0 for wildcard)
            expected_cols: Expected number of columns (or <= 0 for wildcard)
            fuzzy_row: When True, row dimension is ignored (any row count matches)
            fuzzy_col: When True, col dimension is ignored (any col count matches)

        Returns:
            True if matching, False otherwise.
        """
        match_r = fuzzy_row or (expected_rows <= 0) or (self.rows == expected_rows)
        match_c = fuzzy_col or (expected_cols <= 0) or (self.cols == expected_cols)
        if match_r and match_c:
            return True

        # Special compatibility rule:
        # If expected is 1x1 (or fuzzy dimensions) and the content is plain text (even if multi-line without tabs),
        # treat the entire content as a 1x1 table cell (0, 0).
        if (fuzzy_row or expected_rows == 1) and (fuzzy_col or expected_cols == 1):
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
