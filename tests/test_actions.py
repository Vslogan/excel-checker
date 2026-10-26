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


def test_ternary_operator_comprehensive():
    """Requirement 1: Comprehensive unit tests for C-style ternary operator in expressions."""
    from src.core.expression import evaluate_expression

    # 1. Basic ternary evaluation
    assert evaluate_expression("1 ? 'YES' : 'NO'") == "YES"
    assert evaluate_expression("0 ? 'YES' : 'NO'") == "NO"
    assert evaluate_expression("5 > 2 ? 100 : 200") == "100"
    assert evaluate_expression("5 < 2 ? 100 : 200") == "200"

    # 2. Nested ternary in condition
    assert evaluate_expression("(2 > 1 ? 1 : 0) ? 'CondTrue' : 'CondFalse'") == "CondTrue"
    assert evaluate_expression("(2 < 1 ? 1 : 0) ? 'CondTrue' : 'CondFalse'") == "CondFalse"

    # 3. Nested ternary in true branch
    assert evaluate_expression("1 ? (1 ? 'InnerT' : 'InnerF') : 'OuterF'") == "InnerT"
    assert evaluate_expression("1 ? (0 ? 'InnerT' : 'InnerF') : 'OuterF'") == "InnerF"

    # 4. Nested ternary in false branch
    assert evaluate_expression("0 ? 'OuterT' : (1 ? 'InnerT' : 'InnerF')") == "InnerT"
    assert evaluate_expression("0 ? 'OuterT' : (0 ? 'InnerT' : 'InnerF')") == "InnerF"

    # 5. Right-associative chaining without parentheses: a ? 1 : b ? 2 : 3
    # When a=0, b=1 -> evaluates to 2
    assert evaluate_expression("0 ? 1 : 1 ? 2 : 3") == "2"
    # When a=0, b=0 -> evaluates to 3
    assert evaluate_expression("0 ? 1 : 0 ? 2 : 3") == "3"
    # When a=1 -> evaluates to 1
    assert evaluate_expression("1 ? 1 : 0 ? 2 : 3") == "1"

    # 6. Deep 3-level nesting
    expr_deep = "0 ? 'A' : (0 ? 'B' : (1 ? 'C' : 'D'))"
    assert evaluate_expression(expr_deep) == "C"

    # 7. Short-circuit lazy evaluation (unselected branch must NOT cause divide by zero or missing var errors)
    # Division by zero in false branch when condition is True:
    assert evaluate_expression("1 ? 42 : 100 / 0") == "42"
    # Division by zero in true branch when condition is False:
    assert evaluate_expression("0 ? 100 / 0 : 42") == "42"
    # Undefined variable in unselected branch:
    assert evaluate_expression("1 ? 99 : nonexistent_variable") == "99"
    assert evaluate_expression("0 ? nonexistent_variable : 99") == "99"

    # 8. String literals containing '?' and ':' characters
    assert evaluate_expression("1 ? 'https://example.com?query=1:2' : 'other'") == "https://example.com?query=1:2"
    assert evaluate_expression("0 ? 'a' : 'colon:separated?question'") == "colon:separated?question"

    # 9. Expressions with context variables and arithmetic inside ternary
    vars_map = {"x": 10, "y": 20, "name": "Excel"}
    assert evaluate_expression("x < y ? x + y : x - y", vars_map) == "30"
    assert evaluate_expression("x > y ? x + y : x - y", vars_map) == "-10"
    assert evaluate_expression("name == 'Excel' ? strcat(name, 'Checker') : 'Other'", vars_map) == "ExcelChecker"


def test_variable_naming_validation_and_global_scope():
    """Requirement 7: Variable identifier validation and global scope enforcement."""
    from src.core.context import ExecutionContext
    from src.core.expression import validate_variable_name
    from src.core.actions.compute import ComputeAction
    from src.core.context import HeadlessUIDelegate

    # 1. Identifier validation helper tests
    assert validate_variable_name("a") is True
    assert validate_variable_name("_temp") is True
    assert validate_variable_name("var_123") is True
    assert validate_variable_name("CamelCase") is True
    assert validate_variable_name("__double_under__") is True

    # Invalid names
    assert validate_variable_name("123var") is False  # cannot start with digit
    assert validate_variable_name("a-b") is False     # no hyphens
    assert validate_variable_name("a.b") is False     # no dots
    assert validate_variable_name("var name") is False # no spaces
    assert validate_variable_name("") is False
    assert validate_variable_name("   ") is False

    # 2. ExecutionContext.set_var validation
    ctx = ExecutionContext()
    ctx.set_var("valid_var", "100")
    assert ctx.get_var("valid_var") == "100"

    with pytest.raises(ValueError, match="无效的变量名"):
        ctx.set_var("123_invalid", "test")

    with pytest.raises(ValueError, match="无效的变量名"):
        ctx.set_var("my-var", "test")

    # 3. ComputeAction left-value validation
    delegate = HeadlessUIDelegate()
    act_invalid = ComputeAction({"target_var": "99_invalid", "expression": "1 + 1"})
    res_invalid = act_invalid.execute(ctx, delegate)
    assert not res_invalid.success
    assert "不合法" in res_invalid.error

    act_valid = ComputeAction({"target_var": "total_sum", "expression": "10 + 20"})
    res_valid = act_valid.execute(ctx, delegate)
    assert res_valid.success
    assert ctx.get_var("total_sum") == "30"

    # 4. Global scope verification across sequential steps
    act_step2 = ComputeAction({"target_var": "accum", "expression": "total_sum * 2"})
    res_step2 = act_step2.execute(ctx, delegate)
    assert res_step2.success
    assert ctx.get_var("accum") == "60"
    # total_sum remains intact in the global context
    assert ctx.get_var("total_sum") == "30"


def test_extract_cell_with_variable_coords():
    """Requirement 1: ExtractCellAction supports row and column passed as variables or templates,
    auto-casts to number, and reports error on non-numeric values."""
    table = TableData([["r0c0", "r0c1", "r0c2"], ["r1c0", "r1c1", "r1c2"], ["r2c0", "r2c1", "r2c2"]])
    ctx = ExecutionContext(table_data=table)
    delegate = HeadlessUIDelegate()

    # 1. Variables passed as row and col
    ctx.set_var("target_row", "1")
    ctx.set_var("target_col", "2")
    act_var = ExtractCellAction({"row": "target_row", "col": "target_col", "variable": "val_1"})
    res_var = act_var.execute(ctx, delegate)
    assert res_var.success
    assert res_var.output == "r1c2"
    assert ctx.get_var("val_1") == "r1c2"

    # 2. Template string interpolation: e.g. {{r}}, {{c}}
    ctx.set_var("r", 2)
    ctx.set_var("c", 0)
    act_tmpl = ExtractCellAction({"position": ["{{r}}", "{{c}}"], "variable": "val_2"})
    res_tmpl = act_tmpl.execute(ctx, delegate)
    assert res_tmpl.success
    assert res_tmpl.output == "r2c0"
    assert ctx.get_var("val_2") == "r2c0"

    # 3. String float conversion e.g. "1.0"
    act_float = ExtractCellAction({"row": "1.0", "col": "1", "variable": "val_3"})
    res_float = act_float.execute(ctx, delegate)
    assert res_float.success
    assert res_float.output == "r1c1"

    # 4. Non-numeric row string -> error
    act_err_row = ExtractCellAction({"row": "invalid_number_abc", "col": 0, "variable": "val_err"})
    res_err_row = act_err_row.execute(ctx, delegate)
    assert not res_err_row.success
    assert "不是有效数字" in res_err_row.error

    # 5. Non-numeric variable value -> error
    ctx.set_var("bad_col", "not_a_num")
    act_err_var = ExtractCellAction({"row": 0, "col": "bad_col", "variable": "val_err2"})
    res_err_var = act_err_var.execute(ctx, delegate)
    assert not res_err_var.success
    assert "不是有效数字" in res_err_var.error


def test_exit_action():
    """Requirement 4: Exit action cleanly terminates workflow execution immediately."""
    from src.core.actions.exit import ExitAction
    from src.core.engine import WorkflowEngine
    from src.core.config_model import RuleConfig

    ctx = ExecutionContext()
    delegate = HeadlessUIDelegate()
    act = ExitAction()
    res = act.execute(ctx, delegate)
    assert res.success
    assert res.is_exit is True

    # Test in engine: steps after exit are NOT executed
    engine = WorkflowEngine()
    rule = RuleConfig(
        name="ExitTest",
        table_size=(1, 1),
        workflow=[
            {"action": "compute", "target_var": "before_exit", "expression": "100"},
            {"action": "exit"},
            {"action": "compute", "target_var": "after_exit", "expression": "200"},
        ]
    )
    exec_res = engine.execute_rule(rule, TableData([["x"]]))
    assert exec_res.success
    assert exec_res.variables.get("before_exit") == "100"
    assert "after_exit" not in exec_res.variables  # stopped cleanly!



