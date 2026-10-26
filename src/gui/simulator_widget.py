"""Table Simulator and Workflow Test Runner widget."""
from __future__ import annotations

import json
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.config_model import RuleConfig
from src.core.context import HeadlessUIDelegate
from src.core.engine import WorkflowEngine
from src.core.table_parser import TableData


class SimulatorWidget(QWidget):
    """Interactive simulator panel for testing rules against clipboard tables."""

    def __init__(self, engine: WorkflowEngine, get_current_rule_fn: Callable[[], RuleConfig], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.get_current_rule = get_current_rule_fn
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Vertical)

        # Top: Input panel
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        input_header = QHBoxLayout()
        input_header.addWidget(QLabel("<b>模拟剪切板输入 (文本 / TSV / 表格):</b>"))
        input_header.addStretch()

        self.btn_paste_clip = QPushButton("粘贴系统当前剪切板")
        self.btn_paste_clip.clicked.connect(self._paste_from_system)
        input_header.addWidget(self.btn_paste_clip)

        self.btn_sample_1x1 = QPushButton("样例: 888 (1x1)")
        self.btn_sample_1x1.clicked.connect(lambda: self.input_edit.setPlainText("888"))
        input_header.addWidget(self.btn_sample_1x1)

        self.btn_sample_2x2 = QPushButton("样例: 2x2 表格")
        self.btn_sample_2x2.clicked.connect(lambda: self.input_edit.setPlainText("ORDER-100\tAlice\tVIP\r\nORDER-101\tBob\tNormal"))
        input_header.addWidget(self.btn_sample_2x2)

        top_layout.addLayout(input_header)

        self.input_edit = QPlainTextEdit("888")
        self.input_edit.setMaximumHeight(110)
        self.input_edit.textChanged.connect(self._update_table_info)
        top_layout.addWidget(self.input_edit)

        # Info bar & Run button
        action_bar = QHBoxLayout()
        self.lbl_table_info = QLabel("检测到尺寸: 1 行 x 1 列")
        self.lbl_table_info.setStyleSheet("font-weight: bold; color: #0284c7;")
        action_bar.addWidget(self.lbl_table_info)

        self.lbl_match_status = QLabel("待测试")
        self.lbl_match_status.setStyleSheet("color: #64748b; font-weight: bold;")
        action_bar.addWidget(self.lbl_match_status)

        action_bar.addStretch()

        self.btn_run = QPushButton("运行测试当前规则")
        self.btn_run.setProperty("id", "primaryBtn")
        self.btn_run.clicked.connect(self.run_simulation)
        action_bar.addWidget(self.btn_run)

        top_layout.addLayout(action_bar)
        splitter.addWidget(top_widget)

        # Bottom: Results panel
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        # Left of bottom: Variables table inspector
        var_group = QGroupBox("运行时上下文变量 (Variables Inspector)")
        var_layout = QVBoxLayout(var_group)
        self.table_vars = QTableWidget(0, 2)
        self.table_vars.setHorizontalHeaderLabels(["变量名", "变量值"])
        self.table_vars.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_vars.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        var_layout.addWidget(self.table_vars)
        bottom_layout.addWidget(var_group, 1)

        # Right of bottom: Execution Log & Output Clipboard
        res_group = QGroupBox("执行跟踪日志与最终剪切板产物")
        res_layout = QVBoxLayout(res_group)

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setProperty("id", "logConsole")
        res_layout.addWidget(QLabel("执行日志:"), 0)
        res_layout.addWidget(self.log_console, 2)

        res_layout.addWidget(QLabel("写入剪切板的内容:"), 0)
        self.clipboard_output = QPlainTextEdit()
        self.clipboard_output.setReadOnly(True)
        self.clipboard_output.setMaximumHeight(70)
        res_layout.addWidget(self.clipboard_output, 1)

        bottom_layout.addWidget(res_group, 1)
        splitter.addWidget(bottom_widget)

        main_layout.addWidget(splitter)
        self._update_table_info()

    def _paste_from_system(self):
        clip = QApplication.clipboard()
        if clip:
            self.input_edit.setPlainText(clip.text())

    def _update_table_info(self):
        text = self.input_edit.toPlainText()
        table = TableData.from_text(text)
        self.lbl_table_info.setText(f"检测到尺寸: {table.rows} 行 x {table.cols} 列")

    def run_simulation(self):
        rule = self.get_current_rule()
        if not rule:
            QMessageBox.warning(self, "错误", "当前没有可运行的规则")
            return

        text = self.input_edit.toPlainText()
        table = TableData.from_text(text)

        # Check size match with fuzzy support
        if not table.matches_size(rule.table_size[0], rule.table_size[1], fuzzy_row=rule.fuzzy_row, fuzzy_col=rule.fuzzy_col):
            exp_r = "任意" if rule.fuzzy_row else str(rule.table_size[0])
            exp_c = "任意" if rule.fuzzy_col else str(rule.table_size[1])
            self.lbl_match_status.setText(f"❌ 尺寸不匹配 (期望 {exp_r}x{exp_c}, 实际 {table.rows}x{table.cols})")
            self.lbl_match_status.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.log_console.setPlainText(f"[跳过] 表格尺寸不符合规则要求: 期望 {exp_r}x{exp_c}，实际检测为 {table.rows}x{table.cols}")
            return

        # Check extra condition
        for idx, cond in enumerate(rule.extra_conditions):
            if not cond.matches(table):
                self.lbl_match_status.setText(f"❌ 额外正则条件未满足 (条件 {idx + 1})")
                self.lbl_match_status.setStyleSheet("color: #ef4444; font-weight: bold;")
                cell_val = table.get_cell(cond.row, cond.col)
                self.log_console.setPlainText(f"[跳过] 单元格 ({cond.row}, {cond.col}) 内容 '{cell_val}' 不匹配正则: '{cond.regex}'")
                return

        self.lbl_match_status.setText("✅ 触发条件全部满足，正在执行流程...")
        self.lbl_match_status.setStyleSheet("color: #16a34a; font-weight: bold;")

        # Delegate: simulate user prompts with default value or dialog
        delegate = HeadlessUIDelegate(predefined_inputs={
            "请输入要提取第几个": "1",
            "请输入要提取第几个索引 (例如: 1)": "1",
        })

        result = self.engine.execute_rule(rule, table, ui_delegate=delegate)

        # Update log
        full_logs = "\n".join(result.logs)
        self.log_console.setPlainText(full_logs)

        # Update clipboard output
        self.clipboard_output.setPlainText(delegate.get_clipboard())

        # Update variables table
        self.table_vars.setRowCount(0)
        for k, v in result.variables.items():
            if k.startswith("_"):
                continue
            row = self.table_vars.rowCount()
            self.table_vars.insertRow(row)
            self.table_vars.setItem(row, 0, QTableWidgetItem(str(k)))
            val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            self.table_vars.setItem(row, 1, QTableWidgetItem(val_str))

        if result.success:
            self.lbl_match_status.setText("🎉 流程全部执行成功！")
            self.lbl_match_status.setStyleSheet("color: #16a34a; font-weight: bold;")
        else:
            self.lbl_match_status.setText(f"⚠️ 执行中断: {result.error}")
            self.lbl_match_status.setStyleSheet("color: #dc2626; font-weight: bold;")
