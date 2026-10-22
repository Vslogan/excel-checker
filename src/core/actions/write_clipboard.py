"""Write clipboard action implementation."""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate


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

        final_clipboard_text = ""

        if self.data_type in ("table", "表格"):
            # If input is CSV formatted (comma separated), parse and convert to TSV
            try:
                if isinstance(rendered_data, list):
                    # List of lists
                    rows = rendered_data
                else:
                    reader = csv.reader(io.StringIO(str(rendered_data).strip()))
                    rows = [row for row in reader]

                tsv_lines = []
                for row in rows:
                    tsv_lines.append("\t".join(str(c) for c in row))
                final_clipboard_text = "\r\n".join(tsv_lines)
            except Exception as e:
                ui_delegate.log(f"[WriteClipboard Warn] CSV parse error: {e}, falling back to raw text")
                final_clipboard_text = str(rendered_data)
        else:
            # Plain text
            final_clipboard_text = str(rendered_data)

        ui_delegate.set_clipboard(final_clipboard_text)
        preview = final_clipboard_text.replace("\t", " [TAB] ").replace("\r\n", " [NEWLINE] ")
        if len(preview) > 60:
            preview = preview[:60] + "..."
        ui_delegate.log(f"[WriteClipboard] Successfully wrote to clipboard (type={self.data_type}): {preview}")
        return ActionResult.ok(final_clipboard_text)
