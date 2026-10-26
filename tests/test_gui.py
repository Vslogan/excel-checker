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


def test_vscode_scrollbar(qapp):
    from src.gui.vscode_scrollbar import VSCodeScrollBar
    from src.gui.action_cards import ExtractCellCard, HttpRequestCard, WriteClipboardCard
    from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import QPoint, Qt

    sa = QScrollArea()
    sa.resize(400, 500)
    container = QWidget()
    lay = QVBoxLayout(container)
    card1 = ExtractCellCard()
    card2 = HttpRequestCard()
    card3 = WriteClipboardCard()
    card1.setFixedHeight(200)
    card2.setFixedHeight(250)
    card3.setFixedHeight(200)
    lay.addWidget(card1)
    lay.addWidget(card2)
    lay.addWidget(card3)
    sa.setWidget(container)

    cards = [card1, card2, card3]
    sb = VSCodeScrollBar(sa, cards_getter=lambda: cards)
    sa.setVerticalScrollBar(sb)
    sa.show()
    qapp.processEvents()

    assert sb.width() == 24
    assert sb.minimum() == 0

    # Total content height
    total_h = sb._get_total_content_height()
    assert total_h >= 650

    # Markers check
    markers = sb._get_card_markers(24.0, 500.0, float(total_h))
    assert len(markers) == 3
    assert markers[0]["title"] == card1.display_title
    assert markers[0]["is_visible"] is True  # Top card is visible at scroll 0

    # Test clicking marker 3 to scroll to it
    m3_pos = markers[2]["rect"].center().toPoint()
    press_event = QMouseEvent(QMouseEvent.MouseButtonPress, m3_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    sb.mousePressEvent(press_event)
    assert sb.value() > 0

    # Test mouse hover tooltip
    m1_pos = markers[0]["rect"].center().toPoint()
    move_event = QMouseEvent(QMouseEvent.MouseMove, m1_pos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    sb.mouseMoveEvent(move_event)
    assert sb._hovered_idx == 0
    assert "提取单元格" in sb.toolTip()

    # Repaint without errors
    sb.update()
    qapp.processEvents()


def test_compute_ifelse_goto_cards_and_scratch_style(qapp):
    from src.gui.action_cards import ComputeCard, IfElseCard, GotoCard
    from src.gui.block_editor import WorkflowPipelineTab

    # 1. Compute Card
    comp = ComputeCard({"target_var": "total", "expression": "round(a * b, 2)"})
    assert comp.btn_drag is not None
    assert comp.edit_target_var.text() == "total"
    assert comp.edit_expression.text() == "round(a * b, 2)"
    cfg_comp = comp.to_config()
    assert cfg_comp["action"] == "compute"

    # 2. Goto Card
    goto = GotoCard({"condition": "i < 10", "target_line": 2})
    assert goto.btn_drag is not None
    assert goto.edit_condition.text() == "i < 10"
    assert goto.spin_target.value() == 2
    cfg_goto = goto.to_config()
    assert cfg_goto["action"] == "goto"

    # 3. If-Else Card & Scratch-style indentation in pipeline
    pipe = WorkflowPipelineTab()
    pipe.show()
    if_card = IfElseCard({"condition": "x > 0", "has_else": True, "then_count": 1, "else_count": 1})
    pipe.add_card(if_card)
    pipe.add_card(ComputeCard({"target_var": "r1", "expression": "10"}))
    pipe.add_card(ComputeCard({"target_var": "r2", "expression": "20"}))
    qapp.processEvents()

    # Then card has IF branch badge & indent
    assert not pipe.cards[1].badge_branch.isHidden()
    assert "IF 分支" in pipe.cards[1].badge_branch.text()

    # Else card has ELSE branch badge & indent
    assert not pipe.cards[2].badge_branch.isHidden()
    assert "ELSE 分支" in pipe.cards[2].badge_branch.text()


def test_drag_handle_and_pipeline_drag_interactions(qapp):
    from src.gui.block_editor import WorkflowPipelineTab
    from src.gui.action_cards import ComputeCard
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import QPoint, Qt

    pipe = WorkflowPipelineTab()
    pipe.show()
    c1 = ComputeCard({"target_var": "v1", "expression": "1"})
    c2 = ComputeCard({"target_var": "v2", "expression": "2"})
    pipe.add_card(c1)
    pipe.add_card(c2)
    qapp.processEvents()

    # Both cards have drag handle SVG
    assert c1.btn_drag is not None
    assert c2.btn_drag is not None

    # Test drag initiate
    press_event = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    pipe._on_card_drag_initiated(c1, press_event)
    assert pipe._dragging_card == c1

    # Test drag moved into reorder zone (exercises line 374 with QPoint calculation!)
    move_event = QMouseEvent(QMouseEvent.MouseMove, QPoint(150, 80), QPoint(150, 80), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    pipe._on_card_drag_moved(c1, move_event)
    assert pipe._is_dragging is True
    assert pipe._drop_index >= 0

    # Test drag moved into left delete zone
    del_event = QMouseEvent(QMouseEvent.MouseMove, QPoint(5, 80), QPoint(5, 80), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    pipe._on_card_drag_moved(c1, del_event)
    assert pipe._in_delete_zone is True

    # Test release
    release_event = QMouseEvent(QMouseEvent.MouseButtonRelease, QPoint(10, 80), QPoint(10, 80), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    pipe._on_card_drag_released(c1, release_event)

    # Clean up drag
    pipe._cleanup_drag()
    assert pipe._dragging_card is None


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


def test_requirements_gui_enhancements(qapp):
    """Test GUI enhancements: toolbar labels, Goto jump & marker, scrollbar drag highlight, no else checkbox, nested indentation."""
    from PyQt5.QtWidgets import QPushButton
    from src.gui.action_cards import GotoCard, IfElseCard, ComputeCard, GotoTargetMarkerWidget

    editor = BlockEditorWidget()
    pipe = editor.pipeline_tab

    # 1. Requirement 2: Clean toolbar button labels without (if/else) or (goto)
    buttons = pipe.findChildren(QPushButton)
    btn_texts = [b.text() for b in buttons]
    assert "+ 如果" in btn_texts
    assert "+ 跳转" in btn_texts
    assert not any("(if/else)" in t for t in btn_texts)
    assert not any("(goto)" in t for t in btn_texts)

    # 2. Requirement 6: No "包含else分支" checkbox; spin_else_count defaults to 0 and is enabled
    if_card = IfElseCard()
    assert not hasattr(if_card, "chk_has_else")
    assert if_card.spin_else_count.isEnabled() is True
    assert if_card.spin_else_count.value() == 0
    assert if_card.spin_then_count.value() == 1
    cfg_if = if_card.to_config()
    assert cfg_if["else_count"] == 0
    assert cfg_if["has_else"] is False

    # 3. Requirement 4: GotoCard has "跳转" button and emits jump_requested
    goto_card = GotoCard()
    assert hasattr(goto_card, "btn_jump")
    assert goto_card.btn_jump.text() == "跳转"
    goto_card.spin_target.setValue(2)

    received_jump_target = []
    goto_card.jump_requested.connect(lambda t: received_jump_target.append(t))
    goto_card.btn_jump.click()
    assert received_jump_target == [2]

    # 4. Requirement 4: GotoTargetMarkerWidget placed at target step and navigates to source Goto
    pipe.clear_cards()
    card_compute1 = ComputeCard({"target_var": "a", "expression": "1"})
    card_goto = GotoCard({"condition": "1", "target_line": 1}) # jumps to step 1
    pipe.add_card(card_compute1)
    pipe.add_card(card_goto)

    # There should now be a GotoTargetMarkerWidget inserted before step 1
    markers = [w for w in pipe._marker_widgets if isinstance(w, GotoTargetMarkerWidget)]
    assert len(markers) == 1
    assert markers[0].target_step == 1
    assert 2 in markers[0].from_steps

    # Clicking the marker emits jump_to_source_requested(2)
    marker_source_clicked = []
    markers[0].jump_to_source_requested.connect(lambda s: marker_source_clicked.append(s))
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import QPoint
    click_ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    markers[0].mousePressEvent(click_ev)
    assert marker_source_clicked == [2]

    # Test scroll_to_step
    pipe.scroll_to_step(2)

    # 5. Requirement 5: Scrollbar highlights dragged card
    sb = pipe.vscode_scrollbar
    assert sb._dragged_idx is None
    sb.set_dragged_card_index(0)
    assert sb._dragged_idx == 0
    sb.set_dragged_card_index(None)
    assert sb._dragged_idx is None

    # 6. Requirement 3: Multi-level nested Scratch-style indentation
    pipe.clear_cards()
    # Step 1: Outer if (then_count=3, else_count=1)
    pipe.add_card(IfElseCard({"condition": "1", "then_count": 3, "else_count": 1}))
    # Step 2: Inner if inside outer then (then_count=1, else_count=1)
    pipe.add_card(IfElseCard({"condition": "1", "then_count": 1, "else_count": 1}))
    # Step 3: Compute inside inner then (level 2)
    pipe.add_card(ComputeCard({"target_var": "x", "expression": "10"}))
    # Step 4: Compute inside inner else (level 2)
    pipe.add_card(ComputeCard({"target_var": "y", "expression": "20"}))
    # Step 5: Compute inside outer else (level 1)
    pipe.add_card(ComputeCard({"target_var": "z", "expression": "30"}))
    # Step 6: Compute at root level (level 0)
    pipe.add_card(ComputeCard({"target_var": "w", "expression": "40"}))

    assert pipe.cards[0]._indent_level == 0
    assert pipe.cards[1]._indent_level == 1
    assert pipe.cards[1]._branch_type == "if"
    assert pipe.cards[2]._indent_level == 2
    assert pipe.cards[2]._branch_type == "if"
    assert pipe.cards[3]._indent_level == 2
    assert pipe.cards[3]._branch_type == "else"
    assert pipe.cards[4]._indent_level == 1
    assert pipe.cards[4]._branch_type == "else"
    assert pipe.cards[5]._indent_level == 0

