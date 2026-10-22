"""Condition branching action."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate


class ConditionAction(BaseAction):
    """Action to conditionally execute sub-workflows."""

    action_type = "condition"
    display_name = "条件判断"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.left = self.config.get("left", self.config.get("左值", ""))
        self.operator = self.config.get("operator", self.config.get("操作符", "=="))
        self.right = self.config.get("right", self.config.get("右值", ""))
        self.then_actions = self.config.get("then", self.config.get("满足时执行", []))
        self.else_actions = self.config.get("else", self.config.get("不满足时执行", []))

    def evaluate_condition(self, context: ExecutionContext) -> bool:
        left_val = str(context.render_template(self.left))
        right_val = str(context.render_template(self.right))
        op = str(self.operator).strip().lower()

        if op in ("==", "equals", "等于"):
            return left_val == right_val
        elif op in ("!=", "not_equals", "不等于"):
            return left_val != right_val
        elif op in ("contains", "包含"):
            return right_val in left_val
        elif op in ("regex", "正则匹配"):
            return bool(re.search(right_val, left_val))
        elif op in (">", "greater"):
            try:
                return float(left_val) > float(right_val)
            except ValueError:
                return left_val > right_val
        elif op in ("<", "less"):
            try:
                return float(left_val) < float(right_val)
            except ValueError:
                return left_val < right_val
        return False

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        from src.core.actions.base import ActionRegistry

        is_true = self.evaluate_condition(context)
        ui_delegate.log(f"[Condition] Evaluated condition: {self.left} {self.operator} {self.right} -> {is_true}")

        target_list = self.then_actions if is_true else self.else_actions
        for act_cfg in target_list:
            action = ActionRegistry.create(act_cfg)
            res = action.execute(context, ui_delegate)
            if not res.success:
                return res

        return ActionResult.ok(is_true)
