"""PyQt5 desktop frontend for the spreadsheet rule engine.

Qt widgets and the Qt clipboard stay on the GUI thread. Clipboard polling uses
QTimer; rule execution (including synchronous HTTP) runs on a serial worker,
while prompts, notifications, and clipboard writes are marshalled back to Qt.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from PyQt5.QtCore import (
    QObject,
    QRunnable,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import QClipboard, QDesktopServices
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .builtin_actions import build_default_registry
from .clipboard import ClipboardMonitor
from .config import Rule, load_rule_file, save_rule_file
from .dispatcher import ProcessOutcome, RuleDispatcher
from .engine import ExecutionResult, RuleEngine
from .errors import ActionError, ConfigError, ExcelCheckerError
from .interfaces import ClipboardReadPort
from .repository import RuleRepository


@dataclass
class _UiRequest:
    kind: str
    message: str = ""
    text: str = ""
    result: str | None = None
    error: Exception | None = None
    event: threading.Event = field(default_factory=threading.Event)


class QtActionBridge(QObject):
    """Thread-safe port that asks the GUI thread to interact with the user."""

    prompt_requested = pyqtSignal(object)
    notification_requested = pyqtSignal(object)
    clipboard_requested = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None, *, wait_timeout: float = 3600.0) -> None:
        super().__init__(parent)
        self.wait_timeout = wait_timeout
        self._lock = threading.Lock()
        self._pending: dict[int, _UiRequest] = {}
        self._closed = False

    def prompt(self, message: str) -> str | None:
        request = _UiRequest(kind="prompt", message=message)
        self._dispatch(self.prompt_requested, request)
        return request.result

    def notify(self, message: str) -> None:
        request = _UiRequest(kind="notify", message=message)
        self._dispatch(self.notification_requested, request)

    def write_text(self, text: str) -> None:
        request = _UiRequest(kind="clipboard", text=text)
        self._dispatch(self.clipboard_requested, request)

    def _dispatch(self, signal: Any, request: _UiRequest) -> None:
        with self._lock:
            if self._closed:
                raise ActionError("应用正在关闭，无法继续执行交互动作")
            self._pending[id(request)] = request
        signal.emit(request)
        completed = request.event.wait(self.wait_timeout)
        with self._lock:
            self._pending.pop(id(request), None)
        if not completed:
            raise ActionError("等待桌面交互超时")
        if request.error is not None:
            raise ActionError(str(request.error)) from request.error

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            pending = tuple(self._pending.values())
        for request in pending:
            request.error = ActionError("应用已关闭")
            request.event.set()


class _QtClipboardReader(ClipboardReadPort):
    """QClipboard text reader; only called by the GUI-thread QTimer."""

    def __init__(self, clipboard: QClipboard) -> None:
        self._clipboard = clipboard

    def read_text(self) -> str:
        return self._clipboard.text(QClipboard.Clipboard)


class _JobSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, object)


class _RuleJob(QRunnable):
    def __init__(
        self, rule: Rule, table: list[list[str]], registry: Any, bridge: QtActionBridge
    ) -> None:
        super().__init__()
        self.rule = rule
        self.table = table
        self.registry = registry
        self.bridge = bridge
        self.signals = _JobSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            engine = RuleEngine(
                registry=self.registry,
                interaction=self.bridge,
                clipboard=self.bridge,
            )
            result = engine.execute(self.rule, self.table)
        except Exception as exc:  # noqa: BLE001 - worker boundary must report any action error
            self.signals.failed.emit(self.rule.name, exc)
        else:
            self.signals.finished.emit(result)


class QtActionRunner(QObject):
    """Serial queue for matched rules; an HTTP action cannot freeze the UI."""

    job_finished = pyqtSignal(object)
    job_failed = pyqtSignal(str, str)
    queue_warning = pyqtSignal(str)

    def __init__(
        self,
        registry: Any,
        bridge: QtActionBridge,
        parent: QObject | None = None,
        *,
        max_pending: int = 50,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.bridge = bridge
        self.max_pending = max_pending
        self._queue: deque[tuple[Rule, list[list[str]]]] = deque()
        self._running = False
        self._current_job: _RuleJob | None = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

    @property
    def pending_count(self) -> int:
        return len(self._queue) + (1 if self._running else 0)

    def enqueue(self, rule: Rule, table: list[list[str]]) -> bool:
        if self.pending_count >= self.max_pending:
            self.queue_warning.emit(f"待处理队列已满（{self.max_pending} 条），本次复制未排队")
            return False
        snapshot = [[str(cell) for cell in row] for row in table]
        self._queue.append((rule, snapshot))
        self._start_next()
        return True

    def clear_pending(self) -> None:
        self._queue.clear()

    def _start_next(self) -> None:
        if self._running or not self._queue:
            return
        rule, table = self._queue.popleft()
        self._running = True
        job = _RuleJob(rule, table, self.registry, self.bridge)
        job.signals.finished.connect(self._on_finished, Qt.QueuedConnection)
        job.signals.failed.connect(self._on_failed, Qt.QueuedConnection)
        self._current_job = job
        self._pool.start(job)

    def _on_finished(self, result: ExecutionResult) -> None:
        self._current_job = None
        self._running = False
        self.job_finished.emit(result)
        self._start_next()

    def _on_failed(self, rule_name: str, error: Exception) -> None:
        self._current_job = None
        self._running = False
        self.job_failed.emit(rule_name, str(error))
        self._start_next()


class _QueueingDispatcher:
    """Match on the GUI thread, then enqueue actual action execution."""

    def __init__(self, runner: QtActionRunner) -> None:
        self.runner = runner

    def process(self, table: list[list[str]], rules: tuple[Rule, ...]) -> ProcessOutcome:
        rule = RuleDispatcher.select_rule(table, rules)
        if rule is None:
            return ProcessOutcome(matched_rule=None, execution=None)
        if not self.runner.enqueue(rule, table):
            return ProcessOutcome(matched_rule=None, execution=None)
        # Execution is queued, not complete, so the monitor only reports a match.
        return ProcessOutcome(matched_rule=rule, execution=None)


class ActionEditorDialog(QDialog):
    """Form-based editor for built-ins, with a JSON page for plug-in actions."""

    _BUILTINS: ClassVar[frozenset[str]] = frozenset(
        {"extract_cell", "http_request", "user_input", "notify", "clipboard_write"}
    )

    def __init__(
        self,
        registry: Any,
        action: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.original_action = dict(action or {})
        self._forms: dict[str, dict[str, QWidget]] = {}
        self._pages: dict[str, QWidget] = {}
        self.setWindowTitle("编辑动作积木" if action else "添加动作积木")
        self.setMinimumWidth(610)
        self._build_ui()
        self._populate(action)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.kind_combo = QComboBox()
        for definition in self.registry.definitions():
            self.kind_combo.addItem(definition.label, definition.name)
        preferred = self.kind_combo.findData("extract_cell")
        if preferred >= 0:
            self.kind_combo.setCurrentIndex(preferred)
        form = QFormLayout()
        form.addRow("动作类型", self.kind_combo)
        layout.addLayout(form)

        self.stack = QWidget()
        self.stack_layout = QVBoxLayout(self.stack)
        self.stack_layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self.stack)

        for definition in self.registry.definitions():
            page = self._make_page(definition.name)
            self._pages[definition.name] = page
            self.stack_layout.addWidget(page)
            page.hide()
        self.kind_combo.currentIndexChanged.connect(self._show_selected_page)
        self._show_selected_page()

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._accept_action)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _plain_text(self, height: int = 90) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setMinimumHeight(height)
        editor.setMaximumHeight(max(height, 150))
        editor.setTabChangesFocus(False)
        return editor

    def _spin(self, maximum: int = 1000000) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, maximum)
        return spin

    def _make_page(self, action_name: str) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        fields: dict[str, QWidget] = {}
        self._forms[action_name] = fields

        def line(field: str, label: str, default: str = "") -> QLineEdit:
            widget = QLineEdit(default)
            fields[field] = widget
            layout.addRow(label, widget)
            return widget

        def plain(field: str, label: str, default: str = "", height: int = 90) -> QPlainTextEdit:
            widget = self._plain_text(height)
            widget.setPlainText(default)
            fields[field] = widget
            layout.addRow(label, widget)
            return widget

        if action_name == "extract_cell":
            row, column = self._spin(), self._spin()
            line("variable", "变量名", "value")
            fields["row"], fields["column"] = row, column
            layout.insertRow(0, "行（从 0 开始）", row)
            layout.insertRow(1, "列（从 0 开始）", column)
            return page

        if action_name == "http_request":
            method = QComboBox()
            method.setEditable(True)
            method.addItems(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
            fields["method"] = method
            layout.addRow("方法", method)
            line("url", "URL（支持 {{变量}}）", "https://")
            plain("headers", "Headers JSON", "{}", 76)
            plain("body", "Body（JSON 或文本）", "", 92)
            timeout = QSpinBox()
            timeout.setRange(1, 24 * 60 * 60 * 1000)
            timeout.setValue(10000)
            fields["timeout_ms"] = timeout
            layout.addRow("超时（毫秒）", timeout)
            plain("callback", "回调变量 → 路径 JSON", "{}", 76)
            return page

        if action_name == "user_input":
            plain("prompt", "提示文本（支持 {{变量}}）", "", 80)
            line("variable", "保存到变量", "value")
            return page

        if action_name == "notify":
            plain("message", "提示内容（支持 {{变量}}）", "", 110)
            return page

        if action_name == "clipboard_write":
            value_type = QComboBox()
            value_type.addItem("文本", "text")
            value_type.addItem("表格", "table")
            fields["type"] = value_type
            layout.addRow("写入类型", value_type)
            plain("data", "内容（JSON、CSV/TSV 或文本）", "", 145)
            return page

        # Registered plug-ins can be configured without adding a new Qt class.
        # Their handler validator remains the source of truth for the JSON form.
        editor = plain("plugin_json", "动作参数 JSON", '{"action": "' + action_name + '"}', 220)
        editor.setToolTip("输入完整动作 JSON；action 字段必须与上方动作类型相同。")
        return page

    def _show_selected_page(self, *_args: Any) -> None:
        for page in self._pages.values():
            page.hide()
        action_name = self.kind_combo.currentData()
        page = self._pages.get(action_name)
        if page is not None:
            page.show()

    @staticmethod
    def _json_text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_json_or_text(text: str, *, blank_value: Any = "") -> Any:
        if not text.strip():
            return blank_value
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def _populate(self, action: dict[str, Any] | None) -> None:
        if action:
            index = self.kind_combo.findData(action.get("action"))
            if index >= 0:
                self.kind_combo.setCurrentIndex(index)
        action_name = self.kind_combo.currentData()
        fields = self._forms.get(action_name, {})
        if action_name == "extract_cell":
            cell = action.get("cell", [0, 0]) if action else [0, 0]
            fields["row"].setValue(cell[0])
            fields["column"].setValue(cell[1])
            fields["variable"].setText(action.get("variable", "value") if action else "value")
        elif action_name == "http_request":
            method = fields["method"]
            method.setCurrentText(action.get("method", "POST") if action else "POST")
            fields["url"].setText(action.get("url", "https://") if action else "https://")
            fields["headers"].setPlainText(
                self._json_text(action.get("headers", {}), "{}") if action else "{}"
            )
            fields["body"].setPlainText(self._json_text(action.get("body"), "") if action else "")
            fields["timeout_ms"].setValue(action.get("timeout_ms", 10000) if action else 10000)
            fields["callback"].setPlainText(
                self._json_text(action.get("callback", {}), "{}") if action else "{}"
            )
        elif action_name == "user_input":
            fields["prompt"].setPlainText(action.get("prompt", "") if action else "")
            fields["variable"].setText(action.get("variable", "value") if action else "value")
        elif action_name == "notify":
            fields["message"].setPlainText(action.get("message", "") if action else "")
        elif action_name == "clipboard_write":
            index = fields["type"].findData(action.get("type", "text") if action else "text")
            fields["type"].setCurrentIndex(max(index, 0))
            data = action.get("data", "") if action else ""
            fields["data"].setPlainText(
                self._json_text(data) if not isinstance(data, str) else data
            )
        elif action_name not in self._BUILTINS:
            plugin_action = action or {"action": action_name}
            fields["plugin_json"].setPlainText(
                json.dumps(plugin_action, ensure_ascii=False, indent=2)
            )

    def _build_action(self) -> dict[str, Any]:
        action_name = self.kind_combo.currentData()
        fields = self._forms[action_name]
        if action_name == "extract_cell":
            action: dict[str, Any] = {
                "action": action_name,
                "cell": [fields["row"].value(), fields["column"].value()],
                "variable": fields["variable"].text().strip(),
            }
        elif action_name == "http_request":
            try:
                headers = json.loads(fields["headers"].toPlainText() or "{}")
                callback = json.loads(fields["callback"].toPlainText() or "{}")
            except json.JSONDecodeError as exc:
                raise ConfigError(f"Headers/Callback 不是有效 JSON：{exc.msg}") from exc
            body = self._read_json_or_text(fields["body"].toPlainText(), blank_value=None)
            action = {
                "action": action_name,
                "method": fields["method"].currentText().strip(),
                "url": fields["url"].text().strip(),
                "headers": headers,
                "body": body,
                "timeout_ms": fields["timeout_ms"].value(),
                "callback": callback,
            }
        elif action_name == "user_input":
            action = {
                "action": action_name,
                "prompt": fields["prompt"].toPlainText(),
                "variable": fields["variable"].text().strip(),
            }
        elif action_name == "notify":
            action = {"action": action_name, "message": fields["message"].toPlainText()}
        elif action_name == "clipboard_write":
            value_type = fields["type"].currentData()
            raw_data = fields["data"].toPlainText()
            data = raw_data if value_type == "text" else self._read_json_or_text(raw_data)
            action = {"action": action_name, "type": value_type, "data": data}
        else:
            try:
                action = json.loads(fields["plugin_json"].toPlainText())
            except json.JSONDecodeError as exc:
                raise ConfigError(f"动作 JSON 无效：{exc.msg}") from exc
            if not isinstance(action, dict):
                raise ConfigError("动作 JSON 必须是对象")
            action["action"] = action_name

        self.registry.validate(action)
        return action

    def _accept_action(self) -> None:
        try:
            self._build_action()
        except (ConfigError, ActionError) as exc:
            QMessageBox.warning(self, "动作配置有误", str(exc))
            return
        self.accept()

    def action_data(self) -> dict[str, Any]:
        return self._build_action()


class MainWindow(QMainWindow):
    def __init__(self, rules_directory: str | Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Excel Checker · 表格规则助手")
        self.resize(1180, 820)
        self.setMinimumSize(980, 680)
        self.settings = QSettings("ExcelChecker", "ExcelChecker")
        default_directory = Path.cwd() / "rules"
        configured = rules_directory or self.settings.value(
            "rules_dir", str(default_directory), type=str
        )
        self.rules_directory = Path(configured).expanduser().resolve()
        self.registry = build_default_registry()
        self.repository = RuleRepository(self.rules_directory, registry=self.registry)
        self._current_path: Path | None = None
        self._current_rule: Rule | None = None
        self._actions: list[dict[str, Any]] = []
        self._loading = False
        self._dirty = False
        self._expected_clipboard_write: str | None = None

        self._build_ui()
        self.bridge = QtActionBridge(self)
        self.bridge.prompt_requested.connect(self._handle_prompt, Qt.QueuedConnection)
        self.bridge.notification_requested.connect(self._handle_notification, Qt.QueuedConnection)
        self.bridge.clipboard_requested.connect(self._handle_clipboard_write, Qt.QueuedConnection)
        self.runner = QtActionRunner(self.registry, self.bridge, self)
        self.runner.job_finished.connect(self._job_finished)
        self.runner.job_failed.connect(self._job_failed)
        self.runner.queue_warning.connect(self._log_error)

        self.clipboard = QApplication.clipboard()
        self.monitor = self._make_monitor()
        self.clipboard.dataChanged.connect(self._on_clipboard_changed)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(250)
        self.poll_timer.timeout.connect(self._poll_clipboard)

        self._refresh_rule_list()
        self._log(f"规则目录：{self.rules_directory}")
        self._log("选择或新建规则后，可编辑触发条件与动作顺序。")
        self._show_repository_errors()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f4f6fa; }
            QGroupBox { font-weight: 600; border: 1px solid #dce2ec; border-radius: 8px; margin-top: 12px; padding: 10px; background: white; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #334155; }
            QPushButton { min-height: 30px; padding: 3px 10px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; }
            QPushButton:hover { background: #eef4ff; border-color: #7aa2f7; }
            QPushButton#primaryButton { color: white; background: #2563eb; border-color: #2563eb; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget, QListWidget { border: 1px solid #cbd5e1; border-radius: 5px; background: white; padding: 4px; }
            QPlainTextEdit { font-family: Consolas, Menlo, monospace; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #eef1f5; }
            QListWidget::item:selected { background: #e8f0ff; color: #1d4ed8; }
            QHeaderView::section { background: #f1f5f9; padding: 5px; border: 0; border-bottom: 1px solid #dce2ec; }
            """
        )

        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)
        self.monitor_checkbox = QCheckBox("监控剪切板")
        self.monitor_checkbox.setToolTip("开启后，符合规则的复制内容会自动执行对应动作。")
        toolbar.addWidget(self.monitor_checkbox)
        toolbar.addSeparator()
        self.monitor_status = QLabel("● 未监控")
        self.monitor_status.setStyleSheet("color: #64748b; font-weight: 600; padding: 0 8px;")
        toolbar.addWidget(self.monitor_status)
        toolbar.addSeparator()
        folder_action = QAction("打开规则目录", self)
        folder_action.triggered.connect(self._open_rules_directory)
        toolbar.addAction(folder_action)
        import_action = QAction("导入 JSON", self)
        import_action.triggered.connect(self._import_rule)
        toolbar.addAction(import_action)
        change_dir_action = QAction("切换目录…", self)
        change_dir_action.triggered.connect(self._choose_rules_directory)
        toolbar.addAction(change_dir_action)

        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        sidebar = QWidget()
        sidebar.setMinimumWidth(235)
        sidebar.setMaximumWidth(315)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 8, 12)
        sidebar_title = QLabel("我的规则")
        sidebar_title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #0f172a; padding: 2px;"
        )
        sidebar_layout.addWidget(sidebar_title)
        self.rule_list = QListWidget()
        self.rule_list.setSelectionMode(QListWidget.SingleSelection)
        self.rule_list.currentItemChanged.connect(self._on_rule_selection_changed)
        self.rule_list.itemChanged.connect(self._on_rule_item_changed)
        sidebar_layout.addWidget(self.rule_list, 1)

        rule_buttons = QHBoxLayout()
        self.add_rule_button = QPushButton("＋ 新建")
        self.add_rule_button.clicked.connect(self._new_rule)
        self.import_rule_button = QPushButton("导入")
        self.import_rule_button.clicked.connect(self._import_rule)
        rule_buttons.addWidget(self.add_rule_button)
        rule_buttons.addWidget(self.import_rule_button)
        sidebar_layout.addLayout(rule_buttons)
        self.remove_rule_button = QPushButton("删除选中规则")
        self.remove_rule_button.clicked.connect(self._remove_rule)
        sidebar_layout.addWidget(self.remove_rule_button)
        splitter.addWidget(sidebar)

        editor_root = QWidget()
        editor_layout = QVBoxLayout(editor_root)
        editor_layout.setContentsMargins(8, 12, 12, 12)
        header = QHBoxLayout()
        self.editor_title = QLabel("规则编辑器")
        self.editor_title.setStyleSheet("font-size: 21px; font-weight: 700; color: #0f172a;")
        header.addWidget(self.editor_title)
        header.addStretch(1)
        self.save_button = QPushButton("保存规则")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_current_rule)
        header.addWidget(self.save_button)
        editor_layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        editor_canvas = QWidget()
        canvas_layout = QVBoxLayout(editor_canvas)
        canvas_layout.setContentsMargins(2, 6, 2, 6)
        canvas_layout.setSpacing(10)
        scroll.setWidget(editor_canvas)
        editor_layout.addWidget(scroll, 1)

        basics = QGroupBox("基础设置")
        basics_form = QFormLayout(basics)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：订单号查询")
        self.enabled_edit = QCheckBox("启用此规则")
        self.priority_edit = QSpinBox()
        self.priority_edit.setRange(-100000, 100000)
        self.priority_edit.setToolTip("多条规则同时匹配时，优先级高的规则先执行。")
        basics_form.addRow("配置名称", self.name_edit)
        basics_form.addRow("状态", self.enabled_edit)
        basics_form.addRow("优先级", self.priority_edit)
        canvas_layout.addWidget(basics)

        trigger = QGroupBox("触发条件")
        trigger_layout = QVBoxLayout(trigger)
        size_form = QFormLayout()
        self.rows_edit = QSpinBox()
        self.rows_edit.setRange(1, 100000)
        self.columns_edit = QSpinBox()
        self.columns_edit.setRange(1, 100000)
        self.rows_edit.setValue(1)
        self.columns_edit.setValue(1)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("行数"))
        size_row.addWidget(self.rows_edit)
        size_row.addSpacing(16)
        size_row.addWidget(QLabel("列数"))
        size_row.addWidget(self.columns_edit)
        size_row.addStretch(1)
        size_form.addRow("复制表格大小（必须精确匹配）", size_row)
        trigger_layout.addLayout(size_form)
        trigger_layout.addWidget(QLabel("额外条件：单元格必须满足正则表达式；多个条件需同时满足。"))
        self.condition_table = QTableWidget(0, 3)
        self.condition_table.setHorizontalHeaderLabels(["行（0 起）", "列（0 起）", "正则表达式"])
        self.condition_table.horizontalHeader().setStretchLastSection(True)
        self.condition_table.setMinimumHeight(115)
        self.condition_table.setMaximumHeight(185)
        self.condition_table.itemChanged.connect(self._mark_dirty)
        trigger_layout.addWidget(self.condition_table)
        condition_buttons = QHBoxLayout()
        self.add_condition_button = QPushButton("添加条件")
        self.add_condition_button.clicked.connect(self._add_condition)
        self.remove_condition_button = QPushButton("删除条件")
        self.remove_condition_button.clicked.connect(self._remove_condition)
        condition_buttons.addWidget(self.add_condition_button)
        condition_buttons.addWidget(self.remove_condition_button)
        condition_buttons.addStretch(1)
        trigger_layout.addLayout(condition_buttons)
        canvas_layout.addWidget(trigger)

        actions_group = QGroupBox("执行流程 · 按顺序运行")
        actions_layout = QVBoxLayout(actions_group)
        self.action_list = QListWidget()
        self.action_list.setMinimumHeight(180)
        self.action_list.setMaximumHeight(285)
        self.action_list.itemDoubleClicked.connect(lambda _item: self._edit_action())
        actions_layout.addWidget(self.action_list)
        action_buttons = QHBoxLayout()
        self.add_action_button = QPushButton("＋ 添加动作积木")
        self.add_action_button.clicked.connect(self._add_action)
        self.edit_action_button = QPushButton("编辑")
        self.edit_action_button.clicked.connect(self._edit_action)
        self.remove_action_button = QPushButton("删除")
        self.remove_action_button.clicked.connect(self._remove_action)
        self.up_action_button = QPushButton("↑ 上移")
        self.up_action_button.clicked.connect(lambda: self._move_action(-1))
        self.down_action_button = QPushButton("↓ 下移")
        self.down_action_button.clicked.connect(lambda: self._move_action(1))
        for button in (
            self.add_action_button,
            self.edit_action_button,
            self.remove_action_button,
            self.up_action_button,
            self.down_action_button,
        ):
            action_buttons.addWidget(button)
        actions_layout.addLayout(action_buttons)
        canvas_layout.addWidget(actions_group)
        canvas_layout.addStretch(1)

        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setMaximumHeight(145)
        log_layout.addWidget(self.log_view)
        editor_layout.addWidget(log_group)
        splitter.addWidget(editor_root)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([265, 900])

        self.statusBar().showMessage("就绪")
        self.monitor_checkbox.toggled.connect(self._set_monitoring)
        for widget in (self.name_edit,):
            widget.textChanged.connect(self._mark_dirty)
        for widget in (self.enabled_edit,):
            widget.toggled.connect(self._mark_dirty)
        self.priority_edit.valueChanged.connect(self._mark_dirty)
        self.rows_edit.valueChanged.connect(self._mark_dirty)
        self.columns_edit.valueChanged.connect(self._mark_dirty)

    def _make_monitor(self) -> ClipboardMonitor:
        return ClipboardMonitor(
            _QtClipboardReader(QApplication.clipboard()),
            self.repository,
            _QueueingDispatcher(self.runner),
            interval_seconds=0.25,
            ignore_initial_clipboard=True,
            on_result=self._on_clipboard_outcome,
            on_error=self._on_monitor_error,
            on_config_error=self._on_config_errors,
        )

    def _mark_dirty(self, *_args: Any) -> None:
        if self._loading:
            return
        self._dirty = True
        self.save_button.setEnabled(True)
        self.statusBar().showMessage("有未保存的规则修改", 4000)

    def _conditions_from_table(self) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        for row in range(self.condition_table.rowCount()):
            row_item = self.condition_table.item(row, 0)
            column_item = self.condition_table.item(row, 1)
            regex_item = self.condition_table.item(row, 2)
            row_text = row_item.text().strip() if row_item is not None else ""
            column_text = column_item.text().strip() if column_item is not None else ""
            pattern = regex_item.text() if regex_item is not None else ""
            if not row_text and not column_text and not pattern:
                continue
            if (
                re.fullmatch(r"[0-9]+", row_text) is None
                or re.fullmatch(r"[0-9]+", column_text) is None
                or not pattern
            ):
                raise ConfigError(f"额外条件第 {row + 1} 行需要填写非负行列号和正则表达式")
            conditions.append({"cell": [int(row_text), int(column_text)], "regex": pattern})
        return conditions

    def _document_from_editor(self) -> dict[str, Any]:
        return {
            "version": 1,
            "name": self.name_edit.text().strip(),
            "enabled": self.enabled_edit.isChecked(),
            "priority": self.priority_edit.value(),
            "trigger": {
                "table_size": {
                    "rows": self.rows_edit.value(),
                    "columns": self.columns_edit.value(),
                },
                "conditions": self._conditions_from_table(),
            },
            "actions": [dict(action) for action in self._actions],
        }

    def _load_rule(self, path: Path) -> None:
        try:
            rule = load_rule_file(path, registry=self.registry)
        except ExcelCheckerError as exc:
            QMessageBox.warning(self, "无法加载规则", str(exc))
            return
        self._loading = True
        self._current_path = path
        self._current_rule = rule
        self.name_edit.setText(rule.name)
        self.enabled_edit.setChecked(rule.enabled)
        self.priority_edit.setValue(rule.priority)
        self.rows_edit.setValue(rule.table_rows)
        self.columns_edit.setValue(rule.table_columns)
        self.condition_table.setRowCount(0)
        for condition in rule.conditions:
            self._append_condition_row(condition.row, condition.column, condition.regex)
        self._actions = [dict(action) for action in rule.actions]
        self._refresh_action_list()
        self.editor_title.setText(f"规则编辑器 · {rule.name}")
        self._dirty = False
        self.save_button.setEnabled(False)
        self._loading = False

    def _refresh_rule_list(self, select_path: Path | None = None) -> None:
        self.repository.reload_if_changed(force=True)
        rules = self.repository.rules
        wanted = select_path or self._current_path
        self._loading = True
        self.rule_list.blockSignals(True)
        self.rule_list.clear()
        selected_item: QListWidgetItem | None = None
        for rule in rules:
            item = QListWidgetItem(rule.name)
            item.setData(Qt.UserRole, str(rule.source or ""))
            item.setFlags(
                item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
            )
            item.setCheckState(Qt.Checked if rule.enabled else Qt.Unchecked)
            if wanted is not None and rule.source == wanted:
                selected_item = item
            self.rule_list.addItem(item)
        if selected_item is not None:
            self.rule_list.setCurrentItem(selected_item)
        elif self.rule_list.count() > 0:
            selected_item = self.rule_list.item(0)
            self.rule_list.setCurrentItem(selected_item)
        self.rule_list.blockSignals(False)
        self._loading = False

        if selected_item is not None:
            path = Path(selected_item.data(Qt.UserRole))
            self._load_rule(path)
        else:
            self._clear_editor()

    def _clear_editor(self) -> None:
        self._loading = True
        self._current_path = None
        self._current_rule = None
        self._actions = []
        self.name_edit.clear()
        self.enabled_edit.setChecked(False)
        self.priority_edit.setValue(0)
        self.rows_edit.setValue(1)
        self.columns_edit.setValue(1)
        self.condition_table.setRowCount(0)
        self._refresh_action_list()
        self.editor_title.setText("规则编辑器 · 尚未选择规则")
        self._dirty = False
        self.save_button.setEnabled(False)
        self._loading = False

    def _refresh_action_list(self, selected_index: int | None = None) -> None:
        self.action_list.clear()
        for index, action in enumerate(self._actions):
            label = self._action_label(action.get("action", ""))
            summary = self._action_summary(action)
            item = QListWidgetItem(f"{index + 1:02d}  {label}\n      {summary}")
            item.setSizeHint(QSize(0, 56))
            item.setData(Qt.UserRole, index)
            self.action_list.addItem(item)
        if selected_index is not None and 0 <= selected_index < self.action_list.count():
            self.action_list.setCurrentRow(selected_index)

    def _action_label(self, name: str) -> str:
        try:
            return self.registry.get(name).label
        except ActionError:
            return name or "未知动作"

    @staticmethod
    def _action_summary(action: dict[str, Any]) -> str:
        name = action.get("action")
        if name == "extract_cell":
            cell = action.get("cell", ["?", "?"])
            return f"提取 ({cell[0]}, {cell[1]}) → {action.get('variable', '?')}"
        if name == "http_request":
            return f"{action.get('method', 'GET')} {action.get('url', '')} · {action.get('timeout_ms', 10000)} ms"
        if name == "user_input":
            return f"{action.get('prompt', '')} → {action.get('variable', '?')}"
        if name == "notify":
            return str(action.get("message", "")).replace("\n", " ")[:70]
        if name == "clipboard_write":
            return f"{action.get('type', 'text')}：{str(action.get('data', ''))[:70]}"
        return json.dumps(action, ensure_ascii=False)[:90]

    def _add_condition(self) -> None:
        self._append_condition_row(0, 0, "")
        self._mark_dirty()

    def _append_condition_row(self, row: int, column: int, regex: str) -> None:
        index = self.condition_table.rowCount()
        self.condition_table.insertRow(index)
        for col, value in enumerate((str(row), str(column), regex)):
            self.condition_table.setItem(index, col, QTableWidgetItem(value))

    def _remove_condition(self) -> None:
        row = self.condition_table.currentRow()
        if row >= 0:
            self.condition_table.removeRow(row)
            self._mark_dirty()

    def _add_action(self) -> None:
        dialog = ActionEditorDialog(self.registry, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self._actions.append(dialog.action_data())
            self._refresh_action_list(len(self._actions) - 1)
            self._mark_dirty()

    def _edit_action(self) -> None:
        index = self.action_list.currentRow()
        if index < 0 or index >= len(self._actions):
            return
        dialog = ActionEditorDialog(self.registry, self._actions[index], self)
        if dialog.exec_() == QDialog.Accepted:
            self._actions[index] = dialog.action_data()
            self._refresh_action_list(index)
            self._mark_dirty()

    def _remove_action(self) -> None:
        index = self.action_list.currentRow()
        if index < 0:
            return
        del self._actions[index]
        self._refresh_action_list(min(index, len(self._actions) - 1))
        self._mark_dirty()

    def _move_action(self, direction: int) -> None:
        index = self.action_list.currentRow()
        target = index + direction
        if index < 0 or target < 0 or target >= len(self._actions):
            return
        self._actions[index], self._actions[target] = self._actions[target], self._actions[index]
        self._refresh_action_list(target)
        self._mark_dirty()

    def _confirm_unsaved(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "未保存的修改",
            "当前规则有未保存修改。要先保存吗？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Save:
            return self._save_current_rule()
        return answer == QMessageBox.Discard

    def _on_rule_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if self._loading:
            return
        next_path = Path(current.data(Qt.UserRole)) if current is not None else None
        if not self._confirm_unsaved():
            self._loading = True
            self.rule_list.setCurrentItem(previous)
            self._loading = False
            return
        if next_path is None:
            self._clear_editor()
            return
        # Saving from the confirmation dialog rebuilds the list; find the live
        # item again rather than dereferencing the now-deleted QListWidgetItem.
        for index in range(self.rule_list.count()):
            item = self.rule_list.item(index)
            if Path(item.data(Qt.UserRole)) == next_path:
                self._loading = True
                self.rule_list.setCurrentItem(item)
                self._loading = False
                break
        self._load_rule(next_path)

    def _safe_file_name(self, name: str) -> str:
        clean = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", name.strip(), flags=re.UNICODE).strip("._")
        return (clean or "new_rule") + ".json"

    def _new_rule(self) -> None:
        if not self._confirm_unsaved():
            return
        existing_names = {rule.name.casefold() for rule in self.repository.rules}
        name = "新规则"
        suffix = 2
        while name.casefold() in existing_names:
            name = f"新规则 ({suffix})"
            suffix += 1
        document = {
            "version": 1,
            "name": name,
            "enabled": False,
            "priority": 0,
            "trigger": {"table_size": {"rows": 1, "columns": 1}, "conditions": []},
            "actions": [],
        }
        path = self.rules_directory / self._safe_file_name(name)
        suffix = 2
        while path.exists():
            path = self.rules_directory / f"{self._safe_file_name(name)[:-5]}_{suffix}.json"
            suffix += 1
        try:
            save_rule_file(path, document, registry=self.registry)
        except ExcelCheckerError as exc:
            QMessageBox.warning(self, "新建失败", str(exc))
            return
        self._refresh_rule_list(path)
        self._log(f"已新建规则：{path.name}")

    def _import_rule(self) -> None:
        if not self._confirm_unsaved():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "导入规则 JSON",
            str(Path.home()),
            "JSON 配置 (*.json)",
        )
        if not filename:
            return
        source = Path(filename).resolve()
        try:
            rule = load_rule_file(source, registry=self.registry)
            if source.parent == self.rules_directory:
                self._refresh_rule_list(source)
                return
            document = rule.to_dict()
            existing_names = {item.name.casefold() for item in self.repository.rules}
            if document["name"].casefold() in existing_names:
                base = document["name"]
                number = 2
                while f"{base} ({number})".casefold() in existing_names:
                    number += 1
                document["name"] = f"{base} ({number})"
            target = self.rules_directory / source.name
            suffix = 2
            while target.exists():
                target = self.rules_directory / f"{source.stem}_{suffix}{source.suffix}"
                suffix += 1
            save_rule_file(target, document, registry=self.registry)
            self._refresh_rule_list(target)
            self._log(f"已导入：{source} → {target.name}")
        except ExcelCheckerError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    def _remove_rule(self) -> None:
        if self._current_path is None:
            return
        if not self._confirm_unsaved():
            return
        answer = QMessageBox.question(
            self,
            "删除规则",
            f"确定删除“{self._current_rule.name if self._current_rule else self._current_path.name}”吗？此操作会删除 JSON 文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        path = self._current_path
        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self.repository.reload_if_changed(force=True)
        self._current_path = None
        self._refresh_rule_list()
        self._log(f"已删除规则：{path.name}")

    def _save_current_rule(self) -> bool:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "配置名称缺失", "请填写配置名称。")
            return False
        try:
            document = self._document_from_editor()
            normalized_name = document["name"].casefold()
            if any(
                rule.name.casefold() == normalized_name and rule.source != self._current_path
                for rule in self.repository.rules
            ):
                raise ConfigError(f"配置名称“{document['name']}”已存在，请修改名称后保存。")
            if self._current_path is None:
                path = self.rules_directory / self._safe_file_name(document["name"])
                suffix = 2
                while path.exists():
                    path = (
                        self.rules_directory
                        / f"{self._safe_file_name(document['name'])[:-5]}_{suffix}.json"
                    )
                    suffix += 1
            else:
                path = self._current_path
            save_rule_file(path, document, registry=self.registry)
            self.repository.reload_if_changed(force=True)
            self._current_path = path
            self._refresh_rule_list(path)
            self.statusBar().showMessage(f"已保存：{path.name}", 5000)
            self._log(f"规则已保存：{path.name}")
            return True
        except (ExcelCheckerError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False

    def _on_rule_item_changed(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        path = Path(item.data(Qt.UserRole))
        enabled = item.checkState() == Qt.Checked
        stored_rule = next((rule for rule in self.repository.rules if rule.source == path), None)
        old_check_state = (
            Qt.Checked if stored_rule is not None and stored_rule.enabled else Qt.Unchecked
        )
        if self._dirty and not self._confirm_unsaved():
            self._loading = True
            item.setCheckState(old_check_state)
            self._loading = False
            return
        try:
            rule = load_rule_file(path, registry=self.registry)
            document = rule.to_dict()
            document["enabled"] = enabled
            save_rule_file(path, document, registry=self.registry)
            self.repository.reload_if_changed(force=True)
            selected = self._current_path or path
            self._refresh_rule_list(selected)
            self._log(f"规则“{rule.name}”已{'启用' if enabled else '停用'}")
        except ExcelCheckerError as exc:
            QMessageBox.warning(self, "状态更新失败", str(exc))
            self._refresh_rule_list(self._current_path)

    def _open_rules_directory(self) -> None:
        self.rules_directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.rules_directory)))

    def _choose_rules_directory(self) -> None:
        if not self._confirm_unsaved():
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择规则目录",
            str(self.rules_directory),
        )
        if not directory:
            return
        self.rules_directory = Path(directory).resolve()
        self.settings.setValue("rules_dir", str(self.rules_directory))
        self.repository = RuleRepository(self.rules_directory, registry=self.registry)
        self.monitor = self._make_monitor()
        if self.monitor_checkbox.isChecked():
            self.monitor.mark_payload_seen(self.clipboard.text())
        self._refresh_rule_list()
        self._show_repository_errors()
        self._log(f"已切换规则目录：{self.rules_directory}")

    def _set_monitoring(self, enabled: bool) -> None:
        if enabled:
            self.monitor.mark_payload_seen(self.clipboard.text())
            self.poll_timer.start()
            self.monitor_status.setText("● 监控中")
            self.monitor_status.setStyleSheet("color: #16a34a; font-weight: 700; padding: 0 8px;")
            self.statusBar().showMessage("剪切板监控已开启；当前内容作为基线，不会立即触发。")
            self._log("剪切板监控已开启")
        else:
            self.poll_timer.stop()
            self.monitor_status.setText("● 未监控")
            self.monitor_status.setStyleSheet("color: #64748b; font-weight: 600; padding: 0 8px;")
            self.statusBar().showMessage("剪切板监控已关闭。")
            self._log("剪切板监控已关闭")

    def _on_clipboard_changed(self) -> None:
        if not self.monitor_checkbox.isChecked():
            return
        text = self.clipboard.text(QClipboard.Clipboard)
        if self._expected_clipboard_write is not None and text == self._expected_clipboard_write:
            self._expected_clipboard_write = None
            self.monitor.mark_payload_seen(text)
            return
        self.monitor.reset_payload_cache()

    def _handle_prompt(self, request: _UiRequest) -> None:
        if request.event.is_set():
            return
        try:
            value, accepted = QInputDialog.getText(
                self,
                "规则需要输入",
                request.message,
                QLineEdit.Normal,
            )
            request.result = value if accepted else None
        except Exception as exc:  # noqa: BLE001 - return Qt interaction failures to the worker
            request.error = exc
        finally:
            request.event.set()

    def _handle_notification(self, request: _UiRequest) -> None:
        if request.event.is_set():
            return
        try:
            QMessageBox.information(self, "规则提示", request.message)
        except Exception as exc:  # noqa: BLE001 - return Qt interaction failures to the worker
            request.error = exc
        finally:
            request.event.set()

    def _handle_clipboard_write(self, request: _UiRequest) -> None:
        if request.event.is_set():
            return
        try:
            self._expected_clipboard_write = request.text
            self.clipboard.setText(request.text, QClipboard.Clipboard)
            self.monitor.mark_payload_seen(request.text)
            QTimer.singleShot(
                500, lambda text=request.text: self._clear_expected_clipboard_write(text)
            )
        except Exception as exc:  # noqa: BLE001 - return Qt clipboard failures to the worker
            request.error = exc
        finally:
            request.event.set()

    def _clear_expected_clipboard_write(self, text: str) -> None:
        if self._expected_clipboard_write == text:
            self._expected_clipboard_write = None

    def _poll_clipboard(self) -> None:
        try:
            self.monitor.poll_once()
        except Exception as exc:  # noqa: BLE001 - keep QTimer polling alive after one bad read
            self._on_monitor_error(exc)

    def _on_clipboard_outcome(self, outcome: ProcessOutcome) -> None:
        if outcome.matched_rule is not None:
            self._log(f"已匹配规则“{outcome.matched_rule.name}”，加入执行队列。")
            self.statusBar().showMessage(f"已匹配：{outcome.matched_rule.name}", 3000)

    def _on_monitor_error(self, error: Exception) -> None:
        self._log_error(str(error))

    def _on_config_errors(self, errors: dict[Any, str]) -> None:
        if not errors:
            self._log("规则配置检查通过，热加载完成。")
            return
        for path, message in errors.items():
            self._log_error(f"配置 {Path(path).name}：{message}")

    def _show_repository_errors(self) -> None:
        for path, message in self.repository.errors.items():
            self._log_error(f"配置 {path.name}：{message}")

    def _job_finished(self, result: ExecutionResult) -> None:
        self._log(f"规则“{result.rule_name}”执行完成，共 {result.steps_executed} 个动作。")
        self.statusBar().showMessage(f"执行完成：{result.rule_name}", 4000)

    def _job_failed(self, rule_name: str, message: str) -> None:
        self._log_error(f"规则“{rule_name}”执行失败：{message}")
        QMessageBox.warning(self, "规则执行失败", f"{rule_name}\n\n{message}")

    def _log(self, message: str) -> None:
        from datetime import datetime

        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def _log_error(self, message: str) -> None:
        self._log(f"⚠ {message}")

    def closeEvent(self, event: Any) -> None:
        if not self._confirm_unsaved():
            event.ignore()
            return
        if hasattr(self, "poll_timer"):
            self.poll_timer.stop()
        if hasattr(self, "runner"):
            self.runner.clear_pending()
        if hasattr(self, "bridge"):
            self.bridge.shutdown()
        event.accept()


def main(argv: list[str] | None = None) -> int:
    application = QApplication(argv if argv is not None else sys.argv)
    application.setApplicationName("Excel Checker")
    application.setOrganizationName("ExcelChecker")
    window = MainWindow()
    window.show()
    return application.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
