"""Visual block cards for workflow actions (Low-Code Block Programming style)."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QByteArray, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.core.actions.extract_cell import parse_cell_position


def create_svg_tip_button(tip_text: str = "") -> QToolButton:
    """Create a crisp circular exclamation mark button using SVG with hover tooltip."""
    btn = QToolButton()
    btn.setFixedSize(20, 20)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setAutoRaise(True)

    # Crisp vector SVG for exclamation mark in a circle
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
      <circle cx="12" cy="12" r="10" fill="#f0f9ff" stroke="#0284c7" stroke-width="2"/>
      <line x1="12" y1="7" x2="12" y2="13" stroke="#0284c7" stroke-width="2.4" stroke-linecap="round"/>
      <circle cx="12" cy="17" r="1.3" fill="#0284c7"/>
    </svg>"""

    try:
        from PyQt5.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pix = QPixmap(18, 18)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        renderer.render(p)
        p.end()
        btn.setIcon(QIcon(pix))
    except Exception:
        btn.setText("!")

    btn.setStyleSheet("""
        QToolButton {
            border: 1px solid #bae6fd;
            border-radius: 10px;
            background-color: #f0f9ff;
            color: #0284c7;
            font-weight: bold;
            font-size: 11px;
            padding: 0;
            margin-left: 6px;
        }
        QToolButton:hover {
            background-color: #e0f2fe;
            border-color: #0284c7;
        }
    """)
    if tip_text:
        btn.setToolTip(tip_text)
    return btn


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

        # SVG Exclamation Mark Tip Button
        self.btn_tip = create_svg_tip_button()
        self.header_layout.addWidget(self.btn_tip)
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

    def set_tip_text(self, tip_text: str):
        """Set the tooltip on the SVG exclamation mark button."""
        if tip_text:
            self.btn_tip.setToolTip(tip_text)
            self.btn_tip.setVisible(True)
        else:
            self.btn_tip.setVisible(False)

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
        self.set_tip_text("提取指定行列坐标单元格文本，存入变量供后续流程使用 {{变量名}} 引用")

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
        self.set_tip_text("同步等待网络接口返回并按回调映射提取 JSON 字段；若超时或发生网络错误将终止后续流程并弹窗报警")

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
        self.edit_body.setMaximumHeight(65)
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
        self.set_tip_text("执行到该步骤会弹出模态对话框，阻塞等待用户输入文字并存入指定上下文变量")

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
        self.set_tip_text("弹出标准提示对话框展示处理结果，支持使用 {{变量名}} 动态插值")

        self.edit_title = QLineEdit("处理结果提示")
        self.edit_title.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("弹窗标题:", self.edit_title)

        self.edit_content = QTextEdit()
        self.edit_content.setMaximumHeight(65)
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


class ToastCard(BaseActionCard):
    """Card for floating toast notification."""
    action_type = "toast"
    display_title = "弹出冒泡窗 (Toast Notification)"
    color_border = "#06b6d4"

    def setup_ui(self):
        self.set_tip_text("弹出轻量级半透明浮动冒泡窗；可配置停留时长、是否阻塞流程、显示屏幕位置或持续跟随鼠标移动")

        self.edit_content = QTextEdit()
        self.edit_content.setMaximumHeight(60)
        self.edit_content.setPlaceholderText("输入冒泡提示内容 (支持 {{变量}}，若为空则跳过不显示)")
        self.edit_content.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("提示内容 (支持空):", self.edit_content)

        # Duration & Blocking in one row
        timing_row = QHBoxLayout()
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(200, 60000)
        self.spin_duration.setSingleStep(500)
        self.spin_duration.setValue(2000)
        self.spin_duration.setSuffix(" ms")
        self.spin_duration.valueChanged.connect(self.changed.emit)
        timing_row.addWidget(self.spin_duration)

        self.chk_blocking = QCheckBox("阻塞模式 (等待弹窗消失才执行下一步)")
        self.chk_blocking.setChecked(False)
        self.chk_blocking.toggled.connect(self.changed.emit)
        timing_row.addWidget(self.chk_blocking)
        timing_row.addStretch()
        self.form_layout.addRow("持续时间与阻塞:", timing_row)

        # Screen & Position
        pos_row = QHBoxLayout()
        self.combo_screen = QComboBox()
        self.combo_screen.addItem("鼠标所在屏幕", "cursor")
        self.combo_screen.addItem("所有屏幕", "all")
        self.combo_screen.currentIndexChanged.connect(self.changed.emit)
        pos_row.addWidget(self.combo_screen, 1)

        self.combo_position = QComboBox()
        self.combo_position.addItem("底部居中", "bottom_center")
        self.combo_position.addItem("顶部居中", "top_center")
        self.combo_position.addItem("正中间", "center")
        self.combo_position.addItem("持续跟随鼠标", "follow_mouse")
        self.combo_position.currentIndexChanged.connect(self._on_position_changed)
        self.combo_position.currentIndexChanged.connect(self.changed.emit)
        pos_row.addWidget(self.combo_position, 1)

        self.lbl_follow_tip = QLabel("<font color='#0284c7'>[跟随鼠标移动]</font>")
        self.lbl_follow_tip.setVisible(False)
        pos_row.addWidget(self.lbl_follow_tip)

        self.form_layout.addRow("显示屏幕与位置:", pos_row)

    def _on_position_changed(self):
        is_follow = self.combo_position.currentData() == "follow_mouse"
        self.combo_screen.setEnabled(not is_follow)
        self.lbl_follow_tip.setVisible(is_follow)

    def load_config(self, config: Dict[str, Any]):
        c = (
            config.get("content")
            if "content" in config
            else config.get("内容", "数据已处理完成")
        )
        self.edit_content.setText(str(c) if c is not None else "")

        from src.core.actions.toast import parse_duration_ms
        d = config.get("duration") or config.get("持续时间") or 2000
        self.spin_duration.setValue(parse_duration_ms(d))

        b = bool(config.get("blocking", config.get("是否阻塞", False)))
        self.chk_blocking.setChecked(b)

        scr = str(config.get("screen") or config.get("显示的屏幕") or "cursor").lower()
        idx_scr = 1 if scr in ("all", "所有屏幕") else 0
        self.combo_screen.setCurrentIndex(idx_scr)

        pos = str(config.get("position") or config.get("显示的位置") or "bottom_center").lower()
        pos_map = {
            "bottom_center": 0, "底部居中": 0,
            "top_center": 1, "顶部居中": 1,
            "center": 2, "正中间": 2,
            "follow_mouse": 3, "持续跟随鼠标": 3, "跟随鼠标": 3
        }
        self.combo_position.setCurrentIndex(pos_map.get(pos, 0))
        self._on_position_changed()

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "toast",
            "content": self.edit_content.toPlainText(),
            "duration": self.spin_duration.value(),
            "blocking": self.chk_blocking.isChecked(),
            "screen": self.combo_screen.currentData(),
            "position": self.combo_position.currentData(),
        }


class WriteClipboardCard(BaseActionCard):
    """Card for writing back to clipboard."""
    action_type = "write_clipboard"
    display_title = "写入剪切板 (Write Clipboard)"
    color_border = "#ec4899"

    def setup_ui(self):
        self.set_tip_text("若选择 table 类型，会将 CSV 逗号分割数据解析并以 Excel 原生表格格式 (TSV) 写入系统剪切板，粘贴时直接分列分行！")

        self.combo_type = QComboBox()
        self.combo_type.addItems(["table", "text"])
        self.combo_type.currentTextChanged.connect(self.changed.emit)
        self.form_layout.addRow("写入格式类型:", self.combo_type)

        self.edit_data = QTextEdit()
        self.edit_data.setMaximumHeight(70)
        self.edit_data.setPlaceholderText("支持 {{变量}}。若选择 table，在此输入逗号分隔 CSV，例如:\n{{id}},{{newData}},{{index}}")
        self.edit_data.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("写入数据内容:", self.edit_data)

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
        self.set_tip_text("执行本地文件读取、覆盖写入或末尾追加操作，路径与内容均支持 {{变量}}")

        self.combo_op = QComboBox()
        self.combo_op.addItems(["write", "read", "append"])
        self.combo_op.currentTextChanged.connect(self.changed.emit)
        self.form_layout.addRow("文件操作类型:", self.combo_op)

        self.edit_path = QLineEdit("./output/log_{{id}}.txt")
        self.edit_path.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("文件路径:", self.edit_path)

        self.edit_content = QTextEdit()
        self.edit_content.setMaximumHeight(55)
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
        "toast": ToastCard,
        "弹出冒泡窗": ToastCard,
        "冒泡窗": ToastCard,
        "write_clipboard": WriteClipboardCard,
        "写入剪切板": WriteClipboardCard,
        "file_ops": FileOpsCard,
        "文件读写": FileOpsCard,
    }

    card_cls = card_map.get(str(act_type), ExtractCellCard)
    return card_cls(action_config, parent=parent)
