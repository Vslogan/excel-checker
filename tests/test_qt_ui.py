from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtCore import QEventLoop, Qt, QTimer
    from PyQt5.QtWidgets import QApplication

    from excel_checker.builtin_actions import build_default_registry
    from excel_checker.config import save_rule_file
    from excel_checker.qt_app import ActionEditorDialog, MainWindow
except ImportError as exc:  # PyQt5 is an optional dependency, and headless hosts may lack libGL.
    QT_IMPORT_ERROR: str | None = str(exc)
else:
    QT_IMPORT_ERROR = None


@unittest.skipIf(QT_IMPORT_ERROR is not None, f"PyQt5 unavailable: {QT_IMPORT_ERROR}")
class QtFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_action_editor_round_trips_a_http_action(self) -> None:
        registry = build_default_registry()
        action = {
            "action": "http_request",
            "method": "POST",
            "url": "https://example.test/{{id}}",
            "headers": {"X-ID": "{{id}}"},
            "body": {"id": "{{id}}"},
            "timeout_ms": 4321,
            "callback": {"newData": "res.data[0]"},
        }
        dialog = ActionEditorDialog(registry, action)
        try:
            self.assertEqual(dialog.action_data(), action)
        finally:
            dialog.close()

    def test_main_window_creates_and_saves_a_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            window = MainWindow(temp_dir)
            try:
                window._new_rule()
                self.assertEqual(window.rule_list.count(), 1)
                self.assertTrue(window._current_path.exists())
                self.assertEqual(window.name_edit.text(), "新规则")
                self.assertEqual(window._current_rule.table_size, (1, 1))
            finally:
                window.close()
                self.application.processEvents()

    def test_rule_check_state_is_persisted_to_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = build_default_registry()
            path = Path(temp_dir) / "enabled.json"
            save_rule_file(
                path,
                {
                    "version": 1,
                    "name": "enabled rule",
                    "enabled": True,
                    "trigger": {"table_size": {"rows": 1, "columns": 1}},
                    "actions": [],
                },
                registry=registry,
            )
            window = MainWindow(temp_dir)
            try:
                window.rule_list.item(0).setCheckState(Qt.Unchecked)
                self.application.processEvents()
                self.assertFalse(window._current_rule.enabled)
            finally:
                window.close()
                self.application.processEvents()

    def test_clipboard_match_runs_in_worker_and_writes_via_gui_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = build_default_registry()
            rule_path = Path(temp_dir) / "copy.json"
            save_rule_file(
                rule_path,
                {
                    "version": 1,
                    "name": "copy",
                    "enabled": True,
                    "trigger": {
                        "table_size": {"rows": 1, "columns": 1},
                        "conditions": [{"cell": [0, 0], "regex": "^input$"}],
                    },
                    "actions": [
                        {"action": "user_input", "prompt": "请输入确认值", "variable": "answer"},
                        {
                            "action": "clipboard_write",
                            "type": "text",
                            "data": "{{answer}}",
                        },
                    ],
                },
                registry=registry,
            )
            window = MainWindow(temp_dir)
            loop = QEventLoop()
            window.runner.job_finished.connect(lambda _result: loop.quit())
            try:
                window._refresh_rule_list(rule_path)
                window.monitor_checkbox.setChecked(True)
                QApplication.clipboard().setText("input")
                self.application.processEvents()
                with patch(
                    "excel_checker.qt_app.QInputDialog.getText",
                    return_value=("accepted", True),
                ):
                    window._poll_clipboard()
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec_()
                self.assertEqual(QApplication.clipboard().text(), "accepted")
                self.assertEqual(window.runner.pending_count, 0)
            finally:
                window.close()
                self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
