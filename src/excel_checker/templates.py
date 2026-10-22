"""Safe variable interpolation and response-path resolution."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import TemplateError

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _template_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TemplateError(f"变量值无法转换为文本：{type(value).__name__}") from exc


def render_templates(value: Any, variables: Mapping[str, Any]) -> Any:
    """Recursively render ``{{variable}}`` placeholders in JSON values."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in variables:
                raise TemplateError(f"模板引用了尚未定义的变量：{name}")
            return _template_value(variables[name])

        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, list):
        return [render_templates(item, variables) for item in value]
    if isinstance(value, tuple):
        return tuple(render_templates(item, variables) for item in value)
    if isinstance(value, Mapping):
        return {key: render_templates(item, variables) for key, item in value.items()}
    return value


def parse_path_expression(expression: str) -> list[str | int]:
    """Parse a restricted path such as ``res.data[0]`` without using eval."""
    source = expression.strip()
    match = _IDENTIFIER.match(source)
    if match is None:
        raise TemplateError(f"无效的数据提取路径：{expression!r}")

    parts: list[str | int] = [match.group(0)]
    position = match.end()
    while position < len(source):
        if source[position] == ".":
            match = _IDENTIFIER.match(source, position + 1)
            if match is None:
                raise TemplateError(f"无效的数据提取路径：{expression!r}")
            parts.append(match.group(0))
            position = match.end()
            continue

        if source[position] == "[":
            closing = source.find("]", position + 1)
            if closing == -1:
                raise TemplateError(f"无效的数据提取路径：{expression!r}")
            item = source[position + 1 : closing].strip()
            if item.isdecimal():
                parts.append(int(item))
            elif len(item) >= 2 and item[0] == item[-1] and item[0] in ("'", '"'):
                parts.append(item[1:-1])
            else:
                raise TemplateError(f"无效的数据提取路径：{expression!r}")
            position = closing + 1
            continue

        raise TemplateError(f"无效的数据提取路径：{expression!r}")

    return parts


def resolve_path_expression(expression: str, variables: Mapping[str, Any]) -> Any:
    """Resolve a dot/bracket path against variables, with no attribute access."""
    parts = parse_path_expression(expression)
    root_name = parts[0]
    if not isinstance(root_name, str) or root_name not in variables:
        raise TemplateError(f"路径引用了尚未定义的变量：{root_name}")

    current: Any = variables[root_name]
    for part in parts[1:]:
        if isinstance(part, int):
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes, bytearray)):
                raise TemplateError(f"{part} 不能用于索引 {type(current).__name__}")
            try:
                current = current[part]
            except IndexError as exc:
                raise TemplateError(f"数组索引越界：{part}") from exc
        else:
            if not isinstance(current, Mapping):
                raise TemplateError(f"{part!r} 不能用于访问 {type(current).__name__}")
            if part not in current:
                raise TemplateError(f"返回数据中不存在字段：{part}")
            current = current[part]
    return current
