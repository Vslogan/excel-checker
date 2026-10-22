"""主窗口：配置管理、剪贴板监控开关、执行日志。"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..config import RuleConfig
from ..controller import AppController
from .config_editor import ConfigEditor


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self._controller = controller
        self._path_to_item: dict[str, QListWidgetItem] = {}

        # 将 GUI 的真实弹窗接入引擎的人机交互回调
        controller.set_input_callback(self._prompt_input)
        controller.set_alert_callback(self._show_alert)

        # 控制器信号 -> 界面
        controller.ruleMatched.connect(self._on_rule_matched)
        controller.ruleExecuted.connect(self._on_rule_executed)
        controller.error.connect(self._on_error)

        self._build_ui()
        self._refresh_config_list()

    # ------------------------------------------------------------------ 界面搭建

    def _build_ui(self) -> None:
        self.setWindowTitle("excel-checker - 表格数据检查辅助")
        self.resize(1100, 720)

        toolbar = QToolBar("工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.act_new_config = toolbar.addAction("新建配置", self._new_config)
        self.act_open_config = toolbar.addAction("打开配置", self._open_config)
        self.act_save_config = toolbar.addAction("保存配置", self._save_config)
        self.act_edit_config = toolbar.addAction("编辑配置", self._edit_config)
        self.act_del_config = toolbar.addAction("删除配置", self._del_config)
        toolbar.addSeparator()
        self.btn_monitor = toolbar.addAction("启动监控", self._toggle_monitor)
        toolbar.addSeparator()
        toolbar.addAction("退出", self.close)

        splitter = QSplitter()

        # 左侧：配置列表
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(self._label("已加载的规则配置（勾选 = 生效，未勾选 = 忽略）"))
        self.list_configs = QListWidget()
        self.list_configs.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_configs.itemChanged.connect(self._on_item_checked)
        lv.addWidget(self.list_configs)
        lb = self._h_buttons([
            ("新建", self._new_config),
            ("打开", self._open_config),
            ("编辑", self._edit_config),
            ("删除", self._del_config),
        ])
        lv.addLayout(lb)
        splitter.addWidget(left)

        # 右侧：日志
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(self._label("执行日志"))
        self.edit_log = QTextEdit()
        self.edit_log.setReadOnly(True)
        rv.addWidget(self.edit_log)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("监控已停止")

    @staticmethod
    def _label(text: str):
        from PyQt5.QtWidgets import QLabel

        return QLabel(text)

    @staticmethod
    def _h_buttons(specs):
        from PyQt5.QtWidgets import QHBoxLayout, QPushButton

        box = QHBoxLayout()
        for text, slot in specs:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            box.addWidget(btn)
        box.addStretch()
        return box

    # ------------------------------------------------------------------ 配置列表操作

    def _refresh_config_list(self) -> None:
        self.list_configs.itemChanged.disconnect(self._on_item_checked)
        self.list_configs.clear()
        self._path_to_item = {}
        for path in self._controller.config_paths():
            rule = self._controller._configs[path]  # noqa: SLF001
            item = QListWidgetItem(f"{rule.name}  [{path}]")
            item.setCheckState(Qt.Checked if self._controller.is_active(path) else Qt.Unchecked)
            item.setData(Qt.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.list_configs.addItem(item)
            self._path_to_item[path] = item
        self.list_configs.itemChanged.connect(self._on_item_checked)

    def _selected_paths(self) -> list[str]:
        paths = []
        for item in self.list_configs.selectedItems():
            path = item.data(Qt.UserRole)
            if path:
                paths.append(path)
        return paths

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if not path:
            return
        if item.checkState() == Qt.Checked:
            self._controller.enable_config(path)
        else:
            self._controller.disable_config(path)

    def _new_config(self) -> None:
        editor = ConfigEditor(parent=self)
        if editor.exec_():
            rule = editor.rule()
            path, _ = QFileDialog.getSaveFileName(
                self, "保存配置文件", "", "JSON 文件 (*.json)"
            )
            if not path:
                return
            if not path.lower().endswith(".json"):
                path += ".json"
            rule.save_file(path)
            self._controller.load_config(path)
            self._refresh_config_list()

    def _open_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开配置文件", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            self._controller.load_config(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "打开失败", f"无法加载配置：{exc}")
            return
        self._refresh_config_list()

    def _save_config(self) -> None:
        paths = self._selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self, "提示", "请先在列表中选中一条配置再保存")
            return
        path = paths[0]
        try:
            self._controller._configs[path].save_file()  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))

    def _edit_config(self) -> None:
        paths = self._selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self, "提示", "请先在列表中选中一条配置再编辑")
            return
        path = paths[0]
        rule = self._controller._configs[path]  # noqa: SLF001
        editor = ConfigEditor(rule, parent=self)
        if editor.exec_():
            new_rule = editor.rule()
            self._controller.replace_config(path, new_rule)
            self._refresh_config_list()

    def _del_config(self) -> None:
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选中要删除的配置")
            return
        for path in paths:
            self._controller.unload_config(path)
        self._refresh_config_list()

    # ------------------------------------------------------------------ 监控开关

    def _toggle_monitor(self) -> None:
        if self._controller.is_running():
            self._controller.stop()
            self.btn_monitor.setText("启动监控")
            self.status.showMessage("监控已停止")
            self._append_log("[系统] 剪贴板监控已停止")
        else:
            if not self._controller.config_paths():
                QMessageBox.information(self, "提示", "请先加载至少一条规则配置")
                return
            self._controller.start()
            self.btn_monitor.setText("停止监控")
            self.status.showMessage("监控运行中（后台轮询剪贴板）")
            self._append_log("[系统] 剪贴板监控已启动")

    # ------------------------------------------------------------------ 控制器信号处理

    def _on_rule_matched(self, rule_name: str) -> None:
        self._append_log(f"[匹配] 命中规则：{rule_name}")

    def _on_rule_executed(self, rule_name: str, summary: str) -> None:
        self._append_log(f"[执行] 规则 {rule_name} 已完成：{summary}")

    def _on_error(self, message: str) -> None:
        self._append_log(f"[错误] {message}")
        QTimer.singleShot(0, lambda: QMessageBox.warning(self, "错误", message))

    def _append_log(self, text: str) -> None:
        from datetime import datetime

        self.edit_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    # ------------------------------------------------------------------ 引擎人机交互回调（模态弹窗）

    def _prompt_input(self, prompt: str) -> str:
        text, ok = QInputDialog.getText(self, "用户输入", prompt)
        if not ok:
            from ..engine import EngineError

            raise EngineError("用户取消了输入")
        return text

    def _show_alert(self, content: str) -> None:
        QMessageBox.information(self, "规则提示", content)
