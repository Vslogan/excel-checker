"""Write clipboard action implementation."""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import decode_escape_sequences


class WriteClipboardAction(BaseAction):
    """Action to write formatted text or tabular data to clipboard."""

    action_type = "write_clipboard"
    display_name = "写入剪切板"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.data_type = (
            self.config.get("type")
            or self.config.get("类型")
            or "text"
        ).lower()
        self.data = (
            self.config.get("data")
            or self.config.get("数据")
            or self.config.get("内容")
            or ""
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        # Interpolate variables in data template
        rendered_data = context.render_template(self.data)

        # Decode escape sequences (e.g. \t -> Tab, \n -> Newline, \r -> CR, \\ -> \)
        rendered_text = decode_escape_sequences(str(rendered_data))

        final_clipboard_text = ""

        if self.data_type in ("table", "表格"):
            # Table mode: convert to Excel native TSV (\t between columns, \r\n between rows)
            try:
                if isinstance(rendered_data, list):
                    # List of lists
                    tsv_lines = []
                    for row in rendered_data:
                        tsv_lines.append("\t".join(decode_escape_sequences(str(c)) for c in row))
                    final_clipboard_text = "\r\n".join(tsv_lines)
                elif "\t" in rendered_text:
                    # Tab-separated table: preserve lines and tabs
                    lines = [line.split("\t") for line in rendered_text.splitlines()]
                    tsv_lines = ["\t".join(row) for row in lines]
                    final_clipboard_text = "\r\n".join(tsv_lines)
                else:
                    # CSV formatted (comma separated), parse and convert to TSV
                    reader = csv.reader(io.StringIO(rendered_text.strip()))
                    tsv_lines = []
                    for row in reader:
                        tsv_lines.append("\t".join(str(c) for c in row))
                    final_clipboard_text = "\r\n".join(tsv_lines)
            except Exception as e:
                ui_delegate.log(f"[WriteClipboard Warn] Table parse error: {e}, falling back to raw decoded text")
                final_clipboard_text = rendered_text
        else:
            # Plain text mode: write decoded text
            final_clipboard_text = rendered_text

        ui_delegate.set_clipboard(final_clipboard_text)
        preview = (
            final_clipboard_text.replace("\t", " [TAB] ")
            .replace("\r\n", " [NEWLINE] ")
            .replace("\n", " [NEWLINE] ")
        )
        if len(preview) > 60:
            preview = preview[:60] + "..."
        ui_delegate.log(f"[WriteClipboard] Successfully wrote to clipboard (type={self.data_type}): {preview}")
        return ActionResult.ok(final_clipboard_text)
