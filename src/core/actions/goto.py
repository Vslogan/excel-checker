"""
Goto action block.
Conditionally or unconditionally jumps to a specific line number (1-based index).
"""

from typing import Any, Dict
from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import evaluate_expression, is_truthy, ExpressionError


class GotoAction(BaseAction):
    """
    Goto action: evaluates a condition; if non-zero, instructs the engine
    to redirect execution to the specified 1-based line number.
    """

    action_type = "goto"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Condition expression (default '1' for unconditional jump)
        self.condition: str = (
            self.config.get("condition")
            or self.config.get("cond")
            or self.config.get("条件")
            or self.config.get("跳转条件")
            or "1"
        )
        # Target line number (1-based)
        self.target_line: Any = (
            self.config.get("target_line")
            or self.config.get("target")
            or self.config.get("line")
            or self.config.get("行号")
            or self.config.get("目标行号")
            or 1
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        cond_expr = str(self.condition).strip() or "1"
        try:
            cond_res = evaluate_expression(cond_expr, context.variables)
        except ExpressionError as e:
            return ActionResult.fail(f"Goto 条件表达式计算失败: {str(e)}")

        if not is_truthy(cond_res):
            ui_delegate.log(f"[Goto] 条件 '{cond_expr}' 结果为 0 (False)，不执行跳转")
            return ActionResult.ok(output="条件为0，跳过跳转", jump_to=None)

        # Parse target line number
        raw_target = str(self.target_line).strip()
        # Render template if needed
        rendered_target = context.render_template(raw_target)
        try:
            target_int = int(float(rendered_target))
        except (ValueError, TypeError):
            return ActionResult.fail(f"Goto 目标行号无效: '{rendered_target}' 不是有效的正整数")

        if target_int < 1:
            return ActionResult.fail(f"Goto 目标行号必须大于等于 1，当前为: {target_int}")

        ui_delegate.log(f"[Goto] 条件 '{cond_expr}' 结果非零，跳转至第 {target_int} 行")
        return ActionResult.ok(output=f"跳转至第 {target_int} 行", jump_to=target_int)
