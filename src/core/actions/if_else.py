"""
If-Else branching action block.
Supports conditional selection structure with multi-level nesting and optional else branch.
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
        Upon finishing then branch, skips over the else branch (if else_count > 0).
    If zero:
        Jumps directly to the else branch (if else_count > 0) or skips past the then branch.
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
        # Number of blocks in then branch (defaults to 1)
        raw_then = (
            self.config.get("then_count")
            or self.config.get("if_count")
            or self.config.get("if下面有多少个积木")
            or self.config.get("if积木数")
            or self.config.get("then步骤数")
        )
        self.then_count: int = int(raw_then) if raw_then is not None else 1

        # Number of blocks in else branch (defaults to 0: 0 lines = no else branch)
        raw_else = (
            self.config.get("else_count")
            or self.config.get("else下面有多少个积木")
            or self.config.get("else积木数")
            or self.config.get("else步骤数")
        )
        self.else_count: int = int(raw_else) if raw_else is not None else 0
        self.has_else: bool = (self.else_count > 0)

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        cond_expr = str(self.condition).strip() or "1"
        try:
            cond_res = evaluate_expression(cond_expr, context.variables)
        except ExpressionError as e:
            return ActionResult.fail(f"If 条件表达式计算失败: {str(e)}")

        current_line = context.current_step
        then_cnt = max(0, self.then_count)
        else_cnt = max(0, self.else_count)

        if is_truthy(cond_res):
            ui_delegate.log(f"[IfElse] 条件 '{cond_expr}' 结果为非零 (True)，进入 IF 分支 (包含 {then_cnt} 个步骤)")
            skip_after = None
            if else_cnt > 0:
                skip_after = (current_line + then_cnt, current_line + 1 + then_cnt + else_cnt)

            return ActionResult.ok(
                output="条件成立，进入 IF 分支",
                jump_to=None,
                skip_after=skip_after,
                branch_info={
                    "branch": "then",
                    "step": current_line,
                    "then_count": then_cnt,
                    "else_count": else_cnt,
                },
            )
        else:
            # Condition is False (zero)
            if else_cnt > 0:
                target = current_line + 1 + then_cnt
                ui_delegate.log(f"[IfElse] 条件 '{cond_expr}' 结果为 0 (False)，跳转至 ELSE 分支第 {target} 步")
                return ActionResult.ok(
                    output=f"条件为0，跳转至 ELSE 分支第 {target} 步",
                    jump_to=target,
                    branch_info={
                        "branch": "else",
                        "step": current_line,
                        "then_count": then_cnt,
                        "else_count": else_cnt,
                    },
                )
            else:
                target = current_line + 1 + then_cnt
                ui_delegate.log(f"[IfElse] 条件 '{cond_expr}' 结果为 0 (False)，跳过 IF 分支至第 {target} 步")
                return ActionResult.ok(
                    output=f"条件为0，跳过 IF 分支至第 {target} 步",
                    jump_to=target,
                    branch_info=None,
                )
