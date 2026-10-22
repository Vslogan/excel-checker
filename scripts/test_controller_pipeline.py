"""控制器端到端自检（纯头less，不渲染 GUI）：

加载示例规则 -> 注入假剪贴板表格 -> 命中匹配 -> 引擎执行（假网络/输入/弹窗）
-> 验证变量与信号；再验证大小不匹配/条件不匹配/禁用配置都会被忽略。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excel_checker.clipboard import ClipboardTable
from excel_checker.controller import AppController
from excel_checker.engine import EngineError


class FakeResponse:
    def __init__(self, text, status_code=200, json_data=None):
        self.text = text
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


def run() -> None:
    matched: list[str] = []
    executed: list[tuple[str, str]] = []
    errors: list[str] = []

    controller = AppController()
    controller.ruleMatched.connect(lambda n: matched.append(n))
    controller.ruleExecuted.connect(lambda n, s: executed.append((n, s)))
    controller.error.connect(lambda m: errors.append(m))

    config_path = "/home/user/excel-checker/configs/sample.json"
    controller.load_config(config_path)
    assert controller.is_active(config_path)

    # 假网络 + 输入 + 弹窗
    http_calls = []
    alerts: list[str] = []

    def fake_input(prompt: str) -> str:
        return "42"

    def fake_alert(content: str) -> None:
        alerts.append(content)

    def fake_request(method, url, **kwargs):
        http_calls.append((method, url, kwargs))
        return FakeResponse(
            text='{"res":{"data":["test","item2"]}}',
            json_data={"res": {"data": ["test", "item2"]}},
        )

    import excel_checker.engine as engine_mod

    original = engine_mod.requests.request
    engine_mod.requests.request = fake_request
    try:
        controller._engine.on_input = fake_input
        controller._engine.on_alert = fake_alert

        captured_ctxs: list = []
        orig_run = controller._engine.run

        def _run_wrapper(rule, table):
            ctx = orig_run(rule, table)
            captured_ctxs.append(ctx)
            return ctx

        controller._engine.run = _run_wrapper

        # 1) 完全匹配
        matched.clear(); executed.clear(); errors.clear()
        controller._on_clipboard_table(
            ClipboardTable(rows=[["12345", "x"], ["y", "z"]], source="text")
        )
        assert matched == ["示例配置"], matched
        assert len(executed) == 1, executed
        assert not errors, errors
        ctx = captured_ctxs[-1]
        assert ctx.variables["id"] == "12345"
        assert ctx.variables["newData"] == "test"
        assert ctx.variables["index"] == "42"
        assert alerts == ["新内容为test，索引: 42"], alerts
        assert http_calls[0][1] == "http://example.com/12345"
        print("PASS pipeline: full match executes rule")

        # 2) 表格大小不符 -> 忽略
        matched.clear(); executed.clear(); errors.clear()
        controller._on_clipboard_table(ClipboardTable(rows=[["12345"]], source="text"))
        assert matched == [] and executed == [] and errors == []
        print("PASS pipeline: size mismatch ignored")

        # 3) 额外条件不符 -> 忽略
        matched.clear(); executed.clear()
        controller._on_clipboard_table(
            ClipboardTable(rows=[["abc", "x"], ["y", "z"]], source="text")
        )
        assert matched == [] and executed == []
        print("PASS pipeline: extra condition mismatch ignored")

        # 4) 纯文本 1x1 且不满足条件 -> 忽略（兼容约定）
        matched.clear(); executed.clear()
        controller._on_clipboard_table(ClipboardTable(rows=[["hello"]], source="text"))
        assert matched == [] and executed == []
        print("PASS pipeline: plain text 1x1 ignored when condition fails")

        # 5) 禁用配置 -> 忽略
        controller.disable_config(config_path)
        assert not controller.is_active(config_path)
        matched.clear(); executed.clear()
        controller._on_clipboard_table(
            ClipboardTable(rows=[["12345", "x"], ["y", "z"]], source="text")
        )
        assert matched == [] and executed == []
        controller.enable_config(config_path)
        assert controller.is_active(config_path)
        print("PASS pipeline: disabled config ignored, enable works")

        # 6) 超时 -> 报错信号，不崩溃
        def fake_timeout(method, url, **kwargs):
            import requests
            raise requests.exceptions.Timeout("read timeout")

        engine_mod.requests.request = fake_timeout
        matched.clear(); executed.clear(); errors.clear()
        controller._on_clipboard_table(
            ClipboardTable(rows=[["12345", "x"], ["y", "z"]], source="text")
        )
        assert matched == ["示例配置"]
        assert executed == []  # 执行失败不发送 ruleExecuted
        assert any("超时" in m for m in errors), errors
        print("PASS pipeline: timeout reported via error signal")
    finally:
        engine_mod.requests.request = original

    print("\n控制器管道全部自检通过")


if __name__ == "__main__":
    run()
