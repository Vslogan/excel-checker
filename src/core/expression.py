"""
Expression evaluator for Turing-complete Compute, If-Else, and Goto blocks.

Supports:
- Arithmetic: +, -, *, /, % (auto cast string to number, max 6 decimal places, error on fail)
- Logic operators: && (and), || (or), ! (not)
- Comparisons: ==, !=, <, <=, >, >=
- Parentheses grouping: (...)
- Built-in functions: str, substr, strcat, round, ceil, floor
- Logical results are strictly non-zero ("1") or zero ("0"), never "true"/"false".
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any, Callable, Dict, List, Optional


class ExpressionError(Exception):
    """Base exception for expression evaluation failures."""
    pass


def format_number(val: float) -> str:
    """Format number with default max 6 non-zero decimal digits."""
    if math.isnan(val) or math.isinf(val):
        return str(val)
    r = round(val, 6)
    if r == int(r):
        return str(int(r))
    # Keep up to 6 decimals and strip trailing zeros
    s = f"{r:.6f}".rstrip("0").rstrip(".")
    return s


def to_number(val: Any) -> float:
    """Convert value to float. Raises ValueError on failure."""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        raise ExpressionError(f"四则运算操作数转换失败: 无法将 '{val}' 转换为数字进行运算")


def is_truthy(val: Any) -> bool:
    """Non-zero or non-empty string is truthy (1), 0 or empty is falsy (0)."""
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip()
    if s == "" or s == "0" or s.lower() == "false":
        return False
    try:
        num = float(s)
        return num != 0
    except ValueError:
        return True


# Built-in functions available in expressions
def fn_str(x: Any) -> str:
    if isinstance(x, (int, float)):
        return format_number(x)
    return str(x)


def fn_substr(s: Any, start: Any, length: Any = None) -> str:
    s_str = fn_str(s)
    try:
        start_idx = int(float(str(start)))
    except Exception:
        start_idx = 0

    if length is None:
        return s_str[start_idx:]
    try:
        len_val = int(float(str(length)))
        if len_val < 0:
            return ""
        return s_str[start_idx:start_idx + len_val]
    except Exception:
        return s_str[start_idx:]


def fn_strcat(*args: Any) -> str:
    return "".join(fn_str(a) for a in args)


def fn_round(x: Any, decimals: Any = 0) -> str:
    num = to_number(x)
    try:
        dec = int(float(str(decimals)))
    except Exception:
        dec = 0
    r = round(num, dec)
    if dec <= 0 and r == int(r):
        return str(int(r))
    if dec > 0:
        s = f"{r:.{dec}f}"
        return s
    return str(r)


def fn_ceil(x: Any) -> str:
    num = to_number(x)
    return str(int(math.ceil(num)))


def fn_floor(x: Any) -> str:
    num = to_number(x)
    return str(int(math.floor(num)))


BUILTIN_FUNCS: Dict[str, Callable[..., Any]] = {
    "str": fn_str,
    "substr": fn_substr,
    "strcat": fn_strcat,
    "round": fn_round,
    "ceil": fn_ceil,
    "floor": fn_floor,
}


class ASTEvaluator(ast.NodeVisitor):
    """Safe AST visitor to evaluate expressions."""

    def __init__(self, variables: Dict[str, Any]):
        self.variables = variables

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    # Compatibility for Python < 3.8
    def visit_Num(self, node: Any) -> Any:
        return node.n

    def visit_Str(self, node: Any) -> Any:
        return node.s

    def visit_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name in BUILTIN_FUNCS:
            return BUILTIN_FUNCS[name]
        if name in self.variables:
            return self.variables[name]
        # Treat unknown identifiers as literal string or error
        raise ExpressionError(f"未定义的变量: '{name}'")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return to_number(operand)
        elif isinstance(node.op, ast.USub):
            return -to_number(operand)
        elif isinstance(node.op, ast.Not):
            # Logical result: 1 or 0
            return "0" if is_truthy(operand) else "1"
        raise ExpressionError(f"不支持的一元运算符: {type(node.op).__name__}")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)

        num_left = to_number(left)
        num_right = to_number(right)

        if isinstance(node.op, ast.Add):
            res = num_left + num_right
        elif isinstance(node.op, ast.Sub):
            res = num_left - num_right
        elif isinstance(node.op, ast.Mult):
            res = num_left * num_right
        elif isinstance(node.op, ast.Div):
            if num_right == 0:
                raise ExpressionError("除法运算错误: 除数不能为 0")
            res = num_left / num_right
        elif isinstance(node.op, ast.Mod):
            if num_right == 0:
                raise ExpressionError("取模运算错误: 除数不能为 0")
            res = num_left % num_right
        else:
            raise ExpressionError(f"不支持的算术运算符: {type(node.op).__name__}")

        return format_number(res)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        # Logical operators: and, or
        if isinstance(node.op, ast.And):
            for val_node in node.values:
                val = self.visit(val_node)
                if not is_truthy(val):
                    return "0"
            return "1"
        elif isinstance(node.op, ast.Or):
            for val_node in node.values:
                val = self.visit(val_node)
                if is_truthy(val):
                    return "1"
            return "0"
        raise ExpressionError(f"不支持的逻辑运算符: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comparator_node in zip(node.ops, node.comparators):
            right = self.visit(comparator_node)
            matched = self._eval_comparison(op, left, right)
            if not matched:
                return "0"
            left = right
        return "1"

    def _eval_comparison(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        # Check equality/inequality
        if isinstance(op, ast.Eq):
            return self._are_equal(left, right)
        elif isinstance(op, ast.NotEq):
            return not self._are_equal(left, right)

        # Numerical comparisons: <, <=, >, >=
        num_l = to_number(left)
        num_r = to_number(right)

        if isinstance(op, ast.Lt):
            return num_l < num_r
        elif isinstance(op, ast.LtE):
            return num_l <= num_r
        elif isinstance(op, ast.Gt):
            return num_l > num_r
        elif isinstance(op, ast.GtE):
            return num_l >= num_r
        else:
            raise ExpressionError(f"不支持的比较运算符: {type(op).__name__}")

    def _are_equal(self, a: Any, b: Any) -> bool:
        # Try numerical equality first if both convert to numbers cleanly
        try:
            return float(a) == float(b)
        except (ValueError, TypeError):
            return str(a) == str(b)

    def visit_Call(self, node: ast.Call) -> Any:
        func = self.visit(node.func)
        if not callable(func):
            raise ExpressionError(f"'{getattr(node.func, 'id', str(func))}' 不是可调用的内置函数")
        args = [self.visit(arg) for arg in node.args]
        return func(*args)

    def generic_visit(self, node: ast.AST) -> Any:
        raise ExpressionError(f"表达式中含有不支持的语法元素: {type(node).__name__}")


def evaluate_expression(expr: str, variables: Optional[Dict[str, Any]] = None) -> str:
    """
    Evaluate an expression with context variables.
    Returns the string result. Logical/comparison results are strictly '1' or '0'.
    """
    if expr is None:
        return ""
    raw = str(expr).strip()
    if not raw:
        return ""

    vars_dict = dict(variables or {})

    # Pre-render {{var}} if present
    for k, v in vars_dict.items():
        pattern = r"\{\{\s*" + re.escape(k) + r"\s*\}\}"
        # If the variable value is a string, wrap in quotes if inside non-numeric context?
        # Actually replace directly with string representation
        raw = re.sub(pattern, str(v), raw)

    # Normalize logic operators: && -> and, || -> or, ! -> not
    normalized = re.sub(r"&&", " and ", raw)
    normalized = re.sub(r"\|\|", " or ", normalized)
    normalized = re.sub(r"!(?!=)", " not ", normalized)
    normalized = normalized.strip()

    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"表达式语法错误: '{raw}' ({e.msg})")

    evaluator = ASTEvaluator(vars_dict)
    res = evaluator.visit(tree)

    # Ensure result is string
    if isinstance(res, (int, float)):
        return format_number(res)
    return str(res)
