"""User input action implementation."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate


class UserInputAction(BaseAction):
    """Action to prompt the user with an input dialog."""

    action_type = "user_input"
    display_name = "用户输入"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.prompt = (
            self.config.get("prompt")
            or self.config.get("提示文本")
            or "请输入内容"
        )
        self.variable = (
            self.config.get("variable")
            or self.config.get("变量名")
            or "user_input"
        )
        self.default = (
            self.config.get("default")
            or self.config.get("默认值")
            or ""
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        rendered_prompt = context.render_template(self.prompt)
        rendered_default = context.render_template(self.default)

        ui_delegate.log(f"[UserInput] Waiting for user input with prompt: '{rendered_prompt}'...")
        user_val = ui_delegate.prompt_user(rendered_prompt, rendered_default)

        if user_val is None:
            # User cancelled the prompt dialog
            err = f"用户取消了输入: '{rendered_prompt}'"
            ui_delegate.log(f"[UserInput Cancelled] {err}")
            return ActionResult.fail(err)

        context.set_var(self.variable, user_val)
        ui_delegate.log(f"[UserInput] Set '{self.variable}' = '{user_val}'")
        return ActionResult.ok(user_val)
