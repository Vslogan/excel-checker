"""
Compute action block.
Evaluates complex right-value expressions and stores the result into a left-value variable.
"""

from typing import Any, Dict
from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import evaluate_expression, ExpressionError, validate_variable_name


class ComputeAction(BaseAction):
    """
    Compute action: evaluates arithmetic, logic, comparison, and built-in functions,
    assigning the string result to the target left-value variable.
    """

    action_type = "compute"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Left-value variable name
        self.target_var: str = (
            self.config.get("target_var")
            or self.config.get("variable")
            or self.config.get("var")
            or self.config.get("左值")
            or self.config.get("左值变量名")
            or self.config.get("变量名")
            or "result"
        )
        # Right-value expression
        self.expression: str = (
            self.config.get("expression")
            or self.config.get("expr")
            or self.config.get("右值")
            or self.config.get("复杂的右值")
            or self.config.get("表达式")
            or self.config.get("计算表达式")
            or ""
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        if not self.target_var or not self.target_var.strip():
            return ActionResult(success=False, error="计算积木未指定左值变量名")
        var_name = self.target_var.strip()
        if not validate_variable_name(var_name):
            return ActionResult(
                success=False,
                error=f"左值变量名 '{var_name}' 不合法: 必须以下划线或字母开头，只能包含字母、数字和下划线",
            )
        if not self.expression or not self.expression.strip():
            return ActionResult(success=False, error="计算积木未指定右值表达式")
        try:
            # Pass all context variables to expression evaluator
            result_str = evaluate_expression(self.expression, context.variables)
            context.set_var(var_name, result_str)
            msg = f"计算完成: {var_name} = {result_str} (表达式: '{self.expression}')"
            ui_delegate.log(f"[Compute] {msg}")
            return ActionResult(success=True, output=result_str)
        except ExpressionError as e:
            err = f"计算失败: {str(e)}"
            ui_delegate.log(f"[Compute Error] {err}")
            return ActionResult(success=False, error=err)
        except Exception as e:
            err = f"计算发生未捕获异常: {str(e)}"
            ui_delegate.log(f"[Compute Exception] {err}")
            return ActionResult(success=False, error=err)
