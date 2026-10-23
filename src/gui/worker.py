"""Background worker thread for asynchronous workflow execution without blocking GUI."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from src.core.actions.base import ActionRegistry, ActionResult
from src.core.config_model import RuleConfig
from src.core.context import ExecutionContext, UIDelegate
from src.core.engine import WorkflowExecutionResult
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
        self.initial_vars = initial_vars or {}
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

        context = ExecutionContext(table_data=table, initial_vars=self.initial_vars)
        total_steps = len(rule.workflow)

        delegate.log(f"--- [后台任务] 开始异步执行规则: 【{rule.name}】 ---")

        for idx, act_cfg in enumerate(rule.workflow):
            if self._is_cancelled:
                err_msg = "用户手动取消了任务执行"
                delegate.log(f"[Cancelled] {err_msg}")
                res = WorkflowExecutionResult(
                    success=False,
                    rule_name=rule.name,
                    table_size=(table.rows, table.cols),
                    variables=context.variables,
                    logs=list(context.logs),
                    error=err_msg,
                    aborted_step=idx + 1,
                )
                self.finished_signal.emit(res)
                return

            step_num = idx + 1
            act_name = (
                act_cfg.get("action")
                or act_cfg.get("动作")
                or act_cfg.get("action_type")
                or act_cfg.get("type")
                or "未知动作"
            )

            self.progress_signal.emit(step_num, total_steps, str(act_name))
            delegate.log(f"[步骤 {step_num}/{total_steps}] 正在执行动作: {act_name}")

            try:
                action = ActionRegistry.create(act_cfg)
                action_res: ActionResult = action.execute(context, delegate)

                if not action_res.success:
                    err_msg = f"步骤 {step_num} ({act_name}) 执行失败: {action_res.error}"
                    delegate.log(f"[Error] {err_msg}")
                    res = WorkflowExecutionResult(
                        success=False,
                        rule_name=rule.name,
                        table_size=(table.rows, table.cols),
                        variables=context.variables,
                        logs=list(context.logs),
                        error=err_msg,
                        aborted_step=step_num,
                    )
                    self.finished_signal.emit(res)
                    return
            except Exception as e:
                err_msg = f"步骤 {step_num} ({act_name}) 抛出未捕获异常: {str(e)}"
                delegate.log(f"[Exception] {err_msg}")
                res = WorkflowExecutionResult(
                    success=False,
                    rule_name=rule.name,
                    table_size=(table.rows, table.cols),
                    variables=context.variables,
                    logs=list(context.logs),
                    error=err_msg,
                    aborted_step=step_num,
                )
                self.finished_signal.emit(res)
                return

        delegate.log(f"--- [后台任务] 规则 【{rule.name}】 全部流程异步执行完毕 ---")
        combined_logs = list(context.logs)
        if hasattr(delegate, "logs"):
            combined_logs.extend(delegate.logs)

        res = WorkflowExecutionResult(
            success=True,
            rule_name=rule.name,
            table_size=(table.rows, table.cols),
            variables=context.variables,
            logs=combined_logs,
        )
        self.finished_signal.emit(res)
