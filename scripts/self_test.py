"""头less 自检：配置模型、引擎执行、剪贴板解析（无需 GUI 弹窗）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excel_checker.clipboard import parse_mime_data
from excel_checker.config import (
    ConfigError,
    RuleConfig,
    substitute_in_value,
    substitute_template,
)
from excel_checker.engine import Engine, EngineError, extract_json_path


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, json_data=None) -> None:
        self.text = text
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class _FakeMime:
    """最小化模拟 QMimeData，只保留 parse_mime_data 用到的方法。"""

    def __init__(self, formats: set[str], text: str | None, csv_data: bytes | None = None) -> None:
        self._formats = set(formats)
        self._text = text
        self._csv = csv_data

    def hasFormat(self, fmt: str) -> bool:
        return fmt in self._formats

    def data(self, fmt: str):
        if fmt == "text/csv" and self._csv is not None:
            return self._csv
        raise KeyError(fmt)

    def hasText(self) -> bool:
        return self._text is not None

    def text(self) -> str:
        return self._text or ""


def test_config_validation() -> None:
    sample = {
        "name": "示例配置",
        "trigger": {"size": {"rows": 2, "cols": 2},
                    "conditions": [{"cell": [0, 0], "pattern": "[0-9]{3,}"}]},
        "steps": [
            {"action": "extract_cell", "cell": [0, 0], "variable": "id"},
            {"action": "alert", "content": "id={{id}}"},
        ],
    }
    rule = RuleConfig.from_dict(sample)
    assert rule.name == "示例配置"
    assert rule.trigger.size.rows == 2 and rule.trigger.size.cols == 2
    assert rule.trigger.check([["12345", "x"], ["y", "z"]]) is True
    # 大小不符
    assert rule.trigger.check([["12345"]]) is False
    # 前置条件不符
    assert rule.trigger.check([["abc", "x"], ["y", "z"]]) is False
    # 保存/加载往复
    path = "/tmp/_excel_checker_roundtrip.json"
    rule.save_file(path)
    loaded = RuleConfig.load_file(path)
    assert loaded.name == "示例配置" and len(loaded.steps) == 2
    os.remove(path)

    # 非法配置应抛出 ConfigError
    bad_cases = [
        {"trigger": {}, "steps": []},  # 无 name
        {"name": "x", "trigger": {}, "steps": [{"action": "no_such_action"}]},  # 未知动作
        {"name": "x", "trigger": {"size": {"rows": 0, "cols": 2}}, "steps": []},  # 非法 size
    ]
    for bad in bad_cases:
        try:
            RuleConfig.from_dict(bad)
        except ConfigError:
            continue
        raise AssertionError(f"应抛出 ConfigError: {bad}")

    # extract_cell 缺 variable：配置结构合法，引擎运行时报错；此处只确认配置层不拦截
    rule = RuleConfig.from_dict(
        {"name": "x", "trigger": {"size": {"rows": 1, "cols": 1}},
         "steps": [{"action": "extract_cell"}]}
    )
    assert len(rule.steps) == 1
    print("PASS test_config_validation")


def test_substitute() -> None:
    assert substitute_template("http://example.com/{{id}}", {"id": "abc"}) == "http://example.com/abc"
    assert substitute_template("no {{missing}} here", {}) == "no {{missing}} here"
    obj = {"url": "http://x/{{a}}", "body": {"k": "{{a}}"}, "arr": ["{{a}}", 1]}
    assert substitute_in_value(obj, {"a": "1"}) == {
        "url": "http://x/1", "body": {"k": "1"}, "arr": ["1", 1]
    }
    print("PASS test_substitute")


def test_engine_full() -> None:
    sample = {
        "name": "示例配置",
        "trigger": {"size": {"rows": 2, "cols": 2},
                    "conditions": [{"cell": [0, 0], "pattern": "[0-9]{3,}"}]},
        "steps": [
            {"action": "extract_cell", "cell": [0, 0], "variable": "id"},
            {"action": "http_request", "method": "POST", "url": "http://example.com/{{id}}",
             "headers": {"X-Id": "{{id}}"}, "body": {"id": "{{id}}"}, "timeout": 10000,
             "callback": {"newData": "res.data[0]"}},
            {"action": "user_input", "prompt": "请输入要提取第几个", "variable": "index"},
            {"action": "alert", "content": "新内容为{{newData}}，索引: {{index}}"},
            {"action": "write_clipboard", "type": "table",
             "data": [["id", "newData", "index"], ["{{id}}", "{{newData}}", "{{index}}"]]},
        ],
    }
    rule = RuleConfig.from_dict(sample)

    captured_inputs: list[str] = []
    captured_alerts: list[str] = []
    http_calls: list[tuple] = []

    def fake_input(prompt: str) -> str:
        captured_inputs.append(prompt)
        return "42"

    def fake_alert(content: str) -> None:
        captured_alerts.append(content)

    def fake_request(method, url, **kwargs):
        http_calls.append((method, url, kwargs))
        return FakeResponse(
            text='{"res":{"data":["test","item2"]}}',
            status_code=200,
            json_data={"res": {"data": ["test", "item2"]}},
        )

    import excel_checker.engine as engine_mod
    original_request = engine_mod.requests.request
    engine_mod.requests.request = fake_request
    try:
        engine = Engine(on_input=fake_input, on_alert=fake_alert)
        table = [["12345", "x"], ["y", "z"]]
        ctx = engine.run(rule, table)
    finally:
        engine_mod.requests.request = original_request

    assert ctx.variables["id"] == "12345"
    assert len(http_calls) == 1
    assert http_calls[0][0] == "POST"
    assert http_calls[0][1] == "http://example.com/12345"
    assert http_calls[0][2]["headers"] == {"X-Id": "12345"}
    assert http_calls[0][2]["json"] == {"id": "12345"}
    assert http_calls[0][2]["timeout"] == 10.0
    assert ctx.variables["newData"] == "test"
    assert captured_inputs == ["请输入要提取第几个"]
    assert ctx.variables["index"] == "42"
    assert captured_alerts == ["新内容为test，索引: 42"]
    assert ctx.variables["__clipboard__"] == "id,newData,index\r\n12345,test,42"
    print("PASS test_engine_full")


def test_engine_extract_cell_runtime_error() -> None:
    rule = RuleConfig.from_dict(
        {"name": "x", "trigger": {"size": {"rows": 1, "cols": 1}},
         "steps": [{"action": "extract_cell"}]}
    )
    engine = Engine()
    try:
        engine.run(rule, [["a"]])
    except EngineError as exc:
        assert "variable" in str(exc)
    else:
        raise AssertionError("extract_cell 缺 variable 应在引擎层抛出 EngineError")
    print("PASS test_engine_extract_cell_runtime_error")


def test_engine_timeout() -> None:
    rule = RuleConfig.from_dict({
        "name": "t",
        "trigger": {"size": {"rows": 1, "cols": 1}},
        "steps": [{"action": "http_request", "method": "GET",
                   "url": "http://slow.example.com/", "timeout": 100}],
    })

    def fake_request(method, url, **kwargs):
        import requests
        raise requests.exceptions.Timeout("read timeout")

    import excel_checker.engine as engine_mod
    original_request = engine_mod.requests.request
    engine_mod.requests.request = fake_request
    try:
        engine = Engine()
        try:
            engine.run(rule, [["a"]])
        except EngineError as exc:
            assert "超时" in str(exc)
        else:
            raise AssertionError("应抛出超时 EngineError")
    finally:
        engine_mod.requests.request = original_request
    print("PASS test_engine_timeout")


def test_extract_json_path() -> None:
    root = {"res": {"data": ["test", "item2"]}, "n": 1}
    assert extract_json_path(root, "res.data[0]") == "test"
    assert extract_json_path(root, "n") == 1
    assert extract_json_path(root, "res.data[1]") == "item2"
    try:
        extract_json_path(root, "res.missing")
    except EngineError:
        pass
    else:
        raise AssertionError("缺失键应抛出 EngineError")
    print("PASS test_extract_json_path")


def test_clipboard_parsing() -> None:
    # text/csv 格式
    mime = _FakeMime({"text/csv"}, None, b"a,b\r\nc,d")
    table = parse_mime_data(mime)
    assert table is not None and table.rows == [["a", "b"], ["c", "d"]], table
    assert table.size == (2, 2)

    # 纯文本 -> 1x1
    mime = _FakeMime({"text/plain"}, "hello")
    table = parse_mime_data(mime)
    assert table.rows == [["hello"]] and table.size == (1, 1), table

    # 多行纯文本 -> 按行拆（兼容纯文本表格）
    mime = _FakeMime({"text/plain"}, "a,b\nc,d")
    table = parse_mime_data(mime)
    assert table.rows == [["a", "b"], ["c", "d"]], table

    # 制表符分隔
    mime = _FakeMime({"text/plain"}, "a\tb\nc\td")
    table = parse_mime_data(mime)
    assert table.rows == [["a", "b"], ["c", "d"]], table

    # 空 mime
    mime = _FakeMime(set(), None)
    assert parse_mime_data(mime) is None
    print("PASS test_clipboard_parsing")


if __name__ == "__main__":
    test_config_validation()
    test_substitute()
    test_engine_full()
    test_engine_extract_cell_runtime_error()
    test_engine_timeout()
    test_extract_json_path()
    test_clipboard_parsing()
    print("\n全部自检通过")
