"""Workflow and rule execution engine with hot-reload and clipboard dispatching."""
from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core.actions.base import ActionRegistry, ActionResult
from src.core.config_model import RuleConfig
from src.core.context import ExecutionContext, HeadlessUIDelegate, UIDelegate
from src.core.table_parser import TableData


@dataclass
class WorkflowExecutionResult:
    """Result of running a workflow."""
    success: bool
    rule_name: str
    table_size: Tuple[int, int]
    variables: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    aborted_step: Optional[int] = None


class WorkflowEngine:
    """Central engine managing rules and executing workflow pipelines."""

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = config_dir or os.path.join(os.getcwd(), "configs")
        self.rules: List[RuleConfig] = []
        self._file_mtimes: Dict[str, float] = {}
        self.active_rule: Optional[RuleConfig] = None
        self.on_log: Optional[Callable[[str], None]] = None

    def log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def reload_rules(self) -> int:
        """Scan config directory and reload rule files (hot-reload support)."""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

        found_files = glob.glob(os.path.join(self.config_dir, "*.json"))
        loaded: List[RuleConfig] = []
        new_mtimes: Dict[str, float] = {}

        for file_path in found_files:
            try:
                mtime = os.path.getmtime(file_path)
                new_mtimes[file_path] = mtime
                rule = RuleConfig.load_from_file(file_path)
                loaded.append(rule)
            except Exception as e:
                self.log(f"[Engine] Failed to load config {file_path}: {e}")

        self.rules = loaded
        self._file_mtimes = new_mtimes
        self.log(f"[Engine] Loaded {len(self.rules)} rules from {self.config_dir}")
        return len(self.rules)

    def check_hot_reload(self) -> bool:
        """Check if any config files have been modified on disk and reload if so."""
        if not os.path.exists(self.config_dir):
            return False

        current_files = set(glob.glob(os.path.join(self.config_dir, "*.json")))
        cached_files = set(self._file_mtimes.keys())

        if current_files != cached_files:
            self.reload_rules()
            return True

        for path in current_files:
            try:
                if os.path.getmtime(path) > self._file_mtimes.get(path, 0):
                    self.reload_rules()
                    return True
            except OSError:
                pass
        return False

    def add_rule(self, rule: RuleConfig) -> None:
        self.rules.append(rule)

    def find_matching_rule(self, table: TableData) -> Optional[RuleConfig]:
        """Find matching rule for the given table data.

        If active_rule is set, tests against active_rule.
        Otherwise falls back to checking all loaded rules.
        """
        if self.active_rule:
            return self.active_rule if self.active_rule.matches(table) else None

        for rule in self.rules:
            if rule.matches(table):
                return rule
        return None

    def execute_rule(
        self,
        rule: RuleConfig,
        table: TableData,
        ui_delegate: Optional[UIDelegate] = None,
        initial_vars: Optional[Dict[str, Any]] = None,
    ) -> WorkflowExecutionResult:
        """Execute a rule's workflow sequentially."""
        delegate = ui_delegate or HeadlessUIDelegate()
        context = ExecutionContext(table_data=table, initial_vars=initial_vars)

        self.log(f"[Engine] Starting workflow for rule: '{rule.name}' with table {table.rows}x{table.cols}")
        delegate.log(f"--- 开始执行规则: 【{rule.name}】 ---")

        total_steps = len(rule.workflow)
        context.total_steps = total_steps
        pc = 0
        execution_count = 0
        max_executions = 10000  # safeguard against infinite loops

        @dataclass
        class IfScope:
            step: int
            then_end: int
            else_end: int
            exit_step: int
            branch: str  # "then" or "else"

        if_scopes: List[IfScope] = []
        pending_skips: Dict[int, int] = {}  # at_step -> skip_to_step

        while pc < len(rule.workflow):
            execution_count += 1
            if execution_count > max_executions:
                err_msg = f"流程执行步骤达到上限 {max_executions}，检测到可能的死循环并自动终止"
                delegate.log(f"[Loop Abort] {err_msg}")
                return WorkflowExecutionResult(
                    success=False,
                    rule_name=rule.name,
                    table_size=(table.rows, table.cols),
                    variables=context.variables,
                    logs=list(context.logs),
                    error=err_msg,
                    aborted_step=pc + 1,
                )

            step_num = pc + 1
            context.current_step = step_num
            act_cfg = rule.workflow[pc]
            act_name = act_cfg.get("action") or act_cfg.get("type") or act_cfg.get("动作") or "未知"
            self.log(f"[Engine] Executing step {step_num}: {act_name}")

            try:
                action = ActionRegistry.create(act_cfg)
                res: ActionResult = action.execute(context, delegate)

                if not res.success:
                    err_msg = f"步骤 {step_num} ({act_name}) 执行失败: {res.error}"
                    delegate.log(f"[Error] {err_msg}")
                    return WorkflowExecutionResult(
                        success=False,
                        rule_name=rule.name,
                        table_size=(table.rows, table.cols),
                        variables=context.variables,
                        logs=list(context.logs),
                        error=err_msg,
                        aborted_step=step_num,
                    )

                # Register active if scope for multi-level nesting
                if res.branch_info:
                    b_info = res.branch_info
                    b_step = b_info["step"]
                    t_cnt = b_info["then_count"]
                    e_cnt = b_info["else_count"]
                    b_type = b_info["branch"]
                    if_scopes.append(IfScope(
                        step=b_step,
                        then_end=b_step + t_cnt,
                        else_end=b_step + t_cnt + e_cnt if e_cnt > 0 else b_step + t_cnt,
                        exit_step=b_step + 1 + t_cnt + e_cnt,
                        branch=b_type,
                    ))

                # Register any skip_after for backwards compatibility
                if res.skip_after:
                    at_s, skip_s = res.skip_after
                    pending_skips[at_s] = skip_s

                # Check if this action performed an explicit jump (e.g. Goto or If false)
                if res.jump_to is not None:
                    target_step = res.jump_to
                    if target_step > len(rule.workflow):
                        # Jump past the end of workflow -> finishes workflow
                        break
                    pc = target_step - 1
                    # Filter active scopes to only those that still enclose the target step
                    if_scopes = [
                        s for s in if_scopes
                        if (s.branch == "then" and s.step < target_step <= s.then_end)
                        or (s.branch == "else" and s.then_end < target_step <= s.else_end)
                    ]
                else:
                    # Normal sequential advance with nested scope unwinding
                    next_s = step_num + 1
                    while if_scopes:
                        top = if_scopes[-1]
                        if top.branch == "then" and step_num == top.then_end:
                            if_scopes.pop()
                            next_s = top.exit_step
                            step_num = next_s - 1
                            continue
                        elif top.branch == "else" and step_num == top.else_end:
                            if_scopes.pop()
                            next_s = top.exit_step
                            step_num = next_s - 1
                            continue
                        break

                    if step_num in pending_skips:
                        legacy_skip = pending_skips.pop(step_num)
                        next_s = max(next_s, legacy_skip)

                    if next_s > len(rule.workflow):
                        break
                    pc = next_s - 1

            except Exception as e:
                err_msg = f"步骤 {step_num} ({act_name}) 发生未捕获异常: {str(e)}"
                delegate.log(f"[Exception] {err_msg}")
                return WorkflowExecutionResult(
                    success=False,
                    rule_name=rule.name,
                    table_size=(table.rows, table.cols),
                    variables=context.variables,
                    logs=list(context.logs),
                    error=err_msg,
                    aborted_step=step_num,
                )

        delegate.log(f"--- 规则 【{rule.name}】 全部流程执行完毕 ---")
        combined_logs = list(context.logs)
        if hasattr(delegate, "logs"):
            combined_logs.extend(delegate.logs)

        return WorkflowExecutionResult(
            success=True,
            rule_name=rule.name,
            table_size=(table.rows, table.cols),
            variables=context.variables,
            logs=combined_logs,
        )

    def process_clipboard_text(
        self,
        text: str,
        ui_delegate: Optional[UIDelegate] = None,
    ) -> Optional[WorkflowExecutionResult]:
        """Process new clipboard text: parse table, match rule, and execute if matched."""
        if not text:
            return None

        table = TableData.from_text(text)
        rule = self.find_matching_rule(table)

        if not rule:
            # Did not match any rule
            return None

        return self.execute_rule(rule, table, ui_delegate=ui_delegate)
