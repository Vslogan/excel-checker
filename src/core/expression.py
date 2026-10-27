"""
Expression evaluator for Turing-complete Compute, If-Else, and Goto blocks.

Supports:
- Ternary conditional operator: condition ? true_expr : false_expr (with short-circuiting)
- Arithmetic: +, -, *, /, % (auto cast string to number, max 6 decimal places, error on fail)
- Logic operators: && (and), || (or), ! (not)
- Comparisons: ==, !=, <, <=, >, >=
- Parentheses grouping: (...)
- Built-in functions: str, substr, strcat, round, ceil, floor
- Logical results are strictly non-zero ("1") or zero ("0"), never "true"/"false".
- Variable validation: must start with letter or underscore, alphanumeric + underscore only.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple


class ExpressionError(Exception):
    """Base exception for expression evaluation failures."""
    pass


VAR_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

ESCAPE_MAP = {
    "t": "\t",
    "n": "\n",
    "r": "\r",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
}


def decode_escape_sequences(s: str) -> str:
    """Decode escape sequences (e.g. \\t, \\n, \\r, \\\\, \\\", \\\') into actual characters."""
    if not isinstance(s, str) or "\\" not in s:
        return s

    def replace(match: re.Match) -> str:
        esc = match.group(1)
        if esc in ESCAPE_MAP:
            return ESCAPE_MAP[esc]
        if esc.startswith("u") and len(esc) == 5 and all(c in "0123456789abcdefABCDEF" for c in esc[1:]):
            try:
                return chr(int(esc[1:], 16))
            except ValueError:
                return match.group(0)
        if esc.startswith("x") and len(esc) == 3 and all(c in "0123456789abcdefABCDEF" for c in esc[1:]):
            try:
                return chr(int(esc[1:], 16))
            except ValueError:
                return match.group(0)
        return match.group(0)

    pattern = re.compile(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", re.DOTALL)
    return pattern.sub(replace, s)


def validate_variable_name(name: str) -> bool:
    """
    Validate that variable name matches common identifier rules:
    Must start with an underscore or letter, and can contain alphanumeric characters and underscores.
    """
    if not name or not isinstance(name, str):
        return False
    return bool(VAR_NAME_PATTERN.match(name.strip()))


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
    """Convert value to float. Raises ExpressionError on failure."""
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


class ExprParser:
    """
    Recursive descent parser for arithmetic, logic, built-in functions,
    and C-style ternary operators (cond ? true_expr : false_expr).
    """

    def __init__(self, text: str, variables: Optional[Dict[str, Any]] = None):
        self.raw_text = text or ""
        self.vars = dict(variables or {})

        # Pre-render {{var}} templates if present (using safe lambda to avoid regex escape group mangling)
        processed = self.raw_text
        for k, v in self.vars.items():
            pattern = r"\{\{\s*" + re.escape(k) + r"\s*\}\}"
            processed = re.sub(pattern, lambda m, val=str(v): val, processed)

        self.tokens = self._tokenize(processed)
        self.pos = 0

    def _tokenize(self, s: str) -> List[Tuple[str, Any]]:
        tokens: List[Tuple[str, Any]] = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch in " \t\r\n":
                i += 1
                continue

            # String literal (supports escape sequences: \t, \n, \r, \\, \", \', \0, \a, \b, \f, \v, \uXXXX, \xXX)
            if ch in ('"', "'"):
                quote = ch
                i += 1
                val_buf: List[str] = []
                while i < n and s[i] != quote:
                    if s[i] == "\\" and i + 1 < n:
                        next_ch = s[i + 1]
                        if next_ch in ESCAPE_MAP:
                            val_buf.append(ESCAPE_MAP[next_ch])
                            i += 2
                        elif next_ch == "u" and i + 5 < n and all(c in "0123456789abcdefABCDEF" for c in s[i + 2 : i + 6]):
                            val_buf.append(chr(int(s[i + 2 : i + 6], 16)))
                            i += 6
                        elif next_ch == "x" and i + 3 < n and all(c in "0123456789abcdefABCDEF" for c in s[i + 2 : i + 4]):
                            val_buf.append(chr(int(s[i + 2 : i + 4], 16)))
                            i += 4
                        else:
                            val_buf.append(next_ch)
                            i += 2
                    else:
                        val_buf.append(s[i])
                        i += 1
                i += 1  # Skip closing quote
                tokens.append(("STR", "".join(val_buf)))
                continue

            # Two-character operators
            if i + 1 < n and s[i:i + 2] in ("==", "!=", "<=", ">=", "&&", "||"):
                tokens.append(("OP", s[i:i + 2]))
                i += 2
                continue

            # Single-character operators and punctuation
            if ch in "?:+-*/%(),!<>":
                tokens.append(("OP", ch))
                i += 1
                continue

            # Numbers (integers or floats)
            if ch.isdigit() or (ch == "." and i + 1 < n and s[i + 1].isdigit()):
                start = i
                has_dot = (ch == ".")
                i += 1
                while i < n and (s[i].isdigit() or (s[i] == "." and not has_dot)):
                    if s[i] == ".":
                        has_dot = True
                    i += 1
                tokens.append(("NUM", float(s[start:i])))
                continue

            # Identifiers (variable names, keywords, function names)
            if ch.isalpha() or ch == "_":
                start = i
                while i < n and (s[i].isalnum() or s[i] == "_"):
                    i += 1
                name = s[start:i]
                lower_name = name.lower()
                if lower_name == "and":
                    tokens.append(("OP", "&&"))
                elif lower_name == "or":
                    tokens.append(("OP", "||"))
                elif lower_name == "not":
                    tokens.append(("OP", "!"))
                else:
                    tokens.append(("ID", name))
                continue

            raise ExpressionError(f"表达式中含有非法字符: '{ch}'")

        tokens.append(("EOF", ""))
        return tokens

    def peek(self) -> Tuple[str, Any]:
        return self.tokens[self.pos]

    def consume(self) -> Tuple[str, Any]:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def match(self, op_val: str) -> bool:
        if self.peek()[0] == "OP" and self.peek()[1] == op_val:
            self.pos += 1
            return True
        return False

    def expect(self, op_val: str) -> None:
        if not self.match(op_val):
            found = self.peek()[1] or self.peek()[0]
            raise ExpressionError(f"语法错误: 预期符号 '{op_val}'，但找到 '{found}'")

    def parse(self) -> str:
        if self.peek()[0] == "EOF":
            return ""
        res = self.parse_expr(evaluating=True)
        if self.peek()[0] != "EOF":
            raise ExpressionError(f"语法错误: 未解析的冗余后缀 '{self.peek()[1]}'")
        return res

    def parse_expr(self, evaluating: bool = True) -> str:
        return self.parse_ternary(evaluating=evaluating)

    def parse_ternary(self, evaluating: bool = True) -> str:
        cond = self.parse_or(evaluating=evaluating)
        if self.match("?"):
            cond_true = is_truthy(cond) if evaluating else False
            # Short-circuiting: only evaluate the active branch
            true_val = self.parse_expr(evaluating=(evaluating and cond_true))
            self.expect(":")
            false_val = self.parse_ternary(evaluating=(evaluating and not cond_true))
            return true_val if cond_true else false_val
        return cond

    def parse_or(self, evaluating: bool = True) -> str:
        left = self.parse_and(evaluating=evaluating)
        while self.match("||"):
            left_true = is_truthy(left) if evaluating else False
            # Short-circuiting OR
            right = self.parse_and(evaluating=(evaluating and not left_true))
            if evaluating:
                left = "1" if (left_true or is_truthy(right)) else "0"
        return left

    def parse_and(self, evaluating: bool = True) -> str:
        left = self.parse_not(evaluating=evaluating)
        while self.match("&&"):
            left_true = is_truthy(left) if evaluating else False
            # Short-circuiting AND
            right = self.parse_not(evaluating=(evaluating and left_true))
            if evaluating:
                left = "1" if (left_true and is_truthy(right)) else "0"
        return left

    def parse_not(self, evaluating: bool = True) -> str:
        if self.match("!"):
            val = self.parse_not(evaluating=evaluating)
            if evaluating:
                return "0" if is_truthy(val) else "1"
            return "0"
        return self.parse_comparison(evaluating=evaluating)

    def parse_comparison(self, evaluating: bool = True) -> str:
        left = self.parse_arith(evaluating=evaluating)
        if self.peek()[0] == "OP" and self.peek()[1] in ("==", "!=", "<", "<=", ">", ">="):
            op = self.consume()[1]
            right = self.parse_arith(evaluating=evaluating)
            if not evaluating:
                return "0"

            is_both_num = self._is_num(left) and self._is_num(right)
            if op == "==":
                matched = (to_number(left) == to_number(right)) if is_both_num else (str(left) == str(right))
                return "1" if matched else "0"
            elif op == "!=":
                matched = (to_number(left) == to_number(right)) if is_both_num else (str(left) == str(right))
                return "0" if matched else "1"
            else:
                num_l = to_number(left)
                num_r = to_number(right)
                if op == "<":
                    return "1" if num_l < num_r else "0"
                elif op == "<=":
                    return "1" if num_l <= num_r else "0"
                elif op == ">":
                    return "1" if num_l > num_r else "0"
                elif op == ">=":
                    return "1" if num_l >= num_r else "0"
        return left

    def _is_num(self, val: Any) -> bool:
        try:
            float(val)
            return True
        except (ValueError, TypeError):
            return False

    def parse_arith(self, evaluating: bool = True) -> str:
        left = self.parse_term(evaluating=evaluating)
        while self.peek()[0] == "OP" and self.peek()[1] in ("+", "-"):
            op = self.consume()[1]
            right = self.parse_term(evaluating=evaluating)
            if evaluating:
                nl = to_number(left)
                nr = to_number(right)
                res = (nl + nr) if op == "+" else (nl - nr)
                left = format_number(res)
        return left

    def parse_term(self, evaluating: bool = True) -> str:
        left = self.parse_factor(evaluating=evaluating)
        while self.peek()[0] == "OP" and self.peek()[1] in ("*", "/", "%"):
            op = self.consume()[1]
            right = self.parse_factor(evaluating=evaluating)
            if evaluating:
                nl = to_number(left)
                nr = to_number(right)
                if op == "*":
                    res = nl * nr
                elif op == "/":
                    if nr == 0:
                        raise ExpressionError("除法运算错误: 除数不能为 0")
                    res = nl / nr
                elif op == "%":
                    if nr == 0:
                        raise ExpressionError("取模运算错误: 除数不能为 0")
                    res = nl % nr
                left = format_number(res)
        return left

    def parse_factor(self, evaluating: bool = True) -> str:
        if self.match("+"):
            val = self.parse_factor(evaluating=evaluating)
            return format_number(to_number(val)) if evaluating else "0"
        if self.match("-"):
            val = self.parse_factor(evaluating=evaluating)
            return format_number(-to_number(val)) if evaluating else "0"
        return self.parse_atom(evaluating=evaluating)

    def parse_atom(self, evaluating: bool = True) -> str:
        t, val = self.peek()
        if t == "NUM":
            self.consume()
            return format_number(val) if evaluating else "0"

        if t == "STR":
            self.consume()
            return str(val) if evaluating else ""

        if t == "ID":
            name = self.consume()[1]
            if self.match("("):
                # Function call
                args: List[str] = []
                if not self.match(")"):
                    while True:
                        args.append(self.parse_expr(evaluating=evaluating))
                        if self.match(","):
                            continue
                        if self.match(")"):
                            break
                        raise ExpressionError(f"函数 '{name}' 参数列表语法错误")
                if evaluating:
                    return self._call_builtin(name, args)
                return ""
            else:
                # Variable lookup
                if not evaluating:
                    return ""
                if name in self.vars:
                    return str(self.vars[name])
                raise ExpressionError(f"未定义的变量: '{name}'")

        if self.match("("):
            res = self.parse_expr(evaluating=evaluating)
            self.expect(")")
            return res

        raise ExpressionError(f"无法解析的表达式元素: '{val}'")

    def _call_builtin(self, name: str, args: List[str]) -> str:
        fn = name.lower()
        if fn == "str":
            return str(args[0]) if args else ""
        elif fn == "substr":
            s = str(args[0]) if len(args) > 0 else ""
            try:
                start = int(float(args[1])) if len(args) > 1 else 0
            except Exception:
                start = 0
            if len(args) > 2:
                try:
                    length = int(float(args[2]))
                    return s[start:start + length] if length >= 0 else ""
                except Exception:
                    return s[start:]
            return s[start:]
        elif fn == "strcat":
            return "".join(str(a) for a in args)
        elif fn == "round":
            if not args:
                return "0"
            num = to_number(args[0])
            try:
                dec = int(float(args[1])) if len(args) > 1 else 0
            except Exception:
                dec = 0
            r = round(num, dec)
            if dec <= 0 and r == int(r):
                return str(int(r))
            if dec > 0:
                return f"{r:.{dec}f}"
            return str(r)
        elif fn == "ceil":
            if not args:
                return "0"
            return str(int(math.ceil(to_number(args[0]))))
        elif fn == "floor":
            if not args:
                return "0"
            return str(int(math.floor(to_number(args[0]))))
        raise ExpressionError(f"未知的内置函数: '{name}'")


def evaluate_expression(expr: str, variables: Optional[Dict[str, Any]] = None) -> str:
    """
    Evaluate an expression with context variables.
    Supports C-style ternary operators, arithmetic, comparisons, logic, and functions.
    Logical/comparison results are strictly '1' or '0'.
    """
    if expr is None:
        return ""
    raw = str(expr).strip()
    if not raw:
        return ""

    parser = ExprParser(raw, variables or {})
    return parser.parse()
