"""
If-Else branching action block.
Supports conditional selection structure with optional else branch.
"""

from typing import Any, Dict
from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import evaluate_expression, is_truthy, ExpressionError


class IfElseAction(BaseAction):
    """
    If-Else conditional action:
    Evaluates an if-condition expression.
    If non-zero:
        Executes the then branch (next then_count steps).
        Upon finishing then branch, automatically skips over the else branch (if enabled).
    If zero:
        Jumps directly to the else branch (if enabled) or skips past the then branch.
    """

    action_type = "if_else"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Condition expression
        self.condition: str = (
            self.config.get("condition")
            or self.config.get("cond")
            or self.config.get("if_condition")
            or self.config.get("if条件")
            or self.config.get("条件")
            or "1"
        )
        # Has Else branch toggle
        self.has_else: bool = bool(
            self.config.get("has_else", False)
            or self.config.get("else", False)
            or self.config.get("是否有else", False)
            or self.config.get("包含else", False)
        )
        # Number of blocks in then branch
        self.then_count: int = int(
            self.config.get("then_count")
            or self.config.get("if_count")
            or self.config.get("if下面有多少个积木")
            or self.config.get("if积木数")
            or self.config.get("then步骤数")
            or 1
        )
        # Number of blocks in else branch
        self.else_count: int = int(
            self.config.get("else_count")
            or self.config.get("else下面有多少个积木")
            or self.config.get("else积木数")
            or self.config.get("else步骤数")
            or 0
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        cond_expr = str(self.condition).strip() or "1"
        try:
            cond_res = evaluate_expression(cond_expr, context.variables)
        except ExpressionError as e:
            return ActionResult.fail(f"If 条件表达式计算失败: {str(e)}")

        current_line = context.current_step
        then_cnt = max(0, self.then_count)
        else_cnt = max(0, self.else_count) if self.has_else else 0

        if is_truthy(cond_res):
            ui_delegate.log(f"[IfElse] 条件 '{cond_expr}' 结果为非零 (True)，进入 IF 分支 (包含 {then_cnt} 个步骤)")
            # If there is an else branch, register a skip after then branch finishes
            skip_after = None
            if self.has_else and else_cnt > 0:
                at_step = current_line + then_cnt
                skip_to = current_line + 1 + then_cnt + else_cnt
                skip_after = (at_step, skip_to)

            return ActionResult.ok(
                output="条件成立，执行 IF 分支",
                jump_to=None,
                skip_after=skip_after,
            )
        else:
            # Condition is False (zero)
            if self.has_else and else_cnt > 0:
                target = current_line + 1 + then_cnt
                ui_delegate.log(f"[IfElse] 条件 '{cond_expr}' 结果为 0 (False)，跳转至 ELSE 分支第 {target} 步")
                return ActionResult.ok(
                    output=f"条件为0，跳转至 ELSE 分支第 {target} 步",
                    jump_to=target,
                )
            else:
                target = current_line + 1 + then_cnt
                ui_delegate.log(f"[IfElse] 条件 '{cond_expr}' 结果为 0 (False)，跳过 IF 分支至第 {target} 步")
                return ActionResult.ok(
                    output=f"条件为0，跳过 IF 分支至第 {target} 步",
                    jump_to=target,
                )
