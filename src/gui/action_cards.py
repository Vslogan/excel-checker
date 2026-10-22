"""Visual block cards for workflow actions (Low-Code Block Programming style)."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.actions.extract_cell import parse_cell_position


class BaseActionCard(QFrame):
    """Base class for all action cards in the visual block editor."""

    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)
    move_up_requested = pyqtSignal(object)
    move_down_requested = pyqtSignal(object)
    clone_requested = pyqtSignal(object)

    action_type = "base"
    display_title = "基础积木"
    color_border = "#0284c7"

    def __init__(self, config: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName(f"card_{self.action_type}_{abs(id(self))}")
        self.setStyleSheet(f"""
            QFrame#{self.objectName()} {{
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-left: 5px solid {self.color_border};
                border-radius: 8px;
                padding: 4px;
            }}
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 8, 10, 10)
        self.main_layout.setSpacing(8)

        # Header bar
        self.header_layout = QHBoxLayout()
        self.title_label = QLabel(f"<b>{self.display_title}</b>")
        self.title_label.setStyleSheet(f"color: {self.color_border}; font-size: 13px;")
        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()

        # Action buttons
        self.btn_up = QPushButton("▲ 上移")
        self.btn_up.setToolTip("将该积木向上移动")
        self.btn_up.clicked.connect(lambda: self.move_up_requested.emit(self))
        self.header_layout.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ 下移")
        self.btn_down.setToolTip("将该积木向下移动")
        self.btn_down.clicked.connect(lambda: self.move_down_requested.emit(self))
        self.header_layout.addWidget(self.btn_down)

        self.btn_clone = QPushButton("复制")
        self.btn_clone.setToolTip("克隆该动作积木")
        self.btn_clone.clicked.connect(lambda: self.clone_requested.emit(self))
        self.header_layout.addWidget(self.btn_clone)

        self.btn_del = QPushButton("删除")
        self.btn_del.setToolTip("删除该动作积木")
        self.btn_del.setProperty("id", "dangerBtn")
        self.btn_del.clicked.connect(lambda: self.delete_requested.emit(self))
        self.header_layout.addWidget(self.btn_del)

        self.main_layout.addLayout(self.header_layout)

        # Body container
        self.body_widget = QWidget()
        self.form_layout = QFormLayout(self.body_widget)
        self.form_layout.setContentsMargins(0, 4, 0, 0)
        self.form_layout.setSpacing(6)
        self.main_layout.addWidget(self.body_widget)

        self.setup_ui()
        if config:
            self.load_config(config)

    def set_step_number(self, num: int):
        self.title_label.setText(f"<b>第 {num} 步 · {self.display_title}</b>")

    def setup_ui(self):
        """Override to add specific fields."""
        pass

    def load_config(self, config: Dict[str, Any]):
        """Override to load values into widgets."""
        pass

    def to_config(self) -> Dict[str, Any]:
        """Override to export configuration dict."""
        return {"action": self.action_type}


class ExtractCellCard(BaseActionCard):
    """Card for extracting cell value."""
    action_type = "extract_cell"
    display_title = "提取单元格 (Extract Cell)"
    color_border = "#0ea5e9"

    def setup_ui(self):
        pos_layout = QHBoxLayout()
        self.spin_row = QSpinBox()
        self.spin_row.setRange(0, 9999)
        self.spin_row.setPrefix("行: ")
        self.spin_row.valueChanged.connect(self.changed.emit)

        self.spin_col = QSpinBox()
        self.spin_col.setRange(0, 9999)
        self.spin_col.setPrefix("列: ")
        self.spin_col.valueChanged.connect(self.changed.emit)

        pos_layout.addWidget(self.spin_row)
        pos_layout.addWidget(self.spin_col)
        self.form_layout.addRow("单元格位置 (0-based):", pos_layout)

        self.edit_var = QLineEdit("id")
        self.edit_var.setPlaceholderText("存储到的变量名，如: id")
        self.edit_var.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("暂存变量名:", self.edit_var)

        tip = QLabel("<font color='#64748b'>提取指定行列单元格文本，供后续流程使用 {{变量名}} 引用</font>")
        tip.setWordWrap(True)
        self.form_layout.addRow("", tip)

    def load_config(self, config: Dict[str, Any]):
        pos = config.get("position") or config.get("操作位置") or [0, 0]
        r, c = parse_cell_position(pos)
        self.spin_row.setValue(r)
        self.spin_col.setValue(c)
        var = config.get("variable") or config.get("暂存到的变量名") or "id"
        self.edit_var.setText(str(var))

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "extract_cell",
            "position": [self.spin_row.value(), self.spin_col.value()],
            "variable": self.edit_var.text().strip(),
        }


class HttpRequestCard(BaseActionCard):
    """Card for HTTP network request."""
    action_type = "http_request"
    display_title = "发网络请求 (HTTP Request)"
    color_border = "#6366f1"

    def setup_ui(self):
        method_url_layout = QHBoxLayout()
        self.combo_method = QComboBox()
        self.combo_method.addItems(["GET", "POST", "PUT", "DELETE", "PATCH"])
        self.combo_method.currentTextChanged.connect(self.changed.emit)
        method_url_layout.addWidget(self.combo_method, 1)

        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("如: https://example.com/api/user/{{id}} (支持 {{变量}})")
        self.edit_url.textChanged.connect(self.changed.emit)
        method_url_layout.addWidget(self.edit_url, 4)
        self.form_layout.addRow("请求地址 (URL):", method_url_layout)

        self.edit_headers = QLineEdit()
        self.edit_headers.setPlaceholderText('JSON 格式, 如: {"Content-Type": "application/json"}')
        self.edit_headers.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("请求头 (Headers):", self.edit_headers)

        self.edit_body = QTextEdit()
        self.edit_body.setMaximumHeight(70)
        self.edit_body.setPlaceholderText('请求体 (支持 {{变量}})，如: {"id": "{{id}}"}')
        self.edit_body.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("请求体 (Body):", self.edit_body)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(100, 120000)
        self.spin_timeout.setSingleStep(1000)
        self.spin_timeout.setValue(10000)
        self.spin_timeout.setSuffix(" ms")
        self.spin_timeout.valueChanged.connect(self.changed.emit)
        self.form_layout.addRow("超时时间 (Timeout):", self.spin_timeout)

        # Callback mapping
        self.edit_callback = QLineEdit()
        self.edit_callback.setPlaceholderText('变量映射 JSON, 如: {"newData": "res.data[0]"}')
        self.edit_callback.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("回调提取 (Callback):", self.edit_callback)

        tip = QLabel("<font color='#64748b'>同步等待请求完成并按回调映射提取 JSON 字段；若超时或错误将终止后续流程并提示</font>")
        tip.setWordWrap(True)
        self.form_layout.addRow("", tip)

    def load_config(self, config: Dict[str, Any]):
        method = config.get("method") or config.get("方法") or "GET"
        idx = self.combo_method.findText(method.upper())
        if idx >= 0:
            self.combo_method.setCurrentIndex(idx)

        url = config.get("url") or config.get("URL") or ""
        self.edit_url.setText(str(url))

        headers = config.get("headers") or config.get("header") or config.get("请求头") or {}
        if isinstance(headers, dict):
            self.edit_headers.setText(json.dumps(headers, ensure_ascii=False) if headers else "")
        else:
            self.edit_headers.setText(str(headers))

        body = config.get("body") or config.get("请求体")
        if body is not None:
            self.edit_body.setText(json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, (dict, list)) else str(body))
        else:
            self.edit_body.clear()

        timeout = config.get("timeout") or config.get("超时时间") or 10000
        from src.core.actions.http_request import parse_timeout_seconds
        self.spin_timeout.setValue(int(parse_timeout_seconds(timeout) * 1000))

        callback = config.get("callback") or config.get("回调处理") or {}
        if isinstance(callback, dict):
            self.edit_callback.setText(json.dumps(callback, ensure_ascii=False) if callback else "")
        else:
            self.edit_callback.setText(str(callback))

    def to_config(self) -> Dict[str, Any]:
        headers_val = {}
        h_str = self.edit_headers.text().strip()
        if h_str:
            try:
                headers_val = json.loads(h_str)
            except Exception:
                headers_val = h_str

        cb_val = {}
        cb_str = self.edit_callback.text().strip()
        if cb_str:
            try:
                cb_val = json.loads(cb_str)
            except Exception:
                cb_val = cb_str

        body_str = self.edit_body.toPlainText().strip()
        body_val = body_str if body_str else None

        return {
            "action": "http_request",
            "method": self.combo_method.currentText(),
            "url": self.edit_url.text().strip(),
            "headers": headers_val,
            "body": body_val,
            "timeout": self.spin_timeout.value(),
            "callback": cb_val,
        }


class UserInputCard(BaseActionCard):
    """Card for user prompt input."""
    action_type = "user_input"
    display_title = "用户输入 (User Input Alert)"
    color_border = "#f59e0b"

    def setup_ui(self):
        self.edit_prompt = QLineEdit("请输入要提取第几个")
        self.edit_prompt.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("提示文本 (Prompt):", self.edit_prompt)

        self.edit_var = QLineEdit("index")
        self.edit_var.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("保存到的变量名:", self.edit_var)

        self.edit_default = QLineEdit("")
        self.edit_default.setPlaceholderText("可选默认值")
        self.edit_default.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("输入默认值:", self.edit_default)

        tip = QLabel("<font color='#64748b'>执行到该步骤会弹出模态对话框，由用户输入并存入变量</font>")
        self.form_layout.addRow("", tip)

    def load_config(self, config: Dict[str, Any]):
        p = config.get("prompt") or config.get("提示文本") or "请输入要提取第几个"
        self.edit_prompt.setText(str(p))
        v = config.get("variable") or config.get("变量名") or "index"
        self.edit_var.setText(str(v))
        d = config.get("default") or config.get("默认值") or ""
        self.edit_default.setText(str(d))

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "user_input",
            "prompt": self.edit_prompt.text(),
            "variable": self.edit_var.text().strip(),
            "default": self.edit_default.text(),
        }


class ShowMessageCard(BaseActionCard):
    """Card for message popup alert."""
    action_type = "show_message"
    display_title = "弹出提示框 (Show Message)"
    color_border = "#10b981"

    def setup_ui(self):
        self.edit_title = QLineEdit("处理结果提示")
        self.edit_title.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("弹窗标题:", self.edit_title)

        self.edit_content = QTextEdit()
        self.edit_content.setMaximumHeight(70)
        self.edit_content.setPlaceholderText("如: 新内容为: {{newData}}，用户选择: {{index}}")
        self.edit_content.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("提示内容 (支持 {{变量}}):", self.edit_content)

    def load_config(self, config: Dict[str, Any]):
        t = config.get("title") or config.get("标题") or "提示"
        self.edit_title.setText(str(t))
        c = config.get("content") or config.get("内容") or ""
        self.edit_content.setText(str(c))

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "show_message",
            "title": self.edit_title.text().strip(),
            "content": self.edit_content.toPlainText().strip(),
        }


class WriteClipboardCard(BaseActionCard):
    """Card for writing back to clipboard."""
    action_type = "write_clipboard"
    display_title = "写入剪切板 (Write Clipboard)"
    color_border = "#ec4899"

    def setup_ui(self):
        self.combo_type = QComboBox()
        self.combo_type.addItems(["table", "text"])
        self.combo_type.currentTextChanged.connect(self.changed.emit)
        self.form_layout.addRow("写入格式类型:", self.combo_type)

        self.edit_data = QTextEdit()
        self.edit_data.setMaximumHeight(80)
        self.edit_data.setPlaceholderText("支持 {{变量}}。若选择 table，在此输入逗号分隔 CSV，例如:\n{{id}},{{newData}},{{index}}")
        self.edit_data.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("写入数据内容:", self.edit_data)

        tip = QLabel("<font color='#64748b'>若选择 table 类型，会将 CSV 逗号分割数据解析并以 Excel 原生表格格式 (TSV) 写入系统剪切板，粘贴时直接分列分行！</font>")
        tip.setWordWrap(True)
        self.form_layout.addRow("", tip)

    def load_config(self, config: Dict[str, Any]):
        t = (config.get("type") or config.get("类型") or "text").lower()
        idx = self.combo_type.findText(t)
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)
        d = config.get("data") or config.get("数据") or config.get("内容") or ""
        self.edit_data.setText(str(d))

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "write_clipboard",
            "type": self.combo_type.currentText(),
            "data": self.edit_data.toPlainText(),
        }


class FileOpsCard(BaseActionCard):
    """Card for file operations."""
    action_type = "file_ops"
    display_title = "文件读写 (File Ops)"
    color_border = "#8b5cf6"

    def setup_ui(self):
        self.combo_op = QComboBox()
        self.combo_op.addItems(["write", "read", "append"])
        self.combo_op.currentTextChanged.connect(self.changed.emit)
        self.form_layout.addRow("文件操作类型:", self.combo_op)

        self.edit_path = QLineEdit("./output/log_{{id}}.txt")
        self.edit_path.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("文件路径:", self.edit_path)

        self.edit_content = QTextEdit()
        self.edit_content.setMaximumHeight(60)
        self.edit_content.setPlaceholderText("写入内容 (支持 {{变量}})")
        self.edit_content.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("写入内容 / 目标变量:", self.edit_content)

    def load_config(self, config: Dict[str, Any]):
        op = config.get("operation") or config.get("操作") or "write"
        idx = self.combo_op.findText(str(op).lower())
        if idx >= 0:
            self.combo_op.setCurrentIndex(idx)
        p = config.get("path") or config.get("文件路径") or ""
        self.edit_path.setText(str(p))
        c = config.get("content") or config.get("内容") or config.get("variable") or ""
        self.edit_content.setText(str(c))

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "file_ops",
            "operation": self.combo_op.currentText(),
            "path": self.edit_path.text().strip(),
            "content": self.edit_content.toPlainText(),
        }


def create_card_for_action(action_config: Dict[str, Any], parent: Optional[QWidget] = None) -> BaseActionCard:
    """Factory creating appropriate action card for config."""
    act_type = (
        action_config.get("action")
        or action_config.get("动作")
        or action_config.get("action_type")
        or action_config.get("type")
        or "extract_cell"
    )

    card_map = {
        "extract_cell": ExtractCellCard,
        "提取某一格": ExtractCellCard,
        "提取单元格": ExtractCellCard,
        "http_request": HttpRequestCard,
        "发网络请求": HttpRequestCard,
        "网络请求": HttpRequestCard,
        "user_input": UserInputCard,
        "用户输入": UserInputCard,
        "show_message": ShowMessageCard,
        "弹出提示框": ShowMessageCard,
        "write_clipboard": WriteClipboardCard,
        "写入剪切板": WriteClipboardCard,
        "file_ops": FileOpsCard,
        "文件读写": FileOpsCard,
    }

    card_cls = card_map.get(str(act_type), ExtractCellCard)
    return card_cls(action_config, parent=parent)
