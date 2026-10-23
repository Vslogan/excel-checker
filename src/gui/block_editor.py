"""Rule configuration editor split into secondary tabs (Level 2 Menu).

Tab 1: Trigger Conditions (Trigger Predicates & Extra Regex)
Tab 2: Workflow Pipeline (Full-height Action Block Cards area)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config_model import ExtraCondition, RuleConfig
from src.gui.action_cards import (
    BaseActionCard,
    ExtractCellCard,
    FileOpsCard,
    HttpRequestCard,
    ShowMessageCard,
    UserInputCard,
    WriteClipboardCard,
    create_card_for_action,
)
from src.gui.vscode_scrollbar import VSCodeScrollBar


class TriggerConfigTab(QWidget):
    """Secondary Tab 1: Trigger Conditions configuration."""

    changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # Basic Info Card
        meta_group = QGroupBox("规则基础属性")
        meta_layout = QFormLayout(meta_group)
        meta_layout.setSpacing(10)

        self.edit_name = QLineEdit("新建表格检查规则")
        self.edit_name.setPlaceholderText("请输入规则名称")
        self.edit_name.textChanged.connect(self.changed.emit)
        meta_layout.addRow("规则名称:", self.edit_name)

        self.chk_enabled = QCheckBox("启用该规则 (取消勾选将忽略该规则)")
        self.chk_enabled.setChecked(True)
        self.chk_enabled.toggled.connect(self.changed.emit)
        meta_layout.addRow("启用状态:", self.chk_enabled)
        layout.addWidget(meta_group)

        # Table Dimension Card
        dim_group = QGroupBox("复制表格大小要求 (必须一致才触发)")
        dim_layout = QVBoxLayout(dim_group)
        dim_layout.setSpacing(10)

        spin_box = QHBoxLayout()
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 9999)
        self.spin_rows.setValue(1)
        self.spin_rows.setPrefix("行数: ")
        self.spin_rows.valueChanged.connect(self.changed.emit)
        spin_box.addWidget(self.spin_rows)

        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 9999)
        self.spin_cols.setValue(1)
        self.spin_cols.setPrefix("列数: ")
        self.spin_cols.valueChanged.connect(self.changed.emit)
        spin_box.addWidget(self.spin_cols)

        dim_tip = QLabel("<font color='#0284c7'>兼容说明：部分软件复制 1x1 表格时为纯文本，本工具将普通文本统一兼容视为 1x1 表格。</font>")
        spin_box.addWidget(dim_tip)
        spin_box.addStretch()
        dim_layout.addLayout(spin_box)
        layout.addWidget(dim_group)

        # Extra Regex Condition Card
        extra_group = QGroupBox("额外单元格内容条件 (可选)")
        extra_layout = QVBoxLayout(extra_group)
        extra_layout.setSpacing(10)

        self.chk_extra = QCheckBox("启用指定单元格正则表达式格式过滤")
        self.chk_extra.setChecked(False)
        self.chk_extra.toggled.connect(self._on_extra_toggled)
        extra_layout.addWidget(self.chk_extra)

        self.extra_container = QWidget()
        extra_form = QFormLayout(self.extra_container)
        extra_form.setContentsMargins(0, 4, 0, 0)
        extra_form.setSpacing(10)

        pos_box = QHBoxLayout()
        self.spin_cond_row = QSpinBox()
        self.spin_cond_row.setRange(0, 9999)
        self.spin_cond_row.setPrefix("第 ")
        self.spin_cond_row.setSuffix(" 行")
        self.spin_cond_row.valueChanged.connect(self.changed.emit)

        self.spin_cond_col = QSpinBox()
        self.spin_cond_col.setRange(0, 9999)
        self.spin_cond_col.setPrefix("第 ")
        self.spin_cond_col.setSuffix(" 列 (0-based)")
        self.spin_cond_col.valueChanged.connect(self.changed.emit)

        pos_box.addWidget(self.spin_cond_row)
        pos_box.addWidget(self.spin_cond_col)
        pos_box.addStretch()
        extra_form.addRow("目标单元格位置:", pos_box)

        # Regex pattern & live tester
        regex_box = QHBoxLayout()
        self.edit_regex = QLineEdit("[0-9]{3,}")
        self.edit_regex.setPlaceholderText("输入正则表达式，例如: [0-9]{3,}")
        self.edit_regex.textChanged.connect(self._test_live_regex)
        self.edit_regex.textChanged.connect(self.changed.emit)
        regex_box.addWidget(self.edit_regex, 3)

        self.edit_test_input = QLineEdit()
        self.edit_test_input.setPlaceholderText("实时测试输入字符...")
        self.edit_test_input.textChanged.connect(self._test_live_regex)
        regex_box.addWidget(self.edit_test_input, 2)

        self.lbl_regex_result = QLabel("待测试")
        self.lbl_regex_result.setStyleSheet("color: #64748b; font-weight: bold; min-width: 70px;")
        regex_box.addWidget(self.lbl_regex_result)

        extra_form.addRow("正则表达式规则:", regex_box)
        extra_layout.addWidget(self.extra_container)
        self.extra_container.setVisible(False)
        layout.addWidget(extra_group)

        layout.addStretch()

    def _on_extra_toggled(self, checked: bool):
        self.extra_container.setVisible(checked)
        self.changed.emit()

    def _test_live_regex(self):
        pattern = self.edit_regex.text().strip()
        sample = self.edit_test_input.text()
        if not pattern:
            self.lbl_regex_result.setText("空正则")
            self.lbl_regex_result.setStyleSheet("color: #64748b;")
            return

        try:
            compiled = re.compile(pattern)
            if not sample:
                self.lbl_regex_result.setText("语法正确")
                self.lbl_regex_result.setStyleSheet("color: #0284c7;")
            elif compiled.search(sample):
                self.lbl_regex_result.setText("匹配成功")
                self.lbl_regex_result.setStyleSheet("color: #16a34a; font-weight: bold;")
            else:
                self.lbl_regex_result.setText("不匹配")
                self.lbl_regex_result.setStyleSheet("color: #ef4444; font-weight: bold;")
        except re.error:
            self.lbl_regex_result.setText("正则错误")
            self.lbl_regex_result.setStyleSheet("color: #dc2626;")


class WorkflowPipelineTab(QWidget):
    """Secondary Tab 2: Workflow Action Pipeline with full-height scroll area."""

    changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards: List[BaseActionCard] = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Action Toolbar Bar
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px;")
        bar_layout = QHBoxLayout(toolbar_frame)
        bar_layout.setContentsMargins(8, 6, 8, 6)
        bar_layout.setSpacing(8)

        bar_layout.addWidget(QLabel("<b>添加动作积木:</b>"))

        btn_add_extract = QPushButton("+ 提取单元格")
        btn_add_extract.clicked.connect(lambda: self.add_card_by_type("extract_cell"))
        bar_layout.addWidget(btn_add_extract)

        btn_add_http = QPushButton("+ 发网络请求")
        btn_add_http.clicked.connect(lambda: self.add_card_by_type("http_request"))
        bar_layout.addWidget(btn_add_http)

        btn_add_input = QPushButton("+ 用户输入")
        btn_add_input.clicked.connect(lambda: self.add_card_by_type("user_input"))
        bar_layout.addWidget(btn_add_input)

        btn_add_msg = QPushButton("+ 弹出提示框")
        btn_add_msg.clicked.connect(lambda: self.add_card_by_type("show_message"))
        bar_layout.addWidget(btn_add_msg)

        btn_add_toast = QPushButton("+ 弹出冒泡窗")
        btn_add_toast.clicked.connect(lambda: self.add_card_by_type("toast"))
        bar_layout.addWidget(btn_add_toast)

        btn_add_clip = QPushButton("+ 写入剪切板")
        btn_add_clip.clicked.connect(lambda: self.add_card_by_type("write_clipboard"))
        bar_layout.addWidget(btn_add_clip)

        btn_add_file = QPushButton("+ 文件读写")
        btn_add_file.clicked.connect(lambda: self.add_card_by_type("file_ops"))
        bar_layout.addWidget(btn_add_file)

        bar_layout.addStretch()

        self.lbl_step_count = QLabel("当前 0 个步骤")
        self.lbl_step_count.setStyleSheet("color: #0284c7; font-weight: bold; background: #e0f2fe; padding: 4px 8px; border-radius: 4px;")
        bar_layout.addWidget(self.lbl_step_count)

        layout.addWidget(toolbar_frame)

        # Full-height Scroll Area for cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #e2e8f0;
                background-color: #f8fafc;
                border-radius: 6px;
            }
        """)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)

        # VS Code style transparent overview ruler / minimap scrollbar
        self.vscode_scrollbar = VSCodeScrollBar(self.scroll_area, cards_getter=lambda: self.cards)
        self.scroll_area.setVerticalScrollBar(self.vscode_scrollbar)

        layout.addWidget(self.scroll_area)

    def add_card_by_type(self, action_type: str, config: Optional[Dict[str, Any]] = None):
        cfg = dict(config or {})
        cfg["action"] = action_type
        card = create_card_for_action(cfg)
        self.add_card(card)

    def add_card(self, card: BaseActionCard):
        card.changed.connect(self.changed.emit)
        card.delete_requested.connect(self.remove_card)
        card.move_up_requested.connect(self.move_card_up)
        card.move_down_requested.connect(self.move_card_down)
        card.clone_requested.connect(self.clone_card)

        self.cards.append(card)
        self.cards_layout.insertWidget(len(self.cards) - 1, card)
        self._renumber_steps()
        self.changed.emit()

    def remove_card(self, card: BaseActionCard):
        if card in self.cards:
            self.cards.remove(card)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
            self._renumber_steps()
            self.changed.emit()

    def move_card_up(self, card: BaseActionCard):
        idx = self.cards.index(card)
        if idx > 0:
            self.cards[idx], self.cards[idx - 1] = self.cards[idx - 1], self.cards[idx]
            self.cards_layout.removeWidget(card)
            self.cards_layout.insertWidget(idx - 1, card)
            self._renumber_steps()
            self.changed.emit()

    def move_card_down(self, card: BaseActionCard):
        idx = self.cards.index(card)
        if idx < len(self.cards) - 1:
            self.cards[idx], self.cards[idx + 1] = self.cards[idx + 1], self.cards[idx]
            self.cards_layout.removeWidget(card)
            self.cards_layout.insertWidget(idx + 1, card)
            self._renumber_steps()
            self.changed.emit()

    def clone_card(self, card: BaseActionCard):
        cfg = card.to_config()
        idx = self.cards.index(card)
        new_card = create_card_for_action(cfg)
        new_card.changed.connect(self.changed.emit)
        new_card.delete_requested.connect(self.remove_card)
        new_card.move_up_requested.connect(self.move_card_up)
        new_card.move_down_requested.connect(self.move_card_down)
        new_card.clone_requested.connect(self.clone_card)

        self.cards.insert(idx + 1, new_card)
        self.cards_layout.insertWidget(idx + 1, new_card)
        self._renumber_steps()
        self.changed.emit()

    def _renumber_steps(self):
        for i, card in enumerate(self.cards):
            card.set_step_number(i + 1)
            card.btn_up.setEnabled(i > 0)
            card.btn_down.setEnabled(i < len(self.cards) - 1)
        self.lbl_step_count.setText(f"当前共 {len(self.cards)} 个步骤")
        if hasattr(self, "vscode_scrollbar"):
            self.vscode_scrollbar.update()

    def clear_cards(self):
        for card in list(self.cards):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self._renumber_steps()
        if hasattr(self, "vscode_scrollbar"):
            self.vscode_scrollbar.update()


class BlockEditorWidget(QWidget):
    """Main Rule Editor Widget containing secondary tabs (Level 2 Menu).

    Tab 1: 触发前提配置 (Trigger Conditions)
    Tab 2: 触发后执行流程 (Workflow Pipeline)
    """

    rule_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._block_signals = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Secondary Level 2 Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-bottom: none;
                padding: 10px 22px;
                font-weight: 600;
                color: #475569;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0284c7;
                border-top: 3px solid #0284c7;
            }
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                background: #ffffff;
                border-radius: 4px;
            }
        """)

        # Tab 1: Trigger Conditions
        self.trigger_tab = TriggerConfigTab()
        self.trigger_tab.changed.connect(self._on_sub_changed)
        self.tabs.addTab(self.trigger_tab, "触发前提配置 (Trigger Conditions)")

        # Tab 2: Workflow Pipeline (Full-height Action Blocks)
        self.pipeline_tab = WorkflowPipelineTab()
        self.pipeline_tab.changed.connect(self._on_sub_changed)
        self.tabs.addTab(self.pipeline_tab, "触发后执行流程 (Workflow Pipeline)")

        layout.addWidget(self.tabs)

    # Expose cards list for compatibility with existing tests
    @property
    def cards(self) -> List[BaseActionCard]:
        return self.pipeline_tab.cards

    @property
    def edit_name(self) -> QLineEdit:
        return self.trigger_tab.edit_name

    @property
    def chk_enabled(self) -> QCheckBox:
        return self.trigger_tab.chk_enabled

    @property
    def spin_rows(self) -> QSpinBox:
        return self.trigger_tab.spin_rows

    @property
    def spin_cols(self) -> QSpinBox:
        return self.trigger_tab.spin_cols

    @property
    def chk_extra(self) -> QCheckBox:
        return self.trigger_tab.chk_extra

    @property
    def spin_cond_row(self) -> QSpinBox:
        return self.trigger_tab.spin_cond_row

    @property
    def spin_cond_col(self) -> QSpinBox:
        return self.trigger_tab.spin_cond_col

    @property
    def edit_regex(self) -> QLineEdit:
        return self.trigger_tab.edit_regex

    @property
    def scroll_area(self) -> QScrollArea:
        return self.pipeline_tab.scroll_area

    @property
    def cards_container(self) -> QWidget:
        return self.pipeline_tab.cards_container

    def move_card_up(self, card: BaseActionCard):
        self.pipeline_tab.move_card_up(card)

    def move_card_down(self, card: BaseActionCard):
        self.pipeline_tab.move_card_down(card)

    def clone_card(self, card: BaseActionCard):
        self.pipeline_tab.clone_card(card)

    def remove_card(self, card: BaseActionCard):
        self.pipeline_tab.remove_card(card)

    def _on_sub_changed(self):
        if not self._block_signals:
            self.rule_changed.emit()

    def load_rule(self, rule: RuleConfig):
        """Populate both secondary tabs from a RuleConfig model."""
        self._block_signals = True
        try:
            # Load Trigger Tab
            self.trigger_tab.edit_name.setText(rule.name)
            self.trigger_tab.chk_enabled.setChecked(rule.enabled)
            self.trigger_tab.spin_rows.setValue(rule.table_size[0])
            self.trigger_tab.spin_cols.setValue(rule.table_size[1])

            if rule.extra_condition and rule.extra_condition.regex:
                self.trigger_tab.chk_extra.setChecked(True)
                self.trigger_tab.extra_container.setVisible(True)
                self.trigger_tab.spin_cond_row.setValue(rule.extra_condition.row)
                self.trigger_tab.spin_cond_col.setValue(rule.extra_condition.col)
                self.trigger_tab.edit_regex.setText(rule.extra_condition.regex)
            else:
                self.trigger_tab.chk_extra.setChecked(False)
                self.trigger_tab.extra_container.setVisible(False)

            # Load Pipeline Tab
            self.pipeline_tab.clear_cards()
            for act_cfg in rule.workflow:
                card = create_card_for_action(act_cfg)
                self.pipeline_tab.add_card(card)

        finally:
            self._block_signals = False

    def to_rule(self) -> RuleConfig:
        """Construct a RuleConfig model from the current editor state."""
        extra_cond = None
        if self.trigger_tab.chk_extra.isChecked():
            extra_cond = ExtraCondition(
                row=self.trigger_tab.spin_cond_row.value(),
                col=self.trigger_tab.spin_cond_col.value(),
                regex=self.trigger_tab.edit_regex.text().strip(),
            )

        workflow = [card.to_config() for card in self.pipeline_tab.cards]

        return RuleConfig(
            name=self.trigger_tab.edit_name.text().strip() or "未命名规则",
            table_size=(self.trigger_tab.spin_rows.value(), self.trigger_tab.spin_cols.value()),
            extra_condition=extra_cond,
            workflow=workflow,
            enabled=self.trigger_tab.chk_enabled.isChecked(),
        )
