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


def test_compute_action_arithmetic_and_precision():
    from src.core.actions.compute import ComputeAction
    ctx = ExecutionContext()
    ctx.set_var("a", "10")
    ctx.set_var("b", "3")
    delegate = HeadlessUIDelegate()

    # 1. Basic arithmetic and max 6 non-zero decimals
    act1 = ComputeAction({"target_var": "res1", "expression": "a / b"})
    assert act1.execute(ctx, delegate).success
    assert ctx.get_var("res1") == "3.333333"

    # 2. Modulo & parentheses priority
    act2 = ComputeAction({"target_var": "res2", "expression": "(a + 2) % 5"})
    assert act2.execute(ctx, delegate).success
    assert ctx.get_var("res2") == "2"

    # 3. Float addition and subtraction
    act3 = ComputeAction({"target_var": "res3", "expression": "12.3456789 - 2.3456789"})
    assert act3.execute(ctx, delegate).success
    assert ctx.get_var("res3") == "10"


def test_compute_action_logic_and_comparisons():
    from src.core.actions.compute import ComputeAction
    ctx = ExecutionContext()
    ctx.set_var("x", "15")
    ctx.set_var("y", "20")
    delegate = HeadlessUIDelegate()

    # Non-zero or 0 result strictly (no true/false string)
    act1 = ComputeAction({"target_var": "is_greater", "expression": "x > y"})
    assert act1.execute(ctx, delegate).success
    assert ctx.get_var("is_greater") == "0"

    act2 = ComputeAction({"target_var": "is_less", "expression": "x < y"})
    assert act2.execute(ctx, delegate).success
    assert ctx.get_var("is_less") == "1"

    # Logic: &&, ||, !
    act3 = ComputeAction({"target_var": "combined", "expression": "(x < y) && !(x == 0)"})
    assert act3.execute(ctx, delegate).success
    assert ctx.get_var("combined") == "1"


def test_compute_action_builtin_functions():
    from src.core.actions.compute import ComputeAction
    ctx = ExecutionContext()
    ctx.set_var("price", "99.856")
    ctx.set_var("sku", "ITEM_12345")
    delegate = HeadlessUIDelegate()

    act_round = ComputeAction({"target_var": "r_price", "expression": "round(price, 2)"})
    assert act_round.execute(ctx, delegate).success
    assert ctx.get_var("r_price") == "99.86"

    act_ceil = ComputeAction({"target_var": "c_price", "expression": "ceil(price)"})
    assert act_ceil.execute(ctx, delegate).success
    assert ctx.get_var("c_price") == "100"

    act_floor = ComputeAction({"target_var": "f_price", "expression": "floor(price)"})
    assert act_floor.execute(ctx, delegate).success
    assert ctx.get_var("f_price") == "99"

    act_substr = ComputeAction({"target_var": "code", "expression": "substr(sku, 5, 5)"})
    assert act_substr.execute(ctx, delegate).success
    assert ctx.get_var("code") == "12345"

    act_strcat = ComputeAction({"target_var": "merged", "expression": "strcat(\"PREFIX_\", sku, \"_OK\")"})
    assert act_strcat.execute(ctx, delegate).success
    assert ctx.get_var("merged") == "PREFIX_ITEM_12345_OK"


def test_compute_action_conversion_error_stops():
    from src.core.actions.compute import ComputeAction
    ctx = ExecutionContext()
    ctx.set_var("not_a_num", "hello_world")
    delegate = HeadlessUIDelegate()

    act = ComputeAction({"target_var": "out", "expression": "not_a_num + 5"})
    res = act.execute(ctx, delegate)
    assert not res.success
    assert "无法将 'hello_world' 转换为数字" in res.error


def test_goto_action_jump_and_skip():
    from src.core.actions.goto import GotoAction
    ctx = ExecutionContext()
    ctx.set_var("cnt", "3")
    delegate = HeadlessUIDelegate()

    # When condition is true (non-zero) -> jumps to target_line
    act_jump = GotoAction({"condition": "cnt < 5", "target_line": 2})
    res_jump = act_jump.execute(ctx, delegate)
    assert res_jump.success
    assert res_jump.jump_to == 2

    # When condition is false (0) -> does not jump
    act_no_jump = GotoAction({"condition": "cnt > 10", "target_line": 2})
    res_no_jump = act_no_jump.execute(ctx, delegate)
    assert res_no_jump.success
    assert res_no_jump.jump_to is None


def test_if_else_action_branches():
    from src.core.actions.if_else import IfElseAction
    ctx = ExecutionContext()
    ctx.current_step = 2
    ctx.set_var("score", "85")
    delegate = HeadlessUIDelegate()

    # True condition with else branch
    act_true = IfElseAction({
        "condition": "score >= 60",
        "has_else": True,
        "then_count": 2,
        "else_count": 1,
    })
    res_true = act_true.execute(ctx, delegate)
    assert res_true.success
    assert res_true.jump_to is None
    # When step 2+2=4 finishes, skip past else to step 6
    assert res_true.skip_after == (4, 6)

    # False condition with else branch
    ctx.set_var("score", "40")
    act_false = IfElseAction({
        "condition": "score >= 60",
        "has_else": True,
        "then_count": 2,
        "else_count": 1,
    })
    res_false = act_false.execute(ctx, delegate)
    assert res_false.success
    # Jumps directly to start of else (step 2 + 1 + 2 = 5)
    assert res_false.jump_to == 5


def test_turing_completeness_loop_and_goto_in_if():
    from src.core.config_model import RuleConfig
    from src.core.engine import WorkflowEngine
    from src.core.table_parser import TableData

    engine = WorkflowEngine()
    # Calculates factorial of 4: 4 * 3 * 2 * 1 = 24
    rule = RuleConfig(
        name="FactorialLoop",
        table_size=(1, 1),
        workflow=[
            {"action": "compute", "target_var": "n", "expression": "4"},
            {"action": "compute", "target_var": "fact", "expression": "1"},
            # Step 3: loop start
            {"action": "compute", "target_var": "fact", "expression": "fact * n"},
            {"action": "compute", "target_var": "n", "expression": "n - 1"},
            # Step 5: If n > 1 -> Goto 3
            {"action": "if_else", "condition": "n > 1", "has_else": False, "then_count": 1, "else_count": 0},
            {"action": "goto", "condition": "1", "target_line": 3},
            # Step 7: Done
            {"action": "compute", "target_var": "done", "expression": "1"},
        ]
    )
    res = engine.execute_rule(rule, TableData([["1"]]))
    assert res.success
    assert res.variables["fact"] == "24"
    assert res.variables["n"] == "1"
    assert res.variables["done"] == "1"

