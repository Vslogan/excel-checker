"""Tests for goto block layout order, fuzzy table size execution, and configuration migration."""
import json
import os
import shutil
import pytest
from PyQt5.QtWidgets import QApplication

from src.core.config_model import ExtraCondition, RuleConfig
from src.core.table_parser import TableData
from src.gui.action_cards import GotoTargetMarkerWidget
from src.gui.block_editor import BlockEditorWidget, WorkflowPipelineTab
from src.gui.main_window import MainWindow
from migrate_configs import ConfigMigrator, ConfigMigrationReport, migrate_file, sanitize_identifier


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_goto_card_layout_sequence_and_markers(qapp):
    """Bug 1 Verification: Step 12 Goto Step 2 must be positioned strictly before Step 13."""
    pipe = WorkflowPipelineTab()

    # Add 13 cards, step 12 is goto step 2, step 13 is write clipboard
    for i in range(1, 14):
        if i == 12:
            pipe.add_card_by_type("goto", {"condition": "1", "target_line": 2})
        elif i == 13:
            pipe.add_card_by_type("write_clipboard", {"type": "text", "data": "finished"})
        else:
            pipe.add_card_by_type("compute", {"target_var": f"v{i}", "expression": str(i)})

    # Verify self.cards logical order
    assert len(pipe.cards) == 13
    assert pipe.cards[11].action_type == "goto"
    assert pipe.cards[11].step_number == 12
    assert pipe.cards[12].action_type == "write_clipboard"
    assert pipe.cards[12].step_number == 13

    # Inspect all widgets in cards_layout
    layout_widgets = []
    for idx in range(pipe.cards_layout.count()):
        w = pipe.cards_layout.itemAt(idx).widget()
        if w:
            layout_widgets.append(w)

    # Marker must be placed right before step 2 (index 1)
    assert isinstance(layout_widgets[1], GotoTargetMarkerWidget)
    assert layout_widgets[1].target_step == 2
    assert layout_widgets[1].from_steps == [12]

    # Verify action cards sequence inside layout
    card_steps = [w.step_number for w in layout_widgets if hasattr(w, "step_number") and w.step_number is not None]
    assert card_steps == list(range(1, 14)), f"Action cards must appear strictly in steps 1..13, got {card_steps}"

    # Now dynamically change target line of step 12 from 2 to 4
    pipe.cards[11].spin_target.setValue(4)

    layout_widgets_after = [
        pipe.cards_layout.itemAt(i).widget()
        for i in range(pipe.cards_layout.count())
        if pipe.cards_layout.itemAt(i).widget()
    ]
    # Marker should now be right before step 4
    marker_after = [w for w in layout_widgets_after if isinstance(w, GotoTargetMarkerWidget)][0]
    assert marker_after.target_step == 4

    # Step 12 GotoCard must still be positioned before Step 13 WriteClipboardCard
    card_steps_after = [w.step_number for w in layout_widgets_after if hasattr(w, "step_number") and w.step_number is not None]
    assert card_steps_after == list(range(1, 14))


def test_fuzzy_table_size_matches_and_executes_in_main_window(qapp):
    """Bug 2 Verification: Fuzzy table dimensions must successfully trigger clipboard workflows."""
    win = MainWindow()

    rule = RuleConfig(
        name="FuzzyRowTestRule",
        table_size=(1, 3),
        fuzzy_row=True,
        fuzzy_col=False,
        workflow=[
            {"action": "compute", "target_var": "msg", "expression": "'fuzzy_matched'"}
        ],
        enabled=True,
    )
    win.block_editor.load_rule(rule)
    win.clipboard_watcher.is_monitoring = True

    # 4 rows x 3 columns table copied
    clipboard_text = "A1\tB1\tC1\nA2\tB2\tC2\nA3\tB3\tC3\nA4\tB4\tC4"
    win._on_clipboard_text_captured(clipboard_text)

    logs = win.log_console.toPlainText()
    assert "触发条件全部满足" in logs
    assert "与当前配置要求 (任意x3) 不匹配" not in logs

    # Simulator widget test
    sim = win.simulator
    sim.input_edit.setPlainText(clipboard_text)
    sim.run_simulation()
    assert "🎉 流程全部执行成功！" in sim.lbl_match_status.text() or "触发条件全部满足" in sim.lbl_match_status.text()


def test_table_matches_size_method():
    """Verify TableData.matches_size with fuzzy row / fuzzy col combinations."""
    t_5x3 = TableData.from_text("1\t2\t3\n4\t5\t6\n7\t8\t9\n10\t11\t12\n13\t14\t15")
    assert t_5x3.rows == 5
    assert t_5x3.cols == 3

    # Exact mismatch
    assert not t_5x3.matches_size(1, 3)

    # Fuzzy row match
    assert t_5x3.matches_size(1, 3, fuzzy_row=True, fuzzy_col=False)

    # Fuzzy col mismatch (row is 1 != 5)
    assert not t_5x3.matches_size(1, 3, fuzzy_row=False, fuzzy_col=True)

    # Both fuzzy match
    assert t_5x3.matches_size(1, 1, fuzzy_row=True, fuzzy_col=True)


def test_migration_legacy_format_upgrades(tmp_path):
    """Requirement 3: Test standalone configuration migration script."""
    legacy_config = {
        "配置名称": "旧版综合测试规则",
        "触发该配置的前提": {
            "表格大小": "2*4",
            "额外条件": {
                "位置": [0, 1],
                "正则表达式": "^ID-\\d+$"
            }
        },
        "触发后的流程": [
            {
                "动作": "提取某一格",
                "操作位置": [0, 1],
                "暂存到的变量名": "user-id-code"
            },
            {
                "动作": "如果",
                "条件": "user_id_code != ''",
                "是否有else": True,
                "if下面有多少个积木": 2,
                "else下面有多少个积木": 1
            },
            {
                "动作": "跳转",
                "目标行号": "5"
            },
            {
                "动作": "弹出冒泡窗",
                "内容": "已找到"
            },
            {
                "动作": "退出"
            }
        ]
    }

    test_file = str(tmp_path / "legacy_rule.json")
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(legacy_config, f, ensure_ascii=False, indent=2)

    migrator = ConfigMigrator(lang="chinese")
    report = migrate_file(test_file, migrator=migrator, backup=True)

    assert report.is_ok
    assert report.modified

    # Verify backup was created
    assert os.path.exists(f"{test_file}.bak")

    # Read upgraded config
    with open(test_file, "r", encoding="utf-8") as f:
        upgraded = json.load(f)

    # 1. Trigger assertions
    trigger = upgraded["触发该配置的前提"]
    assert trigger["表格大小"] == [2, 4]
    assert trigger["模糊行数"] is False
    assert trigger["模糊列数"] is False
    assert len(trigger["额外条件列表"]) == 1
    assert trigger["额外条件列表"][0]["位置"] == [0, 1]
    assert trigger["额外条件列表"][0]["正则表达式"] == "^ID-\\d+$"
    assert trigger["额外条件"] == trigger["额外条件列表"][0]

    # 2. Workflow assertions
    workflow = upgraded["触发后的流程"]
    assert len(workflow) == 5

    # Variable sanitization
    assert workflow[0]["暂存到的变量名"] == "user_id_code"
    assert workflow[0]["行"] == 0
    assert workflow[0]["列"] == 1

    # if_else counts & deprecated has_else removal
    assert workflow[1]["then_count"] == 2
    assert workflow[1]["else_count"] == 1
    assert "是否有else" not in workflow[1]
    assert "has_else" not in workflow[1]

    # goto normalization
    assert workflow[2]["目标行号"] == 5
    assert workflow[2]["条件"] == "1"

    # toast normalization
    assert workflow[3]["持续时间"] == 2000
    assert workflow[3]["是否阻塞"] is False
    assert workflow[3]["显示的屏幕"] == "鼠标所在屏幕"
    assert workflow[3]["显示的位置"] == "底部居中"


def test_sanitize_identifier_edge_cases():
    assert sanitize_identifier("valid_var_1") == "valid_var_1"
    assert sanitize_identifier("123var") == "v_123var"
    assert sanitize_identifier("my-score.val") == "my_score_val"
    assert sanitize_identifier("  spaced var  ") == "spaced_var"
    assert sanitize_identifier("???") == "var_1"
