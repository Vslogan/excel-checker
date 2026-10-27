"""Show message alert action implementation."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import decode_escape_sequences


class ShowMessageAction(BaseAction):
    """Action to display an alert/message box to the user."""

    action_type = "show_message"
    display_name = "弹出提示框"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.content = (
            self.config.get("content")
            or self.config.get("内容")
            or ""
        )
        self.title = (
            self.config.get("title")
            or self.config.get("标题")
            or "提示"
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        rendered_title = decode_escape_sequences(str(context.render_template(self.title)))
        rendered_content = decode_escape_sequences(str(context.render_template(self.content)))

        ui_delegate.log(f"[ShowMessage] Displaying alert: [{rendered_title}] {rendered_content}")
        ui_delegate.show_message(rendered_title, rendered_content)
        return ActionResult.ok(rendered_content)
