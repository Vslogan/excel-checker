"""Visual Block Editor widget for editing trigger rules and action pipelines."""
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


class BlockEditorWidget(QWidget):
    """Low-code style visual block editor for configuring rules."""

    rule_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards: List[BaseActionCard] = []
        self._block_signals: bool = False
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 1. Trigger Predicates GroupBox
        trigger_group = QGroupBox("触发前提条件配置 (Trigger Conditions)")
        trigger_layout = QVBoxLayout(trigger_group)
        trigger_layout.setSpacing(8)

        # Rule Name & Enabled
        meta_layout = QHBoxLayout()
        meta_layout.addWidget(QLabel("<b>规则名称:</b>"))
        self.edit_name = QLineEdit("新建表格检查规则")
        self.edit_name.textChanged.connect(self._on_changed)
        meta_layout.addWidget(self.edit_name, 3)

        self.chk_enabled = QCheckBox("启用该规则")
        self.chk_enabled.setChecked(True)
        self.chk_enabled.toggled.connect(self._on_changed)
        meta_layout.addWidget(self.chk_enabled, 1)
        trigger_layout.addLayout(meta_layout)

        # Dimensions
        dim_layout = QHBoxLayout()
        dim_layout.addWidget(QLabel("<b>复制表格大小 (必须):</b>"))

        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 9999)
        self.spin_rows.setValue(1)
        self.spin_rows.setPrefix("行数: ")
        self.spin_rows.valueChanged.connect(self._on_changed)
        dim_layout.addWidget(self.spin_rows)

        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 9999)
        self.spin_cols.setValue(1)
        self.spin_cols.setPrefix("列数: ")
        self.spin_cols.valueChanged.connect(self._on_changed)
        dim_layout.addWidget(self.spin_cols)

        dim_tip = QLabel("<font color='#0284c7'>提示：普通纯文本复制将统一兼容视为 1x1 表格</font>")
        dim_layout.addWidget(dim_tip)
        dim_layout.addStretch()
        trigger_layout.addLayout(dim_layout)

        # Extra condition
        extra_group = QGroupBox("额外条件 (可选)")
        extra_layout = QVBoxLayout(extra_group)
        extra_layout.setContentsMargins(10, 8, 10, 8)

        cond_header_layout = QHBoxLayout()
        self.chk_extra = QCheckBox("启用额外单元格格式匹配")
        self.chk_extra.setChecked(False)
        self.chk_extra.toggled.connect(self._on_extra_toggled)
        cond_header_layout.addWidget(self.chk_extra)
        extra_layout.addLayout(cond_header_layout)

        self.extra_fields_widget = QWidget()
        extra_form = QFormLayout(self.extra_fields_widget)
        extra_form.setContentsMargins(0, 4, 0, 0)
        extra_form.setSpacing(6)

        pos_box = QHBoxLayout()
        self.spin_cond_row = QSpinBox()
        self.spin_cond_row.setRange(0, 9999)
        self.spin_cond_row.setPrefix("第 ")
        self.spin_cond_row.setSuffix(" 行")
        self.spin_cond_row.valueChanged.connect(self._on_changed)

        self.spin_cond_col = QSpinBox()
        self.spin_cond_col.setRange(0, 9999)
        self.spin_cond_col.setPrefix("第 ")
        self.spin_cond_col.setSuffix(" 列 (0-based)")
        self.spin_cond_col.valueChanged.connect(self._on_changed)

        pos_box.addWidget(self.spin_cond_row)
        pos_box.addWidget(self.spin_cond_col)
        pos_box.addStretch()
        extra_form.addRow("目标单元格位置:", pos_box)

        # Regex pattern & live tester
        regex_layout = QHBoxLayout()
        self.edit_regex = QLineEdit("[0-9]{3,}")
        self.edit_regex.setPlaceholderText("正则表达式，例如: [0-9]{3,}")
        self.edit_regex.textChanged.connect(self._test_live_regex)
        self.edit_regex.textChanged.connect(self._on_changed)
        regex_layout.addWidget(self.edit_regex, 3)

        self.edit_test_input = QLineEdit()
        self.edit_test_input.setPlaceholderText("实时测试输入...")
        self.edit_test_input.textChanged.connect(self._test_live_regex)
        regex_layout.addWidget(self.edit_test_input, 2)

        self.lbl_regex_result = QLabel("待测试")
        self.lbl_regex_result.setStyleSheet("color: #64748b; font-weight: bold;")
        regex_layout.addWidget(self.lbl_regex_result)

        extra_form.addRow("正则表达式规则:", regex_layout)
        extra_layout.addWidget(self.extra_fields_widget)
        self.extra_fields_widget.setVisible(False)

        trigger_layout.addWidget(extra_group)
        main_layout.addWidget(trigger_group, 0)

        # 2. Workflow Action Blocks Section
        workflow_group = QGroupBox("触发后的执行流程 (Workflow Action Pipeline)")
        wf_layout = QVBoxLayout(workflow_group)
        wf_layout.setSpacing(8)

        # Action Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("<b>添加动作积木:</b>"))

        btn_add_extract = QPushButton("+ 提取单元格")
        btn_add_extract.clicked.connect(lambda: self.add_card_by_type("extract_cell"))
        toolbar_layout.addWidget(btn_add_extract)

        btn_add_http = QPushButton("+ 发网络请求")
        btn_add_http.clicked.connect(lambda: self.add_card_by_type("http_request"))
        toolbar_layout.addWidget(btn_add_http)

        btn_add_input = QPushButton("+ 用户输入")
        btn_add_input.clicked.connect(lambda: self.add_card_by_type("user_input"))
        toolbar_layout.addWidget(btn_add_input)

        btn_add_msg = QPushButton("+ 弹出提示框")
        btn_add_msg.clicked.connect(lambda: self.add_card_by_type("show_message"))
        toolbar_layout.addWidget(btn_add_msg)

        btn_add_clip = QPushButton("+ 写入剪切板")
        btn_add_clip.clicked.connect(lambda: self.add_card_by_type("write_clipboard"))
        toolbar_layout.addWidget(btn_add_clip)

        btn_add_file = QPushButton("+ 文件读写")
        btn_add_file.clicked.connect(lambda: self.add_card_by_type("file_ops"))
        toolbar_layout.addWidget(btn_add_file)

        toolbar_layout.addStretch()
        wf_layout.addLayout(toolbar_layout)

        # Scroll area for cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        self.scroll_area.setWidget(self.cards_container)
        wf_layout.addWidget(self.scroll_area)

        main_layout.addWidget(workflow_group, 1)

    def _on_extra_toggled(self, checked: bool):
        self.extra_fields_widget.setVisible(checked)
        self._on_changed()

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
                self.lbl_regex_result.setText("✅ 匹配成功")
                self.lbl_regex_result.setStyleSheet("color: #16a34a; font-weight: bold;")
            else:
                self.lbl_regex_result.setText("❌ 不匹配")
                self.lbl_regex_result.setStyleSheet("color: #ef4444; font-weight: bold;")
        except re.error as e:
            self.lbl_regex_result.setText("⚠️ 正则错误")
            self.lbl_regex_result.setStyleSheet("color: #dc2626;")

    def _on_changed(self):
        if not self._block_signals:
            self.rule_changed.emit()

    def add_card_by_type(self, action_type: str, config: Optional[Dict[str, Any]] = None):
        cfg = dict(config or {})
        cfg["action"] = action_type
        card = create_card_for_action(cfg)
        self.add_card(card)

    def add_card(self, card: BaseActionCard):
        card.changed.connect(self._on_changed)
        card.delete_requested.connect(self.remove_card)
        card.move_up_requested.connect(self.move_card_up)
        card.move_down_requested.connect(self.move_card_down)
        card.clone_requested.connect(self.clone_card)

        self.cards.append(card)
        # Insert before the trailing stretch
        self.cards_layout.insertWidget(len(self.cards) - 1, card)
        self._renumber_steps()
        self._on_changed()

    def remove_card(self, card: BaseActionCard):
        if card in self.cards:
            self.cards.remove(card)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
            self._renumber_steps()
            self._on_changed()

    def move_card_up(self, card: BaseActionCard):
        idx = self.cards.index(card)
        if idx > 0:
            self.cards[idx], self.cards[idx - 1] = self.cards[idx - 1], self.cards[idx]
            self.cards_layout.removeWidget(card)
            self.cards_layout.insertWidget(idx - 1, card)
            self._renumber_steps()
            self._on_changed()

    def move_card_down(self, card: BaseActionCard):
        idx = self.cards.index(card)
        if idx < len(self.cards) - 1:
            self.cards[idx], self.cards[idx + 1] = self.cards[idx + 1], self.cards[idx]
            self.cards_layout.removeWidget(card)
            self.cards_layout.insertWidget(idx + 1, card)
            self._renumber_steps()
            self._on_changed()

    def clone_card(self, card: BaseActionCard):
        cfg = card.to_config()
        idx = self.cards.index(card)
        new_card = create_card_for_action(cfg)
        new_card.changed.connect(self._on_changed)
        new_card.delete_requested.connect(self.remove_card)
        new_card.move_up_requested.connect(self.move_card_up)
        new_card.move_down_requested.connect(self.move_card_down)
        new_card.clone_requested.connect(self.clone_card)

        self.cards.insert(idx + 1, new_card)
        self.cards_layout.insertWidget(idx + 1, new_card)
        self._renumber_steps()
        self._on_changed()

    def _renumber_steps(self):
        for i, card in enumerate(self.cards):
            card.set_step_number(i + 1)
            card.btn_up.setEnabled(i > 0)
            card.btn_down.setEnabled(i < len(self.cards) - 1)

    def clear_cards(self):
        for card in list(self.cards):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

    def load_rule(self, rule: RuleConfig):
        """Populate the editor from a RuleConfig model."""
        self._block_signals = True
        try:
            self.edit_name.setText(rule.name)
            self.chk_enabled.setChecked(rule.enabled)
            self.spin_rows.setValue(rule.table_size[0])
            self.spin_cols.setValue(rule.table_size[1])

            if rule.extra_condition and rule.extra_condition.regex:
                self.chk_extra.setChecked(True)
                self.extra_fields_widget.setVisible(True)
                self.spin_cond_row.setValue(rule.extra_condition.row)
                self.spin_cond_col.setValue(rule.extra_condition.col)
                self.edit_regex.setText(rule.extra_condition.regex)
            else:
                self.chk_extra.setChecked(False)
                self.extra_fields_widget.setVisible(False)

            self.clear_cards()
            for act_cfg in rule.workflow:
                card = create_card_for_action(act_cfg)
                card.changed.connect(self._on_changed)
                card.delete_requested.connect(self.remove_card)
                card.move_up_requested.connect(self.move_card_up)
                card.move_down_requested.connect(self.move_card_down)
                card.clone_requested.connect(self.clone_card)

                self.cards.append(card)
                self.cards_layout.insertWidget(len(self.cards) - 1, card)

            self._renumber_steps()
        finally:
            self._block_signals = False

    def to_rule(self) -> RuleConfig:
        """Construct a RuleConfig model from the current editor state."""
        extra_cond = None
        if self.chk_extra.isChecked():
            extra_cond = ExtraCondition(
                row=self.spin_cond_row.value(),
                col=self.spin_cond_col.value(),
                regex=self.edit_regex.text().strip(),
            )

        workflow = [card.to_config() for card in self.cards]

        return RuleConfig(
            name=self.edit_name.text().strip() or "未命名规则",
            table_size=(self.spin_rows.value(), self.spin_cols.value()),
            extra_condition=extra_cond,
            workflow=workflow,
            enabled=self.chk_enabled.isChecked(),
        )
