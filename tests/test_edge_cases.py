"""Additional edge case tests for engine and actions."""
from unittest.mock import MagicMock, patch
import pytest

from src.core.actions.condition import ConditionAction
from src.core.actions.extract_cell import parse_cell_position
from src.core.config_model import ExtraCondition, RuleConfig
from src.core.context import ExecutionContext, HeadlessUIDelegate, extract_path_value
from src.core.engine import WorkflowEngine
from src.core.table_parser import TableData


def test_parse_cell_position_varieties():
    assert parse_cell_position("(1, 2)") == (1, 2)
    assert parse_cell_position("0,0") == (0, 0)
    assert parse_cell_position([3, 4]) == (3, 4)
    assert parse_cell_position({"row": 5, "col": 6}) == (5, 6)
    assert parse_cell_position("invalid") == (0, 0)


def test_condition_action_branching():
    ctx = ExecutionContext()
    ctx.set_var("score", "85")
    delegate = HeadlessUIDelegate()

    cond_act = ConditionAction({
        "left": "{{score}}",
        "operator": ">",
        "right": "80",
        "then": [
            {"action": "show_message", "content": "Passed!"}
        ],
        "else": [
            {"action": "show_message", "content": "Failed!"}
        ]
    })

    res = cond_act.execute(ctx, delegate)
    assert res.success is True
    assert res.output is True
    assert delegate.messages[-1]["message"] == "Passed!"


def test_roundtrip_config_json(tmp_path):
    path = str(tmp_path / "custom_rule.json")
    rule = RuleConfig(
        name="测试持久化规则",
        table_size=(2, 3),
        extra_condition=ExtraCondition(row=1, col=2, regex=r"^ABC-\d+$"),
        workflow=[
            {"action": "extract_cell", "position": [1, 2], "variable": "code"},
            {"action": "show_message", "title": "提示", "content": "Code is {{code}}"}
        ],
        enabled=True
    )
    rule.save_to_file(path, use_chinese_keys=True)

    loaded = RuleConfig.load_from_file(path)
    assert loaded.name == rule.name
    assert loaded.table_size == (2, 3)
    assert loaded.extra_condition.regex == r"^ABC-\d+$"
    assert len(loaded.workflow) == 2


def test_path_extraction_deep_nested():
    data = {
        "data": {
            "items": [
                {"tags": ["tag0", "tag1"]},
                {"tags": ["tag2", "special_value"]}
            ]
        }
    }
    val = extract_path_value(data, "res.data.items[1].tags[1]")
    assert val == "special_value"
