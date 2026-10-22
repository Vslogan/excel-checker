"""JSON source code editor with two-way synchronization."""
from __future__ import annotations

import json
from typing import Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.config_model import RuleConfig


class JsonEditorWidget(QWidget):
    """Widget for inspecting, editing, and two-way synchronizing rule JSON."""

    apply_requested = pyqtSignal(RuleConfig)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Toolbar
        bar_layout = QHBoxLayout()
        bar_layout.addWidget(QLabel("<b>JSON 模式:</b>"))

        self.combo_format = QComboBox()
        self.combo_format.addItems(["标准字段 (English Keys)", "中文自然字段 (Chinese Keys)"])
        self.combo_format.currentIndexChanged.connect(self._on_format_changed)
        bar_layout.addWidget(self.combo_format)

        bar_layout.addStretch()

        self.btn_apply = QPushButton("从 JSON 应用到可视化积木")
        self.btn_apply.setProperty("id", "primaryBtn")
        self.btn_apply.setToolTip("将当前 JSON 代码解析并同步刷新到积木编辑器")
        self.btn_apply.clicked.connect(self._apply_to_visual)
        bar_layout.addWidget(self.btn_apply)

        self.btn_format = QPushButton("格式化 JSON")
        self.btn_format.clicked.connect(self._format_json)
        bar_layout.addWidget(self.btn_format)

        layout.addLayout(bar_layout)

        # Code editor
        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.editor)

        self.current_rule: Optional[RuleConfig] = None

    def set_rule(self, rule: RuleConfig):
        """Update JSON display from RuleConfig."""
        self.current_rule = rule
        use_chinese = self.combo_format.currentIndex() == 1
        d = rule.to_dict(use_chinese_keys=use_chinese)
        self.editor.setPlainText(json.dumps(d, ensure_ascii=False, indent=2))

    def _on_format_changed(self):
        if self.current_rule:
            self.set_rule(self.current_rule)

    def _format_json(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        try:
            d = json.loads(text)
            self.editor.setPlainText(json.dumps(d, ensure_ascii=False, indent=2))
        except Exception as e:
            QMessageBox.warning(self, "JSON 格式错误", f"无法解析 JSON: {e}")

    def _apply_to_visual(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        try:
            data = json.loads(text)
            rule = RuleConfig.from_dict(data)
            errors = rule.validate()
            if errors:
                err_text = "\n• " + "\n• ".join(errors)
                QMessageBox.warning(self, "配置校验未通过", f"检测到以下配置问题:{err_text}")
                return
            self.current_rule = rule
            self.apply_requested.emit(rule)
            QMessageBox.information(self, "成功", "已成功从 JSON 同步到积木编辑器！")
        except Exception as e:
            QMessageBox.critical(self, "JSON 解析失败", f"语法错误: {e}")
