"""Tests for action execution."""
from unittest.mock import MagicMock, patch
import pytest

from src.core.actions.base import ActionRegistry
from src.core.actions.extract_cell import ExtractCellAction
from src.core.actions.file_ops import FileOpsAction
from src.core.actions.http_request import HttpRequestAction
from src.core.actions.show_message import ShowMessageAction
from src.core.actions.user_input import UserInputAction
from src.core.actions.write_clipboard import WriteClipboardAction
from src.core.context import ExecutionContext, HeadlessUIDelegate
from src.core.table_parser import TableData


def test_extract_cell_action():
    table = TableData.from_text("cell00\tcell01\r\ncell10\tcell11")
    ctx = ExecutionContext(table_data=table)
    delegate = HeadlessUIDelegate()

    act = ExtractCellAction({"position": [1, 0], "variable": "my_val"})
    res = act.execute(ctx, delegate)
    assert res.success
    assert res.output == "cell10"
    assert ctx.get_var("my_val") == "cell10"


def test_http_request_action():
    ctx = ExecutionContext()
    ctx.set_var("user_id", "456")
    delegate = HeadlessUIDelegate()

    act = HttpRequestAction({
        "method": "POST",
        "url": "https://api.example.com/items/{{user_id}}",
        "headers": {"X-Custom": "test-{{user_id}}"},
        "body": "{\"id\": {{user_id}}}",
        "timeout": "5000 ms",
        "callback": {
            "retrieved_name": "res.data[0].name"
        }
    })

    # Mock requests.request
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "res": {
            "data": [
                {"name": "Alice"}
            ]
        }
    }

    with patch("requests.request", return_value=mock_resp) as mock_req:
        res = act.execute(ctx, delegate)
        assert res.success
        assert ctx.get_var("retrieved_name") == "Alice"
        mock_req.assert_called_once()
        args, kwargs = mock_req.call_args
        assert kwargs["url"] == "https://api.example.com/items/456"
        assert kwargs["headers"]["X-Custom"] == "test-456"
        assert kwargs["timeout"] == 5.0


def test_http_request_timeout():
    import requests
    ctx = ExecutionContext()
    delegate = HeadlessUIDelegate()

    act = HttpRequestAction({
        "method": "GET",
        "url": "https://slow.example.com",
        "timeout": 1000
    })

    with patch("requests.request", side_effect=requests.exceptions.Timeout("Timeout")):
        res = act.execute(ctx, delegate)
        assert not res.success
        assert "超时" in res.error


def test_user_input_action():
    ctx = ExecutionContext()
    delegate = HeadlessUIDelegate(predefined_inputs={"请输入数字": "99"})
    act = UserInputAction({"prompt": "请输入数字", "variable": "chosen_num"})
    res = act.execute(ctx, delegate)
    assert res.success
    assert ctx.get_var("chosen_num") == "99"


def test_show_message_action():
    ctx = ExecutionContext()
    ctx.set_var("val", "OK")
    delegate = HeadlessUIDelegate()
    act = ShowMessageAction({"title": "通知", "content": "状态: {{val}}"})
    res = act.execute(ctx, delegate)
    assert res.success
    assert res.output == "状态: OK"
    assert delegate.messages[0]["message"] == "状态: OK"


def test_write_clipboard_table():
    ctx = ExecutionContext()
    ctx.set_var("c1", "ID01")
    ctx.set_var("c2", "Name01")
    delegate = HeadlessUIDelegate()

    act = WriteClipboardAction({
        "type": "table",
        "data": "{{c1}},{{c2}}\n100,200"
    })
    res = act.execute(ctx, delegate)
    assert res.success
    # In table mode, comma separated becomes tab separated
    expected_tsv = "ID01\tName01\r\n100\t200"
    assert delegate.get_clipboard() == expected_tsv


def test_toast_action_normal():
    from src.core.actions.toast import ToastAction
    ctx = ExecutionContext()
    ctx.set_var("item_name", "iPhone 15")
    delegate = HeadlessUIDelegate()

    act = ToastAction({
        "content": "已成功处理: {{item_name}}",
        "duration": "2500 ms",
        "blocking": True,
        "screen": "all",
        "position": "top_center",
    })
    res = act.execute(ctx, delegate)
    assert res.success
    assert res.output == "已成功处理: iPhone 15"
    assert len(delegate.toasts) == 1
    t = delegate.toasts[0]
    assert t["content"] == "已成功处理: iPhone 15"
    assert t["duration_ms"] == 2500
    assert t["blocking"] is True
    assert t["screen"] == "all"
    assert t["position"] == "top_center"


def test_toast_action_empty_content_skips():
    from src.core.actions.toast import ToastAction
    ctx = ExecutionContext()
    delegate = HeadlessUIDelegate()

    # Empty content should skip showing popup
    act = ToastAction({
        "content": "   ",
        "duration": 2000,
    })
    res = act.execute(ctx, delegate)
    assert res.success
    assert isinstance(res.output, dict) and res.output.get("skipped") is True
    assert len(delegate.toasts) == 0


def test_file_ops_action(tmp_path):
    fpath = str(tmp_path / "test.txt")
    ctx = ExecutionContext()
    ctx.set_var("val", "hello world")
    delegate = HeadlessUIDelegate()

    # Write
    w_act = FileOpsAction({"operation": "write", "path": fpath, "content": "Data: {{val}}"})
    w_res = w_act.execute(ctx, delegate)
    assert w_res.success

    # Read
    r_act = FileOpsAction({"operation": "read", "path": fpath, "variable": "read_val"})
    r_res = r_act.execute(ctx, delegate)
    assert r_res.success
    assert ctx.get_var("read_val") == "Data: hello world"
