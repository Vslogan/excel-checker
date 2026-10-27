"""Execution context and variable management.

Provides variable storage, template string interpolation (e.g. {{var}}),
safe JSON path extraction, and UI delegation.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Protocol, Union

from src.core.expression import validate_variable_name


class UIDelegate(Protocol):
    """Protocol for UI interactions during workflow execution."""

    def prompt_user(self, prompt: str, default: str = "") -> Optional[str]:
        ...

    def show_message(self, title: str, message: str) -> None:
        ...

    def show_toast(
        self,
        content: str,
        duration_ms: int = 2000,
        blocking: bool = False,
        screen: str = "cursor",
        position: str = "bottom_center",
    ) -> None:
        ...

    def set_clipboard(self, content: str) -> None:
        ...

    def get_clipboard(self) -> str:
        ...

    def log(self, message: str) -> None:
        ...


class HeadlessUIDelegate:
    """Default headless implementation useful for testing and background tasks."""

    def __init__(self, predefined_inputs: Optional[Dict[str, str]] = None):
        self.predefined_inputs = predefined_inputs or {}
        self.messages: List[Dict[str, str]] = []
        self.toasts: List[Dict[str, Any]] = []
        self.clipboard_data: str = ""
        self.logs: List[str] = []

    def prompt_user(self, prompt: str, default: str = "") -> Optional[str]:
        val = self.predefined_inputs.get(prompt, default)
        self.log(f"[UI Input] Prompt '{prompt}' -> '{val}'")
        return val

    def show_message(self, title: str, message: str) -> None:
        self.messages.append({"title": title, "message": message})
        self.log(f"[UI Message] [{title}] {message}")

    def show_toast(
        self,
        content: str,
        duration_ms: int = 2000,
        blocking: bool = False,
        screen: str = "cursor",
        position: str = "bottom_center",
    ) -> None:
        self.toasts.append({
            "content": content,
            "duration_ms": duration_ms,
            "blocking": blocking,
            "screen": screen,
            "position": position,
        })
        self.log(f"[UI Toast] [{position} on {screen}] {content} (duration={duration_ms}ms, blocking={blocking})")

    def set_clipboard(self, content: str) -> None:
        self.clipboard_data = content
        self.log(f"[UI Clipboard Set] {content[:50]}..." if len(content) > 50 else f"[UI Clipboard Set] {content}")

    def get_clipboard(self) -> str:
        return self.clipboard_data

    def log(self, message: str) -> None:
        self.logs.append(message)


def extract_path_value(data: Any, path: str) -> Any:
    """Extract a value from nested dicts/lists using dot & bracket notation.

    Examples:
        res.data[0]
        data[0].id
        users[1].name
        [0].title
    """
    if not path:
        return data

    tokens = []
    # Tokenize: supports dots and brackets, e.g. res.data[0][1].name
    pattern = re.compile(r'([^.\[\]]+)|\[(\d+)\]|\["([^"]+)"\]|\'([^\']+)\'')
    for match in pattern.finditer(path):
        key = match.group(1) or match.group(3) or match.group(4)
        idx = match.group(2)
        if key is not None:
            tokens.append(key)
        elif idx is not None:
            tokens.append(int(idx))

    # Helper function to traverse tokens
    def _traverse(cur: Any, token_list: List[Union[str, int]]) -> Any:
        for t in token_list:
            if isinstance(t, int):
                if isinstance(cur, (list, tuple)) and 0 <= t < len(cur):
                    cur = cur[t]
                else:
                    return None
            else:
                if isinstance(cur, dict):
                    if t in cur:
                        cur = cur[t]
                    elif t.isdigit() and int(t) in cur:
                        cur = cur[int(t)]
                    else:
                        return None
                elif isinstance(cur, (list, tuple)) and t.isdigit():
                    idx = int(t)
                    if 0 <= idx < len(cur):
                        cur = cur[idx]
                    else:
                        return None
                else:
                    return None
        return cur

    # If first token is 'res' or 'response' and not in data directly, try stripping it
    res = _traverse(data, tokens)
    if res is not None:
        return res

    if tokens and tokens[0] in ("res", "response") and isinstance(data, dict) and tokens[0] not in data:
        res_stripped = _traverse(data, tokens[1:])
        if res_stripped is not None:
            return res_stripped

    return None


class ExecutionContext:
    """Execution context for workflow execution."""

    def __init__(self, table_data: Optional[Any] = None, initial_vars: Optional[Dict[str, Any]] = None):
        self.table_data = table_data
        self.variables: Dict[str, Any] = {}
        if table_data is not None and hasattr(table_data, "rows") and hasattr(table_data, "cols"):
            self.set_var("row", str(table_data.rows))
            self.set_var("column", str(table_data.cols))
            self.set_var("colunm", str(table_data.cols))  # alias for common spelling typo
            self.set_var("rows", str(table_data.rows))
            self.set_var("cols", str(table_data.cols))
        if initial_vars:
            for k, v in initial_vars.items():
                self.set_var(k, v)
        self.logs: List[str] = []
        self.current_step: int = 1
        self.total_steps: int = 1

    def set_var(self, name: str, value: Any) -> None:
        """Set a variable in global scope with naming rule validation."""
        clean_name = str(name).strip() if name is not None else ""
        if not validate_variable_name(clean_name):
            raise ValueError(
                f"无效的变量名 '{name}': 变量名必须以字母或下划线开头，且只能包含字母、数字或下划线"
            )
        self.variables[clean_name] = value

    def get_var(self, name: str, default: Any = None) -> Any:
        return self.variables.get(name, default)

    def log(self, message: str) -> None:
        self.logs.append(message)

    def render_template(self, template: Any) -> Any:
        """Render {{variable}} expressions recursively in strings, dicts, and lists."""
        if isinstance(template, str):
            def replacer(match: re.Match) -> str:
                var_path = match.group(1).strip()
                # Check direct variable first
                if var_path in self.variables:
                    val = self.variables[var_path]
                    if isinstance(val, (dict, list)):
                        return json.dumps(val, ensure_ascii=False)
                    return str(val)
                # Check dot path in context
                val = extract_path_value(self.variables, var_path)
                if val is not None:
                    if isinstance(val, (dict, list)):
                        return json.dumps(val, ensure_ascii=False)
                    return str(val)
                return match.group(0)  # Keep original if not found

            return re.sub(r'\{\{\s*([^{}]+?)\s*\}\}', replacer, template)

        if isinstance(template, dict):
            return {
                self.render_template(k): self.render_template(v)
                for k, v in template.items()
            }

        if isinstance(template, list):
            return [self.render_template(item) for item in template]

        return template
