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


def test_fuzzy_table_size_matching_and_system_variables():
    """Requirement 2: Fuzzy row/col matching and automatic 'row' / 'column' system variables."""
    from src.core.engine import WorkflowEngine

    # 1. Fuzzy rows only: any rows, but col must be 2
    rule_fuzzy_row = RuleConfig(
        name="FuzzyRowRule",
        table_size=(1, 2),
        fuzzy_row=True,
        fuzzy_col=False,
        workflow=[{"action": "compute", "target_var": "msg", "expression": "'ok'"}]
    )
    t_3x2 = TableData([["a", "b"], ["c", "d"], ["e", "f"]])
    t_3x3 = TableData([["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"]])
    assert rule_fuzzy_row.matches(t_3x2) is True
    assert rule_fuzzy_row.matches(t_3x3) is False  # cols don't match

    # 2. Fuzzy cols only: any cols, but row must be 2
    rule_fuzzy_col = RuleConfig(
        name="FuzzyColRule",
        table_size=(2, 1),
        fuzzy_row=False,
        fuzzy_col=True,
        workflow=[{"action": "compute", "target_var": "msg", "expression": "'ok'"}]
    )
    assert rule_fuzzy_col.matches(t_3x2) is False # rows don't match
    t_2x4 = TableData([["1", "2", "3", "4"], ["5", "6", "7", "8"]])
    assert rule_fuzzy_col.matches(t_2x4) is True

    # 3. Both fuzzy: matches any table!
    rule_both_fuzzy = RuleConfig(
        name="BothFuzzyRule",
        table_size=(1, 1),
        fuzzy_row=True,
        fuzzy_col=True,
        workflow=[{"action": "compute", "target_var": "msg", "expression": "'ok'"}]
    )
    assert rule_both_fuzzy.matches(t_3x2) is True
    assert rule_both_fuzzy.matches(t_2x4) is True

    # 4. Engine automatically establishes system variables 'row' and 'column'
    engine = WorkflowEngine()
    exec_res = engine.execute_rule(rule_both_fuzzy, t_3x2)
    assert exec_res.success
    assert exec_res.variables.get("row") == "3"
    assert exec_res.variables.get("column") == "2"

    exec_res2 = engine.execute_rule(rule_both_fuzzy, t_2x4)
    assert exec_res2.success
    assert exec_res2.variables.get("row") == "2"
    assert exec_res2.variables.get("column") == "4"


def test_multiple_extra_conditions_and_matching():
    """Requirement 3: Multiple extra conditions with logical AND matching."""
    cond1 = ExtraCondition(row=0, col=0, regex=r"^VIP-[0-9]+$")
    cond2 = ExtraCondition(row=1, col=1, regex=r"^PASS$")

    rule = RuleConfig(
        name="MultiExtraTest",
        table_size=(2, 2),
        extra_conditions=[cond1, cond2],
        workflow=[{"action": "compute", "target_var": "status", "expression": "'verified'"}]
    )

    # Both match
    t_both = TableData([["VIP-888", "name"], ["info", "PASS"]])
    assert rule.matches(t_both) is True

    # Cond1 matches, Cond2 fails
    t_fail_2 = TableData([["VIP-888", "name"], ["info", "FAIL"]])
    assert rule.matches(t_fail_2) is False

    # Cond1 fails, Cond2 matches
    t_fail_1 = TableData([["GUEST-123", "name"], ["info", "PASS"]])
    assert rule.matches(t_fail_1) is False

    # Serialization roundtrip with multiple conditions
    d = rule.to_dict(use_chinese_keys=True)
    assert len(d["触发该配置的前提"]["额外条件列表"]) == 2

    restored = RuleConfig.from_dict(d)
    assert len(restored.extra_conditions) == 2
    assert restored.extra_conditions[0].regex == r"^VIP-[0-9]+$"
    assert restored.extra_conditions[1].regex == r"^PASS$"

