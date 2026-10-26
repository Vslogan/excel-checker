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


def create_svg_drag_handle_button() -> QToolButton:
    """Create a sleek SVG grip/drag handle button with 6 dots."""
    btn = QToolButton()
    btn.setFixedSize(22, 22)
    btn.setCursor(Qt.SizeAllCursor)
    btn.setAutoRaise(True)
    btn.setToolTip("按住拖拽积木：拖动重新排序；拖至右侧滚动条快速定位；拖至左侧删除积木")

    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
      <circle cx="5" cy="4" r="1.5" fill="#94a3b8"/>
      <circle cx="11" cy="4" r="1.5" fill="#94a3b8"/>
      <circle cx="5" cy="8" r="1.5" fill="#94a3b8"/>
      <circle cx="11" cy="8" r="1.5" fill="#94a3b8"/>
      <circle cx="5" cy="12" r="1.5" fill="#94a3b8"/>
      <circle cx="11" cy="12" r="1.5" fill="#94a3b8"/>
    </svg>"""

    try:
        from PyQt5.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        btn.setIcon(QIcon(pix))
    except Exception:
        btn.setText("⋮⋮")

    btn.setStyleSheet("""
        QToolButton {
            border: 1px solid transparent;
            border-radius: 4px;
            background-color: transparent;
            padding: 0;
            margin-right: 4px;
        }
        QToolButton:hover {
            background-color: #f1f5f9;
            border-color: #cbd5e1;
        }
    """)
    return btn


class DummyButton:
    """Dummy button stub for backward compatibility with tests/code referencing btn_up/btn_down."""
    def __init__(self):
        self._enabled = True

    def setEnabled(self, enabled: bool):
        self._enabled = enabled

    def isEnabled(self) -> bool:
        return self._enabled


class BaseActionCard(QFrame):
    """Base class for all action cards in the visual block editor."""

    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)
    move_up_requested = pyqtSignal(object)
    move_down_requested = pyqtSignal(object)
    clone_requested = pyqtSignal(object)
    drag_initiated = pyqtSignal(object, object)  # (card, mouse_press_event)
    drag_moved = pyqtSignal(object, object)      # (card, mouse_move_event)
    drag_released = pyqtSignal(object, object)   # (card, mouse_release_event)

    action_type = "base"
    display_title = "基础积木"
    color_border = "#0284c7"

    def __init__(self, config: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.step_number: int = 1
        self._indent_level: int = 0
        self._branch_type: Optional[str] = None
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

        # SVG Drag Handle on the far left
        self.btn_drag = create_svg_drag_handle_button()
        self.btn_drag.installEventFilter(self)
        self.header_layout.addWidget(self.btn_drag)

        # Title label
        self.title_label = QLabel(f"<b>{self.display_title}</b>")
        self.title_label.setStyleSheet(f"color: {self.color_border}; font-size: 13px;")
        self.header_layout.addWidget(self.title_label)

        # Branch Badge (for Scratch-style IF / ELSE indent)
        self.badge_branch = QLabel("")
        self.badge_branch.setVisible(False)
        self.header_layout.addWidget(self.badge_branch)

        # SVG Exclamation Mark Tip Button
        self.btn_tip = create_svg_tip_button()
        self.header_layout.addWidget(self.btn_tip)
        self.header_layout.addStretch()

        # Backward compatibility dummies for up/down
        self.btn_up = DummyButton()
        self.btn_down = DummyButton()

        # Clone button
        self.btn_clone = QPushButton("复制")
        self.btn_clone.setToolTip("克隆该动作积木")
        self.btn_clone.clicked.connect(lambda: self.clone_requested.emit(self))
        self.header_layout.addWidget(self.btn_clone)

        # Delete button
        self.btn_del = QPushButton("删除")
        self.btn_del.setToolTip("删除该动作积木")
        self.btn_del.setProperty("id", "dangerBtn")
        self.btn_del.setStyleSheet("QPushButton { color: #dc2626; border-color: #fca5a5; } QPushButton:hover { background-color: #fee2e2; }")
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

    def eventFilter(self, obj, event):
        """Forward mouse press, move, release on drag handle to initiate dragging."""
        if obj == self.btn_drag:
            t = event.type()
            if t == event.MouseButtonPress and event.button() == Qt.LeftButton:
                self.drag_initiated.emit(self, event)
                return True
            elif t == event.MouseMove and (event.buttons() & Qt.LeftButton):
                self.drag_moved.emit(self, event)
                return True
            elif t == event.MouseButtonRelease and event.button() == Qt.LeftButton:
                self.drag_released.emit(self, event)
                return True
        return super().eventFilter(obj, event)

    def set_indent_level(self, level: int = 0, branch_type: Optional[str] = None):
        """Apply Scratch-style indented wrapping and left colored connector border."""
        self._indent_level = level
        self._branch_type = branch_type

        if level > 0 and branch_type == "if":
            margin_left = 28 * level
            self.badge_branch.setText(" IF 分支 ")
            self.badge_branch.setStyleSheet("background-color: #fef3c7; color: #b45309; font-weight: bold; font-size: 11px; border-radius: 4px; padding: 2px 6px; margin-left: 6px;")
            self.badge_branch.setVisible(True)
            self.setStyleSheet(f"""
                QFrame#{self.objectName()} {{
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-left: 6px solid #f59e0b;
                    border-radius: 8px;
                    padding: 4px;
                    margin-left: {margin_left}px;
                }}
            """)
        elif level > 0 and branch_type == "else":
            margin_left = 28 * level
            self.badge_branch.setText(" ELSE 分支 ")
            self.badge_branch.setStyleSheet("background-color: #ffedd5; color: #c2410c; font-weight: bold; font-size: 11px; border-radius: 4px; padding: 2px 6px; margin-left: 6px;")
            self.badge_branch.setVisible(True)
            self.setStyleSheet(f"""
                QFrame#{self.objectName()} {{
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-left: 6px solid #ea580c;
                    border-radius: 8px;
                    padding: 4px;
                    margin-left: {margin_left}px;
                }}
            """)
        else:
            self.badge_branch.setVisible(False)
            self.setStyleSheet(f"""
                QFrame#{self.objectName()} {{
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-left: 5px solid {self.color_border};
                    border-radius: 8px;
                    padding: 4px;
                    margin-left: 0px;
                }}
            """)

    def set_step_number(self, num: int):
        self.step_number = num
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


class ComputeCard(BaseActionCard):
    """Card for Compute action (Arithmetic, Logic, Built-in Functions)."""
    action_type = "compute"
    display_title = "计算 (Compute / Assignment)"
    color_border = "#8b5cf6"

    def setup_ui(self):
        tip = (
            "<b>计算 (Compute)</b><br/>"
            "输入左值变量名与右值复杂计算表达式：<br/>"
            "• <b>四则运算与取模</b>: +, -, *, /, % (自动转换数字，默认最大保留6位非零小数)<br/>"
            "• <b>逻辑与比较运算</b>: && (与), || (或), ! (非), ==, !=, &lt;, &lt;=, &gt;, &gt;= (结果严格非零即一)<br/>"
            "• <b>内置函数</b>: round(x, [n]), ceil(x), floor(x), str(x), substr(s, start, [len]), strcat(s1, s2, ...)<br/>"
            "• 支持小括号优先级，例如: round({{price}} * 1.05 + ceil(total / 2), 2)"
        )
        self.btn_tip.setToolTip(tip)

        self.edit_target_var = QLineEdit()
        self.edit_target_var.setPlaceholderText("例如: res, count, final_price")
        self.edit_target_var.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("左值 (结果变量名):", self.edit_target_var)

        self.edit_expression = QLineEdit()
        self.edit_expression.setPlaceholderText("例如: round({{price}} * {{count}} * 1.05, 2) 或 i + 1")
        self.edit_expression.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("右值 (计算表达式):", self.edit_expression)

    def load_config(self, config: Dict[str, Any]):
        t = (
            config.get("target_var")
            or config.get("variable")
            or config.get("var")
            or config.get("左值")
            or config.get("左值变量名")
            or config.get("变量名")
            or ""
        )
        self.edit_target_var.setText(str(t))
        e = (
            config.get("expression")
            or config.get("expr")
            or config.get("右值")
            or config.get("复杂的右值")
            or config.get("表达式")
            or config.get("计算表达式")
            or ""
        )
        self.edit_expression.setText(str(e))

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "compute",
            "target_var": self.edit_target_var.text().strip(),
            "expression": self.edit_expression.text().strip(),
        }


class IfElseCard(BaseActionCard):
    """Card for If-Else conditional branch with Scratch-like wrapping."""
    action_type = "if_else"
    display_title = "如果 (If - 条件分支)"
    color_border = "#f59e0b"

    def setup_ui(self):
        tip = (
            "<b>如果 (If-Else 条件分支)</b><br/>"
            "输入条件表达式进行逻辑选择：<br/>"
            "• 若计算结果非零 (True)，依次执行 IF 分支内积木，完成后自动跳过 ELSE 分支。<br/>"
            "• 若计算结果为 0 (False)，跳过 IF 分支，或进入 ELSE 分支（若开启）。<br/>"
            "• 支持在分支内使用 Goto 实现灵活循环与跳转。"
        )
        self.btn_tip.setToolTip(tip)

        self.edit_condition = QLineEdit()
        self.edit_condition.setPlaceholderText("例如: val > 100 或 count == 0 或 (a > 0 && b < 5)")
        self.edit_condition.textChanged.connect(self._update_summary)
        self.form_layout.addRow("IF 条件表达式:", self.edit_condition)

        # Has else checkbox
        self.chk_has_else = QCheckBox("包含 ELSE 分支 (否则)")
        self.chk_has_else.toggled.connect(self._on_else_toggled)
        self.form_layout.addRow("分支选项:", self.chk_has_else)

        # Spinners layout
        counts_layout = QHBoxLayout()
        counts_layout.addWidget(QLabel("IF 包含积木数:"))
        self.spin_then_count = QSpinBox()
        self.spin_then_count.setRange(0, 99)
        self.spin_then_count.setValue(1)
        self.spin_then_count.valueChanged.connect(self._update_summary)
        counts_layout.addWidget(self.spin_then_count)

        self.lbl_else_count = QLabel("ELSE 包含积木数:")
        counts_layout.addWidget(self.lbl_else_count)
        self.spin_else_count = QSpinBox()
        self.spin_else_count.setRange(0, 99)
        self.spin_else_count.setValue(1)
        self.spin_else_count.setEnabled(False)
        self.spin_else_count.valueChanged.connect(self._update_summary)
        counts_layout.addWidget(self.spin_else_count)

        counts_layout.addStretch()
        self.form_layout.addRow("分支范围:", counts_layout)

        # Summary guidance label
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #b45309; background: #fef3c7; border: 1px dashed #fcd34d; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        self.form_layout.addRow("", self.lbl_summary)

        self._update_summary()

    def _on_else_toggled(self, checked: bool):
        self.spin_else_count.setEnabled(checked)
        self._update_summary()

    def _update_summary(self):
        then_cnt = self.spin_then_count.value()
        has_else = self.chk_has_else.isChecked()
        else_cnt = self.spin_else_count.value() if has_else else 0
        cond = self.edit_condition.text().strip() or "条件"

        if has_else:
            text = f"结构: 如果 [{cond}] 成立 → 执行紧随其后的 {then_cnt} 个积木；否则 → 执行再之后的 {else_cnt} 个积木"
        else:
            text = f"结构: 如果 [{cond}] 成立 → 执行紧随其后的 {then_cnt} 个积木；否则 → 直接跳过继续向下执行"
        self.lbl_summary.setText(text)
        self.changed.emit()

    def load_config(self, config: Dict[str, Any]):
        cond = config.get("condition") or config.get("cond") or config.get("if条件") or config.get("条件") or ""
        self.edit_condition.setText(str(cond))
        has_else = bool(
            config.get("has_else", False)
            or config.get("else", False)
            or config.get("包含else", False)
            or config.get("是否有else", False)
        )
        self.chk_has_else.setChecked(has_else)
        then_cnt = int(
            config.get("then_count")
            or config.get("if_count")
            or config.get("if下面有多少个积木")
            or config.get("if积木数")
            or 1
        )
        self.spin_then_count.setValue(then_cnt)
        else_cnt = int(
            config.get("else_count")
            or config.get("else下面有多少个积木")
            or config.get("else积木数")
            or 1
        )
        self.spin_else_count.setValue(else_cnt)
        self._update_summary()

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "if_else",
            "condition": self.edit_condition.text().strip(),
            "has_else": self.chk_has_else.isChecked(),
            "then_count": self.spin_then_count.value(),
            "else_count": self.spin_else_count.value() if self.chk_has_else.isChecked() else 0,
        }


class GotoCard(BaseActionCard):
    """Card for Goto conditional/unconditional jump."""
    action_type = "goto"
    display_title = "跳转 (Goto / Loop Jump)"
    color_border = "#ef4444"

    def setup_ui(self):
        tip = (
            "<b>跳转 (Goto)</b><br/>"
            "流程控制与循环跳转：<br/>"
            "• <b>跳转条件</b>: 表达式计算结果非零时执行跳转；为 0 时跳过并顺序执行下一步。<br/>"
            "• 默认填 '1' 即为无条件强制跳转。<br/>"
            "• <b>目标行号</b>: 步骤编号 (从 1 开始计数)，支持向前跳转形成循环，或向后跳转跳过特定步骤。"
        )
        self.btn_tip.setToolTip(tip)

        self.edit_condition = QLineEdit()
        self.edit_condition.setText("1")
        self.edit_condition.setPlaceholderText("例如: i <= 5 或 1 (无条件跳转)")
        self.edit_condition.textChanged.connect(self.changed.emit)
        self.form_layout.addRow("跳转条件 (非零跳转):", self.edit_condition)

        self.spin_target = QSpinBox()
        self.spin_target.setRange(1, 9999)
        self.spin_target.setValue(1)
        self.spin_target.valueChanged.connect(self.changed.emit)
        self.form_layout.addRow("目标行号 (Step):", self.spin_target)

    def load_config(self, config: Dict[str, Any]):
        c = (
            config.get("condition")
            or config.get("cond")
            or config.get("条件")
            or config.get("跳转条件")
            or "1"
        )
        self.edit_condition.setText(str(c))
        t = (
            config.get("target_line")
            or config.get("target")
            or config.get("line")
            or config.get("行号")
            or config.get("目标行号")
            or 1
        )
        try:
            self.spin_target.setValue(int(float(str(t))))
        except Exception:
            self.spin_target.setValue(1)

    def to_config(self) -> Dict[str, Any]:
        return {
            "action": "goto",
            "condition": self.edit_condition.text().strip() or "1",
            "target_line": self.spin_target.value(),
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
        "compute": ComputeCard,
        "calculate": ComputeCard,
        "计算": ComputeCard,
        "赋值": ComputeCard,
        "if_else": IfElseCard,
        "if": IfElseCard,
        "如果": IfElseCard,
        "条件选择": IfElseCard,
        "goto": GotoCard,
        "跳转": GotoCard,
        "跳转行号": GotoCard,
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
