"""Main window of the Excel Checker desktop application."""
from __future__ import annotations

import datetime
import glob
import os
import sys
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.config_model import RuleConfig
from src.core.engine import WorkflowEngine, WorkflowExecutionResult
from src.core.table_parser import TableData
from src.gui.block_editor import BlockEditorWidget
from src.gui.clipboard_watcher import ClipboardWatcher
from src.gui.json_editor_widget import JsonEditorWidget
from src.gui.qt_delegate import ThreadSafeUIDelegate
from src.gui.sidebar import SidebarNav
from src.gui.simulator_widget import SimulatorWidget
from src.gui.style import APP_STYLESHEET
from src.gui.worker import WorkflowWorker


class MainWindow(QMainWindow):
    """Primary application window for Excel Checker."""

    def __init__(self, config_dir: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("表格数据检查辅助 (Excel Table Checker) - Python 3.13 / PyQt5")
        self.resize(1200, 920)
        self.setStyleSheet(APP_STYLESHEET)

        # Ensure Chinese font is registered
        font_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "fonts", "wqy-microhei.ttc")
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)
            self.setFont(QFont("WenQuanYi Micro Hei", 10))

        self.config_dir = os.path.abspath(config_dir or os.path.join(os.getcwd(), "configs"))
        os.makedirs(self.config_dir, exist_ok=True)

        self.engine = WorkflowEngine(self.config_dir)
        self.ui_delegate = ThreadSafeUIDelegate(self)
        self.ui_delegate.on_log_callback = self.append_log

        # Robust clipboard watcher with debouncing and watchdog
        self.clipboard_watcher = ClipboardWatcher(self, debounce_ms=80, watchdog_interval_ms=800)
        self.clipboard_watcher.text_captured.connect(self._on_clipboard_text_captured)

        self.current_file_path: Optional[str] = None
        self.current_worker: Optional[WorkflowWorker] = None

        self.setup_ui()
        self.load_config_list()

        # Timer for hot reload checking
        self.hot_reload_timer = QTimer(self)
        self.hot_reload_timer.timeout.connect(self._check_hot_reload)
        self.hot_reload_timer.start(2000)

    def setup_ui(self):
        # 1. Top Control Bar
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Logo / Title badge
        title_badge = QLabel(" Excel Checker ")
        title_badge.setProperty("class", "badge")
        title_badge.setStyleSheet("font-size: 14px; font-weight: bold; background: #0284c7; color: white; padding: 4px 10px; border-radius: 4px;")
        toolbar.addWidget(title_badge)

        toolbar.addSeparator()

        # Config dropdown
        toolbar.addWidget(QLabel(" 配置文件: "))
        self.combo_configs = QComboBox()
        self.combo_configs.setMinimumWidth(220)
        self.combo_configs.currentIndexChanged.connect(self._on_config_selected)
        toolbar.addWidget(self.combo_configs)

        # Buttons
        btn_new = QPushButton("新建")
        btn_new.setToolTip("新建一个空白规则配置")
        btn_new.clicked.connect(self.new_config)
        toolbar.addWidget(btn_new)

        btn_open = QPushButton("打开...")
        btn_open.setToolTip("从本地选择打开 JSON 规则文件")
        btn_open.clicked.connect(self.open_config_file)
        toolbar.addWidget(btn_open)

        btn_save = QPushButton("保存")
        btn_save.setToolTip("保存当前规则到文件")
        btn_save.clicked.connect(self.save_config)
        toolbar.addWidget(btn_save)

        btn_save_as = QPushButton("另存为...")
        btn_save_as.setToolTip("当前规则另存为新文件")
        btn_save_as.clicked.connect(self.save_config_as)
        toolbar.addWidget(btn_save_as)

        btn_reload = QPushButton("刷新")
        btn_reload.setToolTip("重新扫描并载入配置目录")
        btn_reload.clicked.connect(self.load_config_list)
        toolbar.addWidget(btn_reload)

        toolbar.addSeparator()

        # Master Monitor Toggle Switch
        self.btn_toggle_monitor = QPushButton("开启该规则后台监控")
        self.btn_toggle_monitor.setProperty("id", "successBtn")
        self.btn_toggle_monitor.setMinimumHeight(32)
        self.btn_toggle_monitor.clicked.connect(self.toggle_monitor)
        toolbar.addWidget(self.btn_toggle_monitor)

        self.lbl_monitor_status = QLabel(" 监控未开启")
        self.lbl_monitor_status.setStyleSheet("color: #64748b; font-weight: bold; margin-left: 6px;")
        toolbar.addWidget(self.lbl_monitor_status)

        # 2. Main Workspace (Splitter: Upper Content + Lower Log Console)
        main_splitter = QSplitter(Qt.Vertical)

        # Upper Content Area: Horizontal split between Sidebar (Level 1) and Pages
        workspace_widget = QWidget()
        workspace_layout = QHBoxLayout(workspace_widget)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        # Level 1 Menu: Vertical Sidebar Navigation
        self.sidebar = SidebarNav(self)
        self.sidebar.page_changed.connect(self._on_sidebar_page_changed)
        workspace_layout.addWidget(self.sidebar)

        # Central Stacked Pages
        self.page_stack = QStackedWidget(self)

        # Page 1: Block Editor (Containing Level 2 Secondary Tabs: Trigger & Pipeline)
        self.block_editor = BlockEditorWidget()
        self.block_editor.rule_changed.connect(self._on_rule_modified)
        self.sidebar.add_page("editor", "低代码积木 (Visual)", self.block_editor, self.page_stack, is_default=True)

        # Page 2: JSON Source Synchronizer
        self.json_editor = JsonEditorWidget()
        self.json_editor.apply_requested.connect(self._on_json_applied)
        self.sidebar.add_page("json", "JSON 源码同步", self.json_editor, self.page_stack)

        # Page 3: Clipboard Table Simulator
        self.simulator = SimulatorWidget(
            engine=self.engine,
            get_current_rule_fn=self.get_active_rule,
        )
        self.sidebar.add_page("simulator", "表格模拟测试器", self.simulator, self.page_stack)

        workspace_layout.addWidget(self.page_stack, 1)
        main_splitter.addWidget(workspace_widget)

        # 3. Bottom Log Console Panel
        bottom_box = QWidget()
        bottom_layout = QVBoxLayout(bottom_box)
        bottom_layout.setContentsMargins(10, 4, 10, 8)
        bottom_layout.setSpacing(6)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("<b>剪切板监控实时跟踪日志 (Live Monitor Log):</b>"))
        log_header.addStretch()

        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.clicked.connect(lambda: self.log_console.clear())
        log_header.addWidget(btn_clear_log)

        bottom_layout.addLayout(log_header)

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setProperty("id", "logConsole")
        self.log_console.setMaximumHeight(160)
        bottom_layout.addWidget(self.log_console)

        main_splitter.addWidget(bottom_box)
        main_splitter.setStretchFactor(0, 4)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([720, 160])

        self.setCentralWidget(main_splitter)

    def append_log(self, msg: str):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_console.appendPlainText(f"[{now_str}] {msg}")
        # Auto scroll to bottom
        sb = self.log_console.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def load_config_list(self):
        """Scan config directory and populate the combo box."""
        self.combo_configs.blockSignals(True)
        self.combo_configs.clear()

        files = sorted(glob.glob(os.path.join(self.config_dir, "*.json")))
        if not files:
            # Create default 示例配置1.json if empty
            default_path = os.path.join(self.config_dir, "示例配置1.json")
            RuleConfig(name="用户ID查询示例").save_to_file(default_path, use_chinese_keys=True)
            files = [default_path]

        selected_idx = 0
        for idx, f in enumerate(files):
            fname = os.path.basename(f)
            self.combo_configs.addItem(fname, f)
            if self.current_file_path and os.path.abspath(f) == os.path.abspath(self.current_file_path):
                selected_idx = idx

        self.combo_configs.blockSignals(False)
        self.combo_configs.setCurrentIndex(selected_idx)
        self._load_selected_file(files[selected_idx])

    def _on_config_selected(self, index: int):
        if index >= 0:
            file_path = self.combo_configs.itemData(index)
            if file_path and os.path.exists(file_path):
                self._load_selected_file(file_path)

    def _load_selected_file(self, file_path: str):
        try:
            rule = RuleConfig.load_from_file(file_path)
            self.current_file_path = file_path
            self.block_editor.load_rule(rule)
            self.json_editor.set_rule(rule)
            self.engine.active_rule = rule
            size_desc = f"{'任意' if rule.fuzzy_row else rule.table_size[0]}x{'任意' if rule.fuzzy_col else rule.table_size[1]}"
            self.append_log(f"已载入配置文件: {os.path.basename(file_path)} (触发尺寸: {size_desc})")
        except Exception as e:
            QMessageBox.critical(self, "读取配置失败", f"无法加载 {file_path}: {e}")

    def get_active_rule(self) -> RuleConfig:
        rule = self.block_editor.to_rule()
        rule.file_path = self.current_file_path
        return rule

    def _on_rule_modified(self):
        """Called whenever visual editor changes."""
        rule = self.get_active_rule()
        self.engine.active_rule = rule

    def _on_sidebar_page_changed(self, page_id: str, page_index: int):
        rule = self.get_active_rule()
        if page_id == "json":
            self.json_editor.set_rule(rule)
        elif page_id == "simulator":
            self.simulator._update_table_info()

    def _on_json_applied(self, rule: RuleConfig):
        """Called when user applies JSON code back to visual blocks."""
        self.block_editor.load_rule(rule)
        self.engine.active_rule = rule
        self.append_log(f"已同步 JSON 配置到积木编辑器: 【{rule.name}】")

    def new_config(self):
        rule = RuleConfig(
            name="新规则",
            table_size=(1, 1),
            workflow=[
                {"action": "extract_cell", "position": [0, 0], "variable": "id"},
                {"action": "show_message", "title": "提示", "content": "提取到ID: {{id}}"},
            ],
            enabled=True,
        )
        self.current_file_path = None
        self.block_editor.load_rule(rule)
        self.json_editor.set_rule(rule)
        self.engine.active_rule = rule
        self.append_log("已创建空白新规则，请配置后点击保存。")

    def open_config_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开配置文件", self.config_dir, "JSON 文件 (*.json)")
        if path:
            self._load_selected_file(path)

    def save_config(self):
        if not self.current_file_path:
            self.save_config_as()
            return

        rule = self.get_active_rule()
        errors = rule.validate()
        if errors:
            QMessageBox.warning(self, "配置校验未通过", "请先修复以下问题:\n• " + "\n• ".join(errors))
            return

        try:
            rule.save_to_file(self.current_file_path, use_chinese_keys=True)
            self.engine.active_rule = rule
            self.append_log(f"配置已成功保存到: {os.path.basename(self.current_file_path)}")
            QMessageBox.information(self, "保存成功", f"配置已保存到 {os.path.basename(self.current_file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def save_config_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "规则另存为", self.config_dir, "JSON 文件 (*.json)")
        if path:
            if not path.endswith(".json"):
                path += ".json"
            self.current_file_path = path
            self.save_config()
            self.load_config_list()

    def toggle_monitor(self):
        """Toggle live background clipboard monitoring."""
        if not self.clipboard_watcher.is_monitoring:
            rule = self.get_active_rule()
            self.engine.active_rule = rule
            self.clipboard_watcher.start_monitoring()

            self.btn_toggle_monitor.setText("停止后台监控 (运行中)")
            self.btn_toggle_monitor.setProperty("id", "dangerBtn")
            self.btn_toggle_monitor.setStyle(self.btn_toggle_monitor.style())
            size_desc = f"{'任意' if rule.fuzzy_row else rule.table_size[0]}x{'任意' if rule.fuzzy_col else rule.table_size[1]}"
            self.lbl_monitor_status.setText(f" 正在监控剪切板 · 激活规则: 【{rule.name}】 ({size_desc})")
            self.lbl_monitor_status.setStyleSheet("color: #16a34a; font-weight: bold; margin-left: 6px;")
            self.append_log(f"--- 后台剪切板监控已启动 (防断联双重机制就绪, 监听尺寸: {size_desc}) ---")
        else:
            self.clipboard_watcher.stop_monitoring()
            if self.current_worker and self.current_worker.isRunning():
                self.current_worker.cancel()

            self.btn_toggle_monitor.setText("开启该规则后台监控")
            self.btn_toggle_monitor.setProperty("id", "successBtn")
            self.btn_toggle_monitor.setStyle(self.btn_toggle_monitor.style())
            self.lbl_monitor_status.setText(" 监控已暂停")
            self.lbl_monitor_status.setStyleSheet("color: #64748b; font-weight: bold; margin-left: 6px;")
            self.append_log("--- 后台剪切板监控已暂停 ---")

    def _on_clipboard_text_captured(self, text: str):
        """Dispatched on GUI thread after debounce, safely passing heavy work to worker thread."""
        if not self.clipboard_watcher.is_monitoring:
            return

        rule = self.get_active_rule()
        if not rule.enabled:
            return

        table = TableData.from_text(text)
        self.append_log(f"[剪切板事件] 捕获新复制内容: 检测尺寸为 {table.rows} 行 x {table.cols} 列 (纯文本预览: {repr(text[:25])})")

        # Step 4: Check table size with fuzzy matching
        if not table.matches_size(rule.table_size[0], rule.table_size[1], fuzzy_row=rule.fuzzy_row, fuzzy_col=rule.fuzzy_col):
            exp_r = "任意" if rule.fuzzy_row else str(rule.table_size[0])
            exp_c = "任意" if rule.fuzzy_col else str(rule.table_size[1])
            self.append_log(f"[跳过] 复制表格尺寸 ({table.rows}x{table.cols}) 与当前配置要求 ({exp_r}x{exp_c}) 不匹配，忽略。")
            return

        # Step 5: Check extra conditions
        for idx, cond in enumerate(rule.extra_conditions):
            if not cond.matches(table):
                cell_v = table.get_cell(cond.row, cond.col)
                self.append_log(f"[跳过] 第 {idx + 1} 个额外条件未满足: 单元格 ({cond.row},{cond.col}) 内容 '{cell_v}' 不匹配正则 '{cond.regex}'")
                return

        # Guard: check if another worker is already running
        if self.current_worker and self.current_worker.isRunning():
            self.append_log("[提示] 上一个任务正在子线程执行中，已忽略本次快速重复触发。")
            return

        # Step 6: Dispatch workflow to Background Worker Thread!
        self.append_log(f"🎯 触发条件全部满足！已将流程 【{rule.name}】 推送至后台子线程执行，主界面保持流畅响应...")
        self.lbl_monitor_status.setText(f" 🟡 正在后台执行: 【{rule.name}】...")
        self.lbl_monitor_status.setStyleSheet("color: #f59e0b; font-weight: bold; margin-left: 6px;")

        self.current_worker = WorkflowWorker(
            rule=rule,
            table=table,
            ui_delegate=self.ui_delegate,
            parent=self,
        )
        self.current_worker.progress_signal.connect(self._on_worker_progress)
        self.current_worker.finished_signal.connect(self._on_worker_finished)
        self.current_worker.start()

    def _on_worker_progress(self, cur_step: int, total_steps: int, act_name: str):
        rule = self.get_active_rule()
        self.lbl_monitor_status.setText(f" 🟡 正在执行 【{rule.name}】 (步骤 {cur_step}/{total_steps}: {act_name})...")
        self.lbl_monitor_status.setStyleSheet("color: #f59e0b; font-weight: bold; margin-left: 6px;")

    def _on_worker_finished(self, result: WorkflowExecutionResult):
        rule = self.get_active_rule()
        if self.clipboard_watcher.is_monitoring:
            size_desc = f"{'任意' if rule.fuzzy_row else rule.table_size[0]}x{'任意' if rule.fuzzy_col else rule.table_size[1]}"
            self.lbl_monitor_status.setText(f" 正在监控剪切板 · 激活规则: 【{rule.name}】 ({size_desc})")
            self.lbl_monitor_status.setStyleSheet("color: #16a34a; font-weight: bold; margin-left: 6px;")
        else:
            self.lbl_monitor_status.setText(" 监控已暂停")
            self.lbl_monitor_status.setStyleSheet("color: #64748b; font-weight: bold; margin-left: 6px;")

        # Ignore what our action wrote to prevent self-loop
        last_clip = self.ui_delegate.clipboard_backup
        if last_clip:
            self.clipboard_watcher.ignore_content(last_clip)

        if result.success:
            self.append_log(f"✅ 规则 【{result.rule_name}】 后台执行完毕！")
        else:
            self.append_log(f"❌ 规则 【{result.rule_name}】 执行失败: {result.error}")
            QMessageBox.critical(self, "规则执行错误", f"在步骤 {result.aborted_step} 执行出错:\n{result.error}")

        self.current_worker = None

    def closeEvent(self, event):
        if self.clipboard_watcher:
            self.clipboard_watcher.stop_monitoring()
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.cancel()
            self.current_worker.wait(1000)
        event.accept()

    def _check_hot_reload(self):
        """Periodically check if files on disk changed."""
        if self.engine.check_hot_reload():
            self.append_log("🔄 检测到配置文件热更新，已自动重载！")
            if self.current_file_path and os.path.exists(self.current_file_path):
                self._load_selected_file(self.current_file_path)
