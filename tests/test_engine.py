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
