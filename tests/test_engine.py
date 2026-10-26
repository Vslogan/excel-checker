"""Tests for WorkflowEngine and complete rule execution."""
import os
from unittest.mock import MagicMock, patch
import pytest

from src.core.config_model import RuleConfig
from src.core.context import HeadlessUIDelegate
from src.core.engine import WorkflowEngine
from src.core.monitor import ClipboardMonitor
from src.core.table_parser import TableData


def test_engine_load_and_execute_example1():
    engine = WorkflowEngine(config_dir="configs")
    count = engine.reload_rules()
    assert count >= 1

    # Find 示例配置1
    rule1 = None
    for r in engine.rules:
        if "示例" in r.name:
            rule1 = r
            break
    assert rule1 is not None
    engine.active_rule = rule1

    # Text that triggers 示例配置1.json: size [1, 1], matches [0-9]{3,}
    clipboard_text = "888"
    delegate = HeadlessUIDelegate(predefined_inputs={"请输入要提取第几个": "5"})

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "res": {
            "data": ["extracted_item_0"]
        }
    }

    with patch("requests.request", return_value=mock_resp):
        res = engine.process_clipboard_text(clipboard_text, ui_delegate=delegate)
        assert res is not None
        assert res.success is True
        assert res.variables.get("id") == "888"
        assert res.variables.get("newData") == "extracted_item_0"
        assert res.variables.get("index") == "5"

        # Check that clipboard was written with table
        assert delegate.get_clipboard() == "888\textracted_item_0\t5"


def test_engine_ignores_unmatched_clipboard():
    engine = WorkflowEngine(config_dir="configs")
    engine.reload_rules()

    # 示例配置1 requires [0-9]{3,}
    rule1 = None
    for r in engine.rules:
        if "示例" in r.name:
            rule1 = r
            break
    engine.active_rule = rule1

    # "12" has only 2 digits, won't match [0-9]{3,}
    res = engine.process_clipboard_text("12")
    assert res is None


def test_clipboard_monitor_loop_avoidance():
    engine = WorkflowEngine(config_dir="configs")
    engine.reload_rules()
    delegate = HeadlessUIDelegate()
    monitor = ClipboardMonitor(engine, ui_delegate=delegate)

    # First ignore content
    monitor.ignore_content("888")
    res = monitor.handle_new_text("888")
    # Should be ignored because it was just set
    assert res is None


def test_multilevel_nested_if_else_execution():
    """Requirement 3: Multi-level arbitrary nested if/else execution engine support."""
    engine = WorkflowEngine()

    # Workflow structure:
    # 1: If outer (then_count=4, else_count=2)
    #   2: If inner (then_count=1, else_count=1)
    #     3: Compute branch='inner_then'
    #     4: Compute branch='inner_else'
    #   5: Compute outer_then_tail='executed'
    #   6: Compute outer_else_1='executed'
    #   7: Compute outer_else_2='executed'
    # 8: Compute finish='done'
    def make_rule(outer_cond: str, inner_cond: str):
        return RuleConfig(
            name="NestedIfTest",
            table_size=(1, 1),
            workflow=[
                {"action": "if_else", "condition": outer_cond, "then_count": 4, "else_count": 2},
                {"action": "if_else", "condition": inner_cond, "then_count": 1, "else_count": 1},
                {"action": "compute", "target_var": "path", "expression": "'INNER_THEN'"},
                {"action": "compute", "target_var": "path", "expression": "'INNER_ELSE'"},
                {"action": "compute", "target_var": "outer_tail", "expression": "'YES'"},
                {"action": "compute", "target_var": "outer_else", "expression": "'ELSE_1'"},
                {"action": "compute", "target_var": "outer_else", "expression": "'ELSE_2'"},
                {"action": "compute", "target_var": "finish", "expression": "'DONE'"},
            ]
        )

    # Case A: Outer True, Inner True
    res_a = engine.execute_rule(make_rule("1", "1"), TableData([["x"]]))
    assert res_a.success
    assert res_a.variables.get("path") == "INNER_THEN"
    assert res_a.variables.get("outer_tail") == "YES"
    assert "outer_else" not in res_a.variables  # outer else must be skipped!
    assert res_a.variables.get("finish") == "DONE"

    # Case B: Outer True, Inner False
    res_b = engine.execute_rule(make_rule("1", "0"), TableData([["x"]]))
    assert res_b.success
    assert res_b.variables.get("path") == "INNER_ELSE"
    assert res_b.variables.get("outer_tail") == "YES"
    assert "outer_else" not in res_b.variables  # outer else must be skipped!
    assert res_b.variables.get("finish") == "DONE"

    # Case C: Outer False
    res_c = engine.execute_rule(make_rule("0", "1"), TableData([["x"]]))
    assert res_c.success
    assert "path" not in res_c.variables        # entire outer then was skipped!
    assert "outer_tail" not in res_c.variables
    assert res_c.variables.get("outer_else") == "ELSE_2"
    assert res_c.variables.get("finish") == "DONE"


def test_if_else_zero_lines_no_else():
    """Requirement 6: else_count=0 semantically means no else branch."""
    engine = WorkflowEngine()

    rule_true = RuleConfig(
        name="NoElseTrue",
        table_size=(1, 1),
        workflow=[
            {"action": "if_else", "condition": "1", "then_count": 1, "else_count": 0},
            {"action": "compute", "target_var": "executed_then", "expression": "100"},
            {"action": "compute", "target_var": "step3", "expression": "200"},
        ]
    )
    res_t = engine.execute_rule(rule_true, TableData([["x"]]))
    assert res_t.success
    assert res_t.variables.get("executed_then") == "100"
    assert res_t.variables.get("step3") == "200"

    rule_false = RuleConfig(
        name="NoElseFalse",
        table_size=(1, 1),
        workflow=[
            {"action": "if_else", "condition": "0", "then_count": 1, "else_count": 0},
            {"action": "compute", "target_var": "executed_then", "expression": "100"},
            {"action": "compute", "target_var": "step3", "expression": "200"},
        ]
    )
    res_f = engine.execute_rule(rule_false, TableData([["x"]]))
    assert res_f.success
    assert "executed_then" not in res_f.variables  # skipped!
    assert res_f.variables.get("step3") == "200"

