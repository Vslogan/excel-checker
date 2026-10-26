"""Exit action block to immediately terminate workflow execution."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate


class ExitAction(BaseAction):
    """Exit action: immediately terminates the workflow execution cleanly without values."""

    action_type = "exit"
    display_name = "退出"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        step_num = context.current_step
        ui_delegate.log(f"[Exit] 执行退出积木，立即正常结束流程 (步骤 {step_num})")
        return ActionResult.ok(output="流程已退出", is_exit=True)
