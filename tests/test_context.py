"""Tests for ExecutionContext and path extraction."""
import pytest
from src.core.context import ExecutionContext, HeadlessUIDelegate, extract_path_value
from src.core.table_parser import TableData


def test_variable_get_set():
    ctx = ExecutionContext()
    ctx.set_var("test_key", "hello")
    assert ctx.get_var("test_key") == "hello"
    assert ctx.get_var("unknown", "default") == "default"


def test_render_template_simple():
    ctx = ExecutionContext()
    ctx.set_var("id", 123)
    ctx.set_var("name", "Alice")
    rendered = ctx.render_template("Hello {{name}}, your ID is {{id}}!")
    assert rendered == "Hello Alice, your ID is 123!"


def test_render_template_dict_and_list():
    ctx = ExecutionContext()
    ctx.set_var("token", "xyz-123")
    data = {
        "header": "Bearer {{token}}",
        "items": ["prefix_{{token}}", 42]
    }
    rendered = ctx.render_template(data)
    assert rendered["header"] == "Bearer xyz-123"
    assert rendered["items"][0] == "prefix_xyz-123"
    assert rendered["items"][1] == 42


def test_extract_path_value_direct():
    # User example: "newData": "res.data[0]" with {"res":{"data":["test",...]}}
    data = {
        "res": {
            "data": ["test", "another"]
        }
    }
    assert extract_path_value(data, "res.data[0]") == "test"
    assert extract_path_value(data, "res.data[1]") == "another"


def test_extract_path_value_strip_res_prefix():
    # When user writes res.data[0] but server returned {"data": ["test"]}
    data = {
        "data": ["test", "another"]
    }
    assert extract_path_value(data, "res.data[0]") == "test"


def test_extract_nested_dict():
    data = {
        "users": [
            {"id": 1, "profile": {"age": 25}},
            {"id": 2, "profile": {"age": 30}}
        ]
    }
    assert extract_path_value(data, "users[1].profile.age") == 30
    assert extract_path_value(data, "users[99].profile") is None


def test_headless_ui_delegate():
    delegate = HeadlessUIDelegate({"请输入名字": "Bob"})
    ans = delegate.prompt_user("请输入名字")
    assert ans == "Bob"
    delegate.show_message("标题", "内容测试")
    assert len(delegate.messages) == 1
    assert delegate.messages[0]["title"] == "标题"
    delegate.set_clipboard("test_clip")
    assert delegate.get_clipboard() == "test_clip"
