"""应用控制器：配置加载/热更新、剪贴板匹配、规则执行。

数据流：剪贴板监控 -> 解析表格 -> 匹配已加载且启用的规则（size + 额外条件） ->
按顺序执行动作步骤（网络请求同步阻塞，超时报错）。
"""

from __future__ import annotations

import os
from typing import Any

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .clipboard import ClipboardTable, ClipboardMonitor
from .config import ConfigError, RuleConfig
from .engine import Engine, EngineError


class AppController(QObject):
    """顶层控制器。GUI 与其通信：加载/卸载配置、启动/停止监控、接收事件信号。"""

    ruleMatched = pyqtSignal(str)        # 命中规则名称
    ruleExecuted = pyqtSignal(str, str)  # 规则名称，执行日志摘要
    error = pyqtSignal(str)              # 配置/执行错误

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._configs: dict[str, RuleConfig] = {}  # 路径 -> 规则
        self._active_paths: set[str] = set()       # 当前生效的配置路径
        self._mtimes: dict[str, float] = {}
        self._engine = Engine(
            on_input=self._default_input,
            on_alert=self._default_alert,
            on_log=self._log,
        )
        self._monitor: ClipboardMonitor | None = None
        self._watcher = QTimer(self)
        self._watcher.setInterval(2000)
        self._watcher.timeout.connect(self._check_hot_reload)
        self._logs: list[str] = []

    # ------------------------------------------------------------------ 配置管理

    def load_config(self, path: str) -> RuleConfig:
        rule = RuleConfig.load_file(path)
        self._configs[path] = rule
        self._active_paths.add(path)  # 新加载的配置默认生效
        self._mtimes[path] = os.path.getmtime(path)
        self._log(f"已加载配置: {rule.name} ({path})")
        return rule

    def replace_config(self, path: str, rule: RuleConfig) -> None:
        """用编辑后的规则替换已加载的配置（保持其启用状态）。"""
        was_active = path in self._active_paths
        self._configs[path] = rule
        self._mtimes[path] = os.path.getmtime(path)
        if was_active:
            self._active_paths.add(path)
        self._log(f"配置已更新: {rule.name} ({path})")

    def unload_config(self, path: str) -> None:
        self._configs.pop(path, None)
        self._active_paths.discard(path)
        self._mtimes.pop(path, None)
        self._log(f"已卸载配置: {path}")

    def list_configs(self) -> list[RuleConfig]:
        return list(self._configs.values())

    def config_paths(self) -> list[str]:
        return list(self._configs.keys())

    def enable_config(self, path: str) -> None:
        self._active_paths.add(path)
        self._log(f"已启用配置: {path}")

    def disable_config(self, path: str) -> None:
        self._active_paths.discard(path)
        self._log(f"已禁用配置: {path}")

    def is_active(self, path: str) -> bool:
        return path in self._active_paths

    def active_configs(self) -> list[RuleConfig]:
        return [self._configs[p] for p in self.config_paths() if p in self._active_paths]

    # ------------------------------------------------------------------ 监控生命周期

    def start(self) -> None:
        if self._monitor is None:
            self._monitor = ClipboardMonitor(interval_ms=1000)
            self._monitor.newTable.connect(self._on_clipboard_table)
            self._monitor.error.connect(self.error.emit)
        self._monitor.start()
        self._watcher.start()
        self._log("剪贴板监控已启动")

    def stop(self) -> None:
        self._watcher.stop()
        if self._monitor is not None:
            self._monitor.stop()
        self._log("剪贴板监控已停止")

    def is_running(self) -> bool:
        return self._monitor is not None and self._monitor.is_running()

    # ------------------------------------------------------------------ 热更新（热插拔）

    def _check_hot_reload(self) -> None:
        for path in list(self._configs.keys()):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if path not in self._mtimes or mtime != self._mtimes[path]:
                try:
                    self.load_config(path)  # reload replaces entry
                    self._log(f"配置热更新: {path}")
                except (ConfigError, OSError) as exc:
                    self.error.emit(f"配置 {path} 热更新失败: {exc}")

    # ------------------------------------------------------------------ 剪贴板 -> 匹配 -> 执行

    def _on_clipboard_table(self, table: ClipboardTable) -> None:
        rows, cols = table.size
        for path in self.config_paths():
            if path not in self._active_paths:
                continue
            rule = self._configs[path]
            if rule.trigger.check(table.rows):
                self._log(f"剪贴板命中规则 {rule.name} ({rows}x{cols})")
                self.ruleMatched.emit(rule.name)
                try:
                    ctx = self._engine.run(rule, table.rows)
                    self.ruleExecuted.emit(rule.name, "; ".join(ctx.logs))
                except EngineError as exc:
                    self.error.emit(f"规则 {rule.name} 执行失败: {exc}")
                break  # 命中第一条生效规则即执行，不再继续匹配

    # ------------------------------------------------------------------ 默认人机交互回调（GUI 接入后替换为模态弹窗）

    def _default_input(self, prompt: str) -> str:
        raise EngineError(f"需要用户输入：{prompt}（未提供输入回调）")

    def _default_alert(self, content: str) -> None:
        self._log(f"[提示] {content}")

    def _log(self, msg: str) -> None:
        self._logs.append(msg)

    def get_logs(self) -> list[str]:
        return list(self._logs)

    # 供 GUI 注入真实的交互回调
    def set_input_callback(self, callback: Any) -> None:
        self._engine.on_input = callback

    def set_alert_callback(self, callback: Any) -> None:
        self._engine.on_alert = callback
