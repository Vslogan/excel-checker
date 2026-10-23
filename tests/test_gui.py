"""Automated GUI tests using offscreen Qt platform."""
import os
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from src.core.config_model import ExtraCondition, RuleConfig
from src.core.engine import WorkflowEngine
from src.gui.block_editor import BlockEditorWidget
from src.gui.json_editor_widget import JsonEditorWidget
from src.gui.main_window import MainWindow
from src.gui.simulator_widget import SimulatorWidget


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_block_editor_load_and_dump(qapp):
    editor = BlockEditorWidget()
    rule = RuleConfig(
        name="测试规则",
        table_size=(2, 3),
        extra_condition=ExtraCondition(row=0, col=1, regex=r"^\d+$"),
        workflow=[
            {"action": "extract_cell", "position": [0, 1], "variable": "target_id"},
            {"action": "show_message", "title": "通知", "content": "收到 {{target_id}}"}
        ],
        enabled=True,
    )

    editor.load_rule(rule)

    assert editor.edit_name.text() == "测试规则"
    assert editor.spin_rows.value() == 2
    assert editor.spin_cols.value() == 3
    assert editor.chk_extra.isChecked() is True
    assert editor.spin_cond_row.value() == 0
    assert editor.spin_cond_col.value() == 1
    assert editor.edit_regex.text() == r"^\d+$"
    assert len(editor.cards) == 2

    # Card operations: Move down
    editor.move_card_down(editor.cards[0])
    dumped = editor.to_rule()
    assert dumped.workflow[0]["action"] == "show_message"
    assert dumped.workflow[1]["action"] == "extract_cell"

    # Card operations: Clone
    editor.clone_card(editor.cards[0])
    assert len(editor.cards) == 3

    # Card operations: Delete
    editor.remove_card(editor.cards[0])
    assert len(editor.cards) == 2


def test_svg_tip_button_and_toast_card(qapp):
    from src.gui.action_cards import ToastCard, ExtractCellCard

    cell_card = ExtractCellCard()
    assert cell_card.btn_tip is not None
    assert "提取指定行列" in cell_card.btn_tip.toolTip()

    toast_card = ToastCard({
        "content": "提示: {{id}}",
        "duration": 3500,
        "blocking": True,
        "screen": "all",
        "position": "follow_mouse",
    })
    assert toast_card.btn_tip is not None
    assert "浮动冒泡" in toast_card.btn_tip.toolTip()
    assert toast_card.edit_content.toPlainText() == "提示: {{id}}"
    assert toast_card.spin_duration.value() == 3500
    assert toast_card.chk_blocking.isChecked() is True
    # Follow mouse disables screen combo
    assert toast_card.combo_screen.isEnabled() is False
    assert toast_card.combo_position.currentData() == "follow_mouse"

    cfg = toast_card.to_config()
    assert cfg["action"] == "toast"
    assert cfg["duration"] == 3500
    assert cfg["blocking"] is True
    assert cfg["position"] == "follow_mouse"


def test_toast_window_and_manager(qapp):
    from src.gui.toast_window import ToastWindow, ToastManager
    w = ToastWindow("Hello Toast", duration_ms=2000, position_mode="top_center")
    assert w.content == "Hello Toast"
    assert w.duration_ms == 2000
    w.show()
    w.close()

    ToastManager.show("测试冒泡", duration_ms=1000, position_mode="center", screen_mode="all")
    ToastManager.close_all()


def test_json_editor_sync(qapp):
    editor = JsonEditorWidget()
    rule = RuleConfig(
        name="JSON测试",
        table_size=(1, 1),
        workflow=[{"action": "extract_cell", "position": [0, 0], "variable": "val"}]
    )

    editor.set_rule(rule)
    text = editor.editor.toPlainText()
    assert "JSON测试" in text
    assert "extract_cell" in text

    # Switch to Chinese keys
    editor.combo_format.setCurrentIndex(1)
    text_cn = editor.editor.toPlainText()
    assert "配置名称" in text_cn
    assert "触发该配置的前提" in text_cn


def test_main_window_init(qapp):
    win = MainWindow(config_dir="configs")
    assert win.combo_configs.count() >= 1

    # Toggle monitor
    assert not win.clipboard_watcher.is_monitoring
    win.toggle_monitor()
    assert win.clipboard_watcher.is_monitoring
    win.toggle_monitor()
    assert not win.clipboard_watcher.is_monitoring


def test_simulator_widget_run(qapp):
    engine = WorkflowEngine(config_dir="configs")
    rule = RuleConfig(
        name="测试模拟",
        table_size=(1, 1),
        extra_condition=ExtraCondition(row=0, col=0, regex=r"^\d+$"),
        workflow=[
            {"action": "extract_cell", "position": [0, 0], "variable": "num"},
            {"action": "show_message", "title": "提示", "content": "收到数字: {{num}}"},
            {"action": "write_clipboard", "type": "table", "data": "COL1,COL2\n{{num}},OK"}
        ]
    )

    sim = SimulatorWidget(engine=engine, get_current_rule_fn=lambda: rule)
    sim.input_edit.setPlainText("999")
    sim.run_simulation()

    assert "流程全部执行成功" in sim.lbl_match_status.text()
    assert "999\tOK" in sim.clipboard_output.toPlainText()
