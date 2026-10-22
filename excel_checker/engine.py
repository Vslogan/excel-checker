"""规则执行引擎：按顺序执行动作步骤，维护变量上下文，动作可插拔扩展。

设计要点：
- 所有动作都在一个上下文（ExecutionContext）里执行，变量可在步骤间共享。
- 网络请求为同步阻塞，超时抛出 EngineError。
- 需要人机交互的动作（user_input/alert）通过回调完成，GUI 接入时再替换为真实弹窗；
  纯头less 运行时可用于自动化测试。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from .config import ConfigError, RuleConfig, substitute_in_value, substitute_template


class EngineError(Exception):
    """引擎执行错误（超时、请求失败、参数不合法等）。"""


class StepSkip(Exception):
    """本次剪贴板数据不满足触发条件，忽略本次。"""


# 微型 JSON 路径，支持 res.data[0] / data[0] / res 这种风格，供 http_request callback 使用。
_JSON_PATH_TOKEN_RE = re.compile(r"[^.\[\]]+")


@dataclass
class ExecutionContext:
    """一次规则执行的上下文：变量表、来源表格、最后一次响应、日志。"""

    variables: dict[str, Any] = field(default_factory=dict)
    table: list[list[str]] = field(default_factory=list)
    last_response: str | None = None
    last_response_json: Any = None
    logs: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.logs.append(msg)


def extract_json_path(root: Any, expr: str) -> Any:
    """按点/下标路径从 JSON 对象中提取值。

    例如 root={"res": {"data": ["test", ...]}}，expr="res.data[0]" -> "test"。
    """
    current: Any = root
    for token in _JSON_PATH_TOKEN_RE.findall(expr):
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (IndexError, ValueError) as exc:
                raise EngineError(f"无法从路径 {expr!r} 提取索引 {token!r}") from exc
        elif isinstance(current, dict):
            if token not in current:
                raise EngineError(f"路径 {expr!r} 中不存在键 {token!r}")
            current = current[token]
        else:
            raise EngineError(f"路径 {expr!r} 在 {token!r} 处命中非容器类型")
    return current


# 回调类型：GUI 接入后用真实弹窗实现。
InputCallback = Callable[[str], str]
AlertCallback = Callable[[str], None]
LogCallback = Callable[[str], None]


class Engine:
    def __init__(
        self,
        on_input: InputCallback | None = None,
        on_alert: AlertCallback | None = None,
        on_log: LogCallback | None = None,
        request_timeout_default: float = 30.0,
    ) -> None:
        self.on_input = on_input
        self.on_alert = on_alert
        self.on_log = on_log
        self.request_timeout_default = request_timeout_default

    # ------------------------------------------------------------------ public

    def run(self, rule: RuleConfig, table: list[list[str]]) -> ExecutionContext:
        """按顺序执行规则的全部步骤；任一步骤失败抛出 EngineError。"""
        ctx = ExecutionContext(table=table)
        ctx.log(f"开始执行规则: {rule.name}")
        for index, step in enumerate(rule.steps):
            action = step.get("action")
            ctx.log(f"步骤 {index}: {action}")
            self._execute_step(action, step, ctx)
        ctx.log("规则执行完成")
        return ctx

    # ------------------------------------------------------------------ internals

    def _execute_step(self, action: str, step: dict[str, Any], ctx: ExecutionContext) -> None:
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            raise EngineError(f"不支持的动作: {action}")
        handler(step, ctx)

    # --- 具体动作实现 ---

    def _do_extract_cell(self, step: dict[str, Any], ctx: ExecutionContext) -> None:
        """提取某一格并暂存到变量。"""
        cell = step.get("cell")
        variable = step.get("variable")
        if not isinstance(variable, str) or not variable:
            raise EngineError("extract_cell 缺少 variable")
        if not (isinstance(cell, list) and len(cell) == 2):
            raise EngineError("extract_cell 缺少合法的 cell（[行, 列]）")
        r, c = int(cell[0]), int(cell[1])
        if r < 0 or r >= len(ctx.table) or c < 0 or c >= len(ctx.table[r]):
            raise EngineError(
                f"单元格 ({r},{c}) 超出表格范围（{len(ctx.table)}x"
                f"{max(len(row) for row in ctx.table) if ctx.table else 0}）"
            )
        value = ctx.table[r][c]
        ctx.variables[variable] = value
        ctx.log(f"提取单元格 ({r},{c}) = {value!r} -> {variable}")

    def _do_http_request(self, step: dict[str, Any], ctx: ExecutionContext) -> None:
        """发送网络请求，同步等待返回；timeout 超时抛出 EngineError。"""
        method = str(step.get("method", "GET")).upper()
        url = substitute_template(str(step.get("url", "")), ctx.variables)
        if not url:
            raise EngineError("http_request 缺少 url")
        headers = substitute_in_value(step.get("headers", {}), ctx.variables) or None
        body = step.get("body")
        if body is not None:
            body = substitute_in_value(body, ctx.variables)
            # 字符串 body 若为合法 JSON 对象，以 json= 发送；否则以 data= 发送。
            if isinstance(body, str):
                try:
                    maybe_json = json.loads(body)
                except (ValueError, TypeError):
                    maybe_json = None
                if isinstance(maybe_json, dict):
                    body = maybe_json
        timeout_ms = float(step.get("timeout", self.request_timeout_default * 1000))
        timeout = timeout_ms / 1000.0

        try:
            if isinstance(body, dict):
                resp = requests.request(method, url, headers=headers, json=body, timeout=timeout)
            else:
                resp = requests.request(method, url, headers=headers, data=body, timeout=timeout)
        except requests.exceptions.Timeout as exc:
            raise EngineError(f"HTTP 请求超时: {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise EngineError(f"HTTP 请求失败: {url}: {exc}") from exc

        ctx.last_response = resp.text
        try:
            ctx.last_response_json = resp.json()
        except ValueError:
            ctx.last_response_json = None
        ctx.log(f"HTTP {method} {url} -> {resp.status_code}")

        callback = step.get("callback")
        if callback:
            if not isinstance(callback, dict):
                raise EngineError("callback 必须是对象")
            if ctx.last_response_json is None:
                raise EngineError("callback 需要 JSON 响应，但返回内容不是 JSON")
            for var_name, json_path in callback.items():
                ctx.variables[str(var_name)] = extract_json_path(ctx.last_response_json, str(json_path))
                ctx.log(f"回调变量 {var_name} = {ctx.variables[str(var_name)]!r} <- {json_path}")

    def _do_user_input(self, step: dict[str, Any], ctx: ExecutionContext) -> None:
        """弹出输入框，把结果暂存到变量（由 GUI 提供真实弹窗）。"""
        prompt = substitute_template(str(step.get("prompt", "请输入内容")), ctx.variables)
        variable = step.get("variable")
        if not isinstance(variable, str) or not variable:
            raise EngineError("user_input 缺少 variable")
        if self.on_input is None:
            raise EngineError(f"需要用户输入：{prompt}，但未提供输入回调")
        answer = self.on_input(prompt)
        ctx.variables[variable] = answer
        ctx.log(f"用户输入 -> {variable}: {answer!r}")

    def _do_alert(self, step: dict[str, Any], ctx: ExecutionContext) -> None:
        """弹出提示框，内容支持变量替换。"""
        content = substitute_template(str(step.get("content", "")), ctx.variables)
        if self.on_alert is not None:
            self.on_alert(content)
        ctx.log(f"提示: {content}")

    def _do_write_clipboard(self, step: dict[str, Any], ctx: ExecutionContext) -> None:
        """写入剪贴板：type=text 写纯文本；type=table 把二维数组解析为 CSV 写入。"""
        data = step.get("data")
        if data is None:
            raise EngineError("write_clipboard 缺少 data")
        data = substitute_in_value(data, ctx.variables)
        ctype = str(step.get("type", "text"))
        if ctype == "table" and isinstance(data, list):
            text = "\r\n".join(",".join(str(cell) for cell in row) for row in data)
        else:
            text = str(data)
        ctx.variables["__clipboard__"] = text
        ctx.log(f"写入剪贴板 ({ctype}): {text[:100]!r}")
