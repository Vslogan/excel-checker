"""Tests for RuleConfig model and serialization."""
import os
import pytest
from src.core.config_model import ExtraCondition, RuleConfig
from src.core.table_parser import TableData


def test_load_chinese_config():
    path = os.path.join("configs", "示例配置1.json")
    rule = RuleConfig.load_from_file(path)
    assert "用户ID" in rule.name
    assert rule.table_size == (1, 1)
    assert rule.extra_condition is not None
    assert rule.extra_condition.row == 0
    assert rule.extra_condition.col == 0
    assert rule.extra_condition.regex == "[0-9]{3,}"
    assert len(rule.workflow) == 5
    assert rule.enabled is True

    # Validate passes
    errors = rule.validate()
    assert len(errors) == 0


def test_rule_matches():
    rule = RuleConfig(
        name="Test Rule",
        table_size=(1, 1),
        extra_condition=ExtraCondition(row=0, col=0, regex=r"^\d{3,}$"),
        workflow=[{"action": "show_message", "content": "hi"}]
    )

    # 12345 should match
    t1 = TableData.from_text("12345")
    assert rule.matches(t1)

    # 12 should not match (only 2 digits)
    t2 = TableData.from_text("12")
    assert not rule.matches(t2)

    # 2x2 table should not match
    t3 = TableData.from_text("123\t456\r\n789\t000")
    assert not rule.matches(t3)


def test_validation_errors():
    rule = RuleConfig(name="", table_size=(0, 0), workflow=[])
    errors = rule.validate()
    assert any("规则名称不能为空" in e for e in errors)
    assert any("表格大小" in e for e in errors)
    assert any("至少需要包含一个动作" in e for e in errors)
