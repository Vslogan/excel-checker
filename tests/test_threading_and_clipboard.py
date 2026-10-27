"""Tests for background worker threading and clipboard watcher robustness."""
import os
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication

from src.core.config_model import ExtraCondition, RuleConfig
from src.core.engine import WorkflowExecutionResult
from src.core.table_parser import TableData
from src.gui.clipboard_watcher import ClipboardWatcher
from src.gui.qt_delegate import ThreadSafeUIDelegate
from src.gui.worker import WorkflowWorker


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_worker_thread_asynchronous_execution(qapp):
    """Verify that WorkflowWorker executes on a separate background thread without blocking main thread."""
    rule = RuleConfig(
        name="异步测试规则",
        table_size=(1, 1),
        workflow=[
            {"action": "extract_cell", "position": [0, 0], "variable": "item_id"},
            {"action": "show_message", "title": "通知", "content": "收到: {{item_id}}"},
            {"action": "write_clipboard", "type": "text", "data": "OUT_{{item_id}}"},
        ]
    )
    table = TableData.from_text("ITEM_999")
    delegate = ThreadSafeUIDelegate()

    # Track thread IDs
    main_thread_id = threading.get_ident()
    worker_thread_ids = []

    worker = WorkflowWorker(rule, table, delegate)

    results = []
    worker.finished_signal.connect(lambda r: results.append(r))

    def on_progress(cur, total, name):
        worker_thread_ids.append(threading.get_ident())

    worker.progress_signal.connect(on_progress)

    worker.start()

    # Wait for completion while processing Qt events
    timeout = time.time() + 3.0
    while not results and time.time() < timeout:
        qapp.processEvents()
        QThread.msleep(20)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].variables.get("item_id") == "ITEM_999"

    # Confirm work ran on a separate worker thread
    assert worker.execution_thread_id is not None
    assert worker.execution_thread_id != main_thread_id


def test_thread_safe_ui_delegate_cross_thread_input(qapp):
    """Verify cross-thread user input and dialog communication."""
    delegate = ThreadSafeUIDelegate()

    input_received = []

    def mock_input_handler(prompt, default, event, result_box):
        result_box[0] = "user_entered_value"
        event.set()

    # Connect to custom handler for test
    delegate.input_requested.disconnect()
    delegate.input_requested.connect(mock_input_handler)

    # Call from a background thread
    def background_task():
        val = delegate.prompt_user("请输入内容", default="default")
        input_received.append(val)

    t = threading.Thread(target=background_task)
    t.start()

    timeout = time.time() + 2.0
    while not input_received and time.time() < timeout:
        qapp.processEvents()
        time.sleep(0.01)
    t.join(timeout=1.0)

    assert len(input_received) == 1
    assert input_received[0] == "user_entered_value"


def test_clipboard_watcher_debounce_and_watchdog(qapp):
    """Verify ClipboardWatcher handles debouncing and doesn't fire multiple times."""
    watcher = ClipboardWatcher(debounce_ms=50, watchdog_interval_ms=200)
    captured = []
    watcher.text_captured.connect(lambda t: captured.append(t))

    watcher.start_monitoring()

    # Simulate rapid OS dataChanged triggers
    watcher._last_content = "initial_seed"
    watcher._on_data_changed()
    watcher._on_data_changed()
    watcher._on_data_changed()

    # Mock the safe read to return new content
    watcher._safe_read_text = lambda: "debounced_excel_data\t123"

    # Process events to let debounce timer finish
    timeout = time.time() + 1.0
    while not captured and time.time() < timeout:
        qapp.processEvents()
        QThread.msleep(20)

    watcher.stop_monitoring()

    # Debounce ensured only 1 event fired despite 3 rapid signals!
    assert len(captured) == 1
    assert "debounced_excel_data" in captured[0]


def test_clipboard_watcher_loop_prevention(qapp):
    """Verify ClipboardWatcher ignores content written by the tool itself."""
    watcher = ClipboardWatcher(debounce_ms=20)
    captured = []
    watcher.text_captured.connect(lambda t: captured.append(t))

    watcher.start_monitoring()
    watcher.ignore_content("SELF_GENERATED_TSV")

    # When clipboard changes to the self-generated content
    watcher._process_text_if_new("SELF_GENERATED_TSV")
    watcher.stop_monitoring()

    # Must be ignored!
    assert len(captured) == 0


def test_delegate_show_toast_blocking_and_nonblocking(qapp):
    """Verify ThreadSafeUIDelegate emits toast_requested and handles blocking/non-blocking."""
    from src.gui.qt_delegate import ThreadSafeUIDelegate

    delegate = ThreadSafeUIDelegate()
    toast_log = []

    def mock_toast_handler(content, duration_ms, blocking, screen, position, event):
        toast_log.append({
            "content": content,
            "duration": duration_ms,
            "blocking": blocking,
            "screen": screen,
            "position": position
        })
        if event:
            event.set()

    delegate.toast_requested.disconnect()
    delegate.toast_requested.connect(mock_toast_handler)

    # Non-blocking call from background thread
    def call_non_blocking():
        delegate.show_toast("后台非阻塞冒泡", duration_ms=1500, blocking=False, screen="cursor", position="center")

    t1 = threading.Thread(target=call_non_blocking)
    t1.start()
    t1.join(timeout=1.0)

    timeout = time.time() + 1.0
    while not toast_log and time.time() < timeout:
        qapp.processEvents()
        time.sleep(0.01)

    assert len(toast_log) == 1
    assert toast_log[0]["blocking"] is False
    assert toast_log[0]["content"] == "后台非阻塞冒泡"

    # Blocking call from background thread
    blocking_done = []

    def call_blocking():
        delegate.show_toast("后台阻塞冒泡", duration_ms=1000, blocking=True, screen="all", position="top_center")
        blocking_done.append(True)

    t2 = threading.Thread(target=call_blocking)
    t2.start()

    timeout = time.time() + 1.0
    while not blocking_done and time.time() < timeout:
        qapp.processEvents()
        time.sleep(0.01)
    t2.join(timeout=1.0)

    assert len(toast_log) == 2
    assert toast_log[1]["blocking"] is True
    assert toast_log[1]["content"] == "后台阻塞冒泡"
    assert len(blocking_done) == 1


def test_worker_row_and_column_variables_exact_match(qapp):
    """Verify that row and column (and typo colunm) are properly available in worker for exact match."""
    rule = RuleConfig(
        name="尺寸精确测试规则",
        table_size=(3, 4),
        workflow=[
            {"action": "compute", "target_var": "r_val", "expression": "row"},
            {"action": "compute", "target_var": "c_val", "expression": "column"},
            {"action": "compute", "target_var": "typo_val", "expression": "colunm"},
            {"action": "compute", "target_var": "cells_count", "expression": "row * column"},
        ]
    )
    raw_tsv = "a1\tb1\tc1\td1\na2\tb2\tc2\td2\na3\tb3\tc3\td3"
    table = TableData.from_text(raw_tsv)
    assert table.rows == 3
    assert table.cols == 4

    delegate = ThreadSafeUIDelegate()
    worker = WorkflowWorker(rule, table, delegate)

    results = []
    worker.finished_signal.connect(lambda r: results.append(r))
    worker.start()

    timeout = time.time() + 3.0
    while not results and time.time() < timeout:
        qapp.processEvents()
        QThread.msleep(20)

    assert len(results) == 1
    res = results[0]
    assert res.success is True, f"Worker failed with error: {res.error}"
    assert res.variables.get("row") == "3"
    assert res.variables.get("column") == "4"
    assert res.variables.get("colunm") == "4"
    assert res.variables.get("r_val") == "3"
    assert res.variables.get("c_val") == "4"
    assert res.variables.get("typo_val") == "4"
    assert res.variables.get("cells_count") == "12"


def test_worker_row_and_column_variables_fuzzy_match(qapp):
    """Verify that row and column are set to actual copied dimensions even when fuzzy matching is enabled."""
    rule = RuleConfig(
        name="尺寸模糊测试规则",
        table_size=(1, 1),
        fuzzy_row=True,
        fuzzy_col=True,
        workflow=[
            {"action": "compute", "target_var": "r_val", "expression": "row"},
            {"action": "compute", "target_var": "c_val", "expression": "column"},
            {"action": "compute", "target_var": "typo_val", "expression": "colunm"},
            {"action": "compute", "target_var": "sum_dims", "expression": "row + column"},
        ]
    )
    # Copied table has 5 rows and 2 columns
    raw_tsv = "10\t20\n30\t40\n50\t60\n70\t80\n90\t100"
    table = TableData.from_text(raw_tsv)
    assert table.rows == 5
    assert table.cols == 2

    delegate = ThreadSafeUIDelegate()
    worker = WorkflowWorker(rule, table, delegate)

    results = []
    worker.finished_signal.connect(lambda r: results.append(r))
    worker.start()

    timeout = time.time() + 3.0
    while not results and time.time() < timeout:
        qapp.processEvents()
        QThread.msleep(20)

    assert len(results) == 1
    res = results[0]
    assert res.success is True, f"Worker failed with error: {res.error}"
    assert res.variables.get("row") == "5"
    assert res.variables.get("column") == "2"
    assert res.variables.get("colunm") == "2"
    assert res.variables.get("r_val") == "5"
    assert res.variables.get("c_val") == "2"
    assert res.variables.get("typo_val") == "2"
    assert res.variables.get("sum_dims") == "7"


def test_worker_plain_text_1x1_variables(qapp):
    """Verify that 1x1 plain text assigns row=1, column=1 to context variables."""
    rule = RuleConfig(
        name="纯文本1x1测试规则",
        table_size=(1, 1),
        workflow=[
            {"action": "compute", "target_var": "r_val", "expression": "row"},
            {"action": "compute", "target_var": "c_val", "expression": "column"},
        ]
    )
    table = TableData.from_text("plain single line string")
    assert table.rows == 1
    assert table.cols == 1

    delegate = ThreadSafeUIDelegate()
    worker = WorkflowWorker(rule, table, delegate)

    results = []
    worker.finished_signal.connect(lambda r: results.append(r))
    worker.start()

    timeout = time.time() + 3.0
    while not results and time.time() < timeout:
        qapp.processEvents()
        QThread.msleep(20)

    assert len(results) == 1
    res = results[0]
    assert res.success is True
    assert res.variables.get("row") == "1"
    assert res.variables.get("column") == "1"
    assert res.variables.get("colunm") == "1"


def test_worker_workflow_features_and_cancellation(qapp):
    """Verify that WorkflowWorker properly handles if/else branches, goto jumps, and cancellation."""
    # Test if/else and goto support in worker
    rule = RuleConfig(
        name="高级控制流规则",
        table_size=(2, 2),
        workflow=[
            {"action": "if_else", "condition": "row == 2", "then_count": 1, "else_count": 1},
            {"action": "compute", "target_var": "branch", "expression": "'THEN_BRANCH'"},
            {"action": "compute", "target_var": "branch", "expression": "'ELSE_BRANCH'"},
            {"action": "exit"},
            {"action": "compute", "target_var": "should_not_run", "expression": "'NO'"},
        ]
    )
    table = TableData.from_text("r1c1\tr1c2\nr2c1\tr2c2")
    delegate = ThreadSafeUIDelegate()
    worker = WorkflowWorker(rule, table, delegate)

    results = []
    worker.finished_signal.connect(lambda r: results.append(r))
    worker.start()

    timeout = time.time() + 3.0
    while not results and time.time() < timeout:
        qapp.processEvents()
        QThread.msleep(20)

    assert len(results) == 1
    res = results[0]
    assert res.success is True
    assert res.variables.get("branch") == "THEN_BRANCH"
    assert "should_not_run" not in res.variables


