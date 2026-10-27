"""Background worker thread for asynchronous workflow execution without blocking GUI."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from src.core.actions.base import ActionRegistry, ActionResult
from src.core.config_model import RuleConfig
from src.core.context import ExecutionContext, UIDelegate
from src.core.engine import WorkflowEngine, WorkflowExecutionResult
from src.core.table_parser import TableData


class WorkflowWorker(QThread):
    """Executes a workflow pipeline asynchronously on a dedicated worker thread."""

    progress_signal = pyqtSignal(int, int, str)       # current_step, total_steps, action_name
    finished_signal = pyqtSignal(object)              # WorkflowExecutionResult
    log_signal = pyqtSignal(str)                      # log message

    def __init__(
        self,
        rule: RuleConfig,
        table: TableData,
        ui_delegate: UIDelegate,
        initial_vars: Optional[Dict[str, Any]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.rule = rule
        self.table = table
        self.ui_delegate = ui_delegate
        # Always pre-initialize row and column system variables from the copied table dimensions
        self.initial_vars = dict(initial_vars or {})
        self.initial_vars.setdefault("row", str(table.rows))
        self.initial_vars.setdefault("column", str(table.cols))
        self.initial_vars.setdefault("colunm", str(table.cols))  # alias for common spelling typo
        self.initial_vars.setdefault("rows", str(table.rows))
        self.initial_vars.setdefault("cols", str(table.cols))
        self._is_cancelled = False
        self.execution_thread_id: Optional[int] = None

    def cancel(self):
        """Request worker cancellation."""
        self._is_cancelled = True

    def run(self):
        """Thread execution entry point."""
        import threading
        self.execution_thread_id = threading.get_ident()
        rule = self.rule
        table = self.table
        delegate = self.ui_delegate

        delegate.log(f"--- [后台任务] 开始异步执行规则: 【{rule.name}】 ---")

        engine = WorkflowEngine()

        def on_progress(cur_step: int, total_steps: int, act_name: str):
            self.progress_signal.emit(cur_step, total_steps, str(act_name))

        def is_cancelled() -> bool:
            return self._is_cancelled

        res = engine.execute_rule(
            rule=rule,
            table=table,
            ui_delegate=delegate,
            initial_vars=self.initial_vars,
            progress_callback=on_progress,
            cancel_check=is_cancelled,
        )

        if res.success:
            delegate.log(f"--- [后台任务] 规则 【{rule.name}】 全部流程异步执行完毕 ---")
        else:
            delegate.log(f"--- [后台任务] 规则 【{rule.name}】 执行终止: {res.error} ---")

        self.finished_signal.emit(res)
