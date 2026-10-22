"""Built-in action blocks and their reusable configuration validators."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .context import ExecutionContext
from .errors import ActionError, ConfigError, TemplateError, UserCancelledError
from .registry import ActionRegistry
from .templates import parse_path_expression, resolve_path_expression

_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _require_string(action: Mapping[str, Any], key: str, action_name: str) -> str:
    value = action.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{action_name}.{key} 必须是非空字符串")
    return value


def _require_variable(action: Mapping[str, Any], key: str, action_name: str) -> str:
    value = _require_string(action, key, action_name)
    if _VARIABLE.fullmatch(value) is None:
        raise ConfigError(
            f"{action_name}.{key} 必须是字母、数字和下划线组成的变量名，且不能以数字开头"
        )
    return value


def _validate_cell_action(action: Mapping[str, Any], action_name: str) -> None:
    cell = action.get("cell")
    if (
        not isinstance(cell, list)
        or len(cell) != 2
        or any(isinstance(part, bool) or not isinstance(part, int) or part < 0 for part in cell)
    ):
        raise ConfigError(f"{action_name}.cell 必须是非负整数数组 [行, 列]")


def _validate_extract_cell(action: Mapping[str, Any]) -> None:
    _validate_cell_action(action, "extract_cell")
    _require_variable(action, "variable", "extract_cell")


def _validate_http(action: Mapping[str, Any]) -> None:
    method = _require_string(action, "method", "http_request")
    if re.fullmatch(r"[A-Za-z]+", method) is None:
        raise ConfigError("http_request.method 只能包含英文字母")
    _require_string(action, "url", "http_request")
    headers = action.get("headers", {})
    if not isinstance(headers, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()
    ):
        raise ConfigError("http_request.headers 必须是字符串键值组成的 JSON 对象")
    timeout = action.get("timeout_ms", 10000)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError("http_request.timeout_ms 必须是大于 0 的毫秒数")
    callback = action.get("callback", {})
    if not isinstance(callback, Mapping):
        raise ConfigError("http_request.callback 必须是对象，格式为 {变量名: 数据路径}")
    for variable, expression in callback.items():
        if not isinstance(variable, str) or _VARIABLE.fullmatch(variable) is None:
            raise ConfigError(f"http_request.callback 的键 {variable!r} 不是有效变量名")
        if not isinstance(expression, str) or not expression.strip():
            raise ConfigError(f"http_request.callback[{variable!r}] 必须是非空数据路径")
        try:
            parse_path_expression(expression)
        except TemplateError as exc:
            raise ConfigError(str(exc)) from exc


def _validate_user_input(action: Mapping[str, Any]) -> None:
    _require_string(action, "prompt", "user_input")
    _require_variable(action, "variable", "user_input")


def _validate_notify(action: Mapping[str, Any]) -> None:
    _require_string(action, "message", "notify")


def _validate_clipboard_write(action: Mapping[str, Any]) -> None:
    value_type = action.get("type")
    if value_type not in {"text", "table"}:
        raise ConfigError("clipboard_write.type 必须是 text 或 table")
    if "data" not in action:
        raise ConfigError("clipboard_write.data 为必填项")


def _action_extract_cell(action: Mapping[str, Any], context: ExecutionContext) -> None:
    row, column = action["cell"]
    try:
        value = context.table[row][column]
    except IndexError as exc:
        raise ActionError(f"单元格 ({row}, {column}) 超出当前表格范围") from exc
    context.set_variable(action["variable"], value)


def _action_http_request(action: Mapping[str, Any], context: ExecutionContext) -> None:
    method = str(action["method"]).upper()
    url = context.render(action["url"])
    headers = context.render(dict(action.get("headers", {})))
    body = context.render(action.get("body"))
    timeout_ms = action.get("timeout_ms", 10000)
    response = context.http_client.request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        timeout_ms=timeout_ms,
    )
    # ``response`` preserves the exact decoded body. ``res`` is a convenient
    # path root: use a top-level ``res`` object when the server wraps its result
    # that way, otherwise use the body itself. Thus both {"data": [...]} and
    # {"res": {"data": [...]}} support the documented res.data[0] expression.
    context.set_variable("response", response.body)
    response_root = response.body
    if isinstance(response_root, Mapping) and "res" in response_root:
        response_root = response_root["res"]
    context.set_variable("res", response_root)
    context.set_variable("http_status", response.status_code)
    extracted = {
        variable: resolve_path_expression(expression, context.variables)
        for variable, expression in action.get("callback", {}).items()
    }
    for variable, value in extracted.items():
        context.set_variable(variable, value)


def _action_user_input(action: Mapping[str, Any], context: ExecutionContext) -> None:
    prompt = context.render(action["prompt"])
    answer = context.interaction.prompt(str(prompt))
    if answer is None:
        raise UserCancelledError("用户取消了输入，后续步骤已停止")
    context.set_variable(action["variable"], answer)


def _action_notify(action: Mapping[str, Any], context: ExecutionContext) -> None:
    message = context.render(action["message"])
    context.interaction.notify(str(message))


def _as_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ActionError(f"表格单元格无法转换为文本：{exc}") from exc


def _table_from_value(value: Any) -> list[list[Any]]:
    if isinstance(value, str):
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.removesuffix("\n")
        delimiter = "\t" if "\t" in normalized else ","
        try:
            return [list(row) for row in csv.reader(io.StringIO(normalized), delimiter=delimiter)]
        except csv.Error as exc:
            raise ActionError(f"table 数据不是有效的 CSV/TSV：{exc}") from exc
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
        if values and all(
            isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray))
            for row in values
        ):
            return [list(row) for row in values]
        return [values]
    return [[value]]


def _serialize_table(value: Any) -> str:
    table = _table_from_value(value)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerows([_as_cell_text(cell) for cell in row] for row in table)
    return stream.getvalue()


def _action_clipboard_write(action: Mapping[str, Any], context: ExecutionContext) -> None:
    data = context.render(action["data"])
    if action["type"] == "text":
        text = _as_cell_text(data)
    else:
        text = _serialize_table(data)
    context.clipboard.write_text(text)


def build_default_registry() -> ActionRegistry:
    """Create the built-in registry; plug-ins can register more actions later."""
    registry = ActionRegistry()
    registry.register(
        "extract_cell",
        _action_extract_cell,
        label="提取单元格",
        validator=_validate_extract_cell,
        form_schema={"cell": "cell", "variable": "string"},
    )
    registry.register(
        "http_request",
        _action_http_request,
        label="发送 HTTP 请求",
        validator=_validate_http,
        form_schema={
            "method": "string",
            "url": "template",
            "headers": "json-object",
            "body": "json-or-template",
            "timeout_ms": "number",
            "callback": "variable-path-map",
        },
    )
    registry.register(
        "user_input",
        _action_user_input,
        label="用户输入",
        validator=_validate_user_input,
        form_schema={"prompt": "template", "variable": "string"},
    )
    registry.register(
        "notify",
        _action_notify,
        label="弹出提示",
        validator=_validate_notify,
        form_schema={"message": "template"},
    )
    registry.register(
        "clipboard_write",
        _action_clipboard_write,
        label="写入剪切板",
        validator=_validate_clipboard_write,
        form_schema={"type": ["text", "table"], "data": "template-or-json"},
    )
    return registry
