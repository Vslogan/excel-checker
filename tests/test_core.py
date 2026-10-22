from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from excel_checker.builtin_actions import build_default_registry
from excel_checker.clipboard import ClipboardMonitor
from excel_checker.config import load_rule_file, rule_from_dict, save_rule_file
from excel_checker.dispatcher import RuleDispatcher
from excel_checker.engine import RuleEngine
from excel_checker.errors import ActionExecutionError, ConfigError
from excel_checker.interfaces import HttpResponse
from excel_checker.parsing import parse_clipboard_text
from excel_checker.repository import RuleRepository


def make_document(
    *,
    name: str = "test",
    rows: int = 1,
    columns: int = 1,
    conditions: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    enabled: bool = True,
    priority: int = 0,
) -> dict[str, Any]:
    return {
        "version": 1,
        "name": name,
        "enabled": enabled,
        "priority": priority,
        "trigger": {
            "table_size": {"rows": rows, "columns": columns},
            "conditions": conditions or [],
        },
        "actions": actions or [],
    }


class FakeInteraction:
    def __init__(
        self, answers: list[str | None] | None = None, events: list[Any] | None = None
    ) -> None:
        self.answers = list(answers or [])
        self.prompts: list[str] = []
        self.notifications: list[str] = []
        self.events = events if events is not None else []

    def prompt(self, message: str) -> str | None:
        self.prompts.append(message)
        self.events.append(("prompt", message))
        return self.answers.pop(0) if self.answers else ""

    def notify(self, message: str) -> None:
        self.notifications.append(message)
        self.events.append(("notify", message))


class FakeClipboard:
    def __init__(self, text: str | None = "", events: list[Any] | None = None) -> None:
        self.text = text
        self.writes: list[str] = []
        self.events = events if events is not None else []

    def read_text(self) -> str | None:
        return self.text

    def write_text(self, text: str) -> None:
        self.writes.append(text)
        self.events.append(("clipboard", text))


class FakeHttp:
    def __init__(
        self, body: Any = None, error: Exception | None = None, events: list[Any] | None = None
    ) -> None:
        self.body = body
        self.error = error
        self.events = events if events is not None else []
        self.requests: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> HttpResponse:
        self.requests.append(kwargs)
        self.events.append(("http", kwargs))
        if self.error is not None:
            raise self.error
        return HttpResponse(200, {"content-type": "application/json"}, self.body)


class ClipboardParsingTests(unittest.TestCase):
    def test_plain_text_is_a_one_by_one_table(self) -> None:
        self.assertEqual(parse_clipboard_text("sample text"), [["sample text"]])

    def test_excel_tsv_and_final_line_ending(self) -> None:
        self.assertEqual(
            parse_clipboard_text("A\tB\r\n1\t2\r\n"),
            [["A", "B"], ["1", "2"]],
        )

    def test_trailing_empty_cell_and_blank_row_are_preserved(self) -> None:
        self.assertEqual(parse_clipboard_text("A\t\r\n"), [["A", ""]])
        self.assertEqual(parse_clipboard_text("A\n\n"), [["A"], [""]])

    def test_bom_is_removed(self) -> None:
        self.assertEqual(parse_clipboard_text("\ufeff123"), [["123"]])

    def test_quoted_cells_can_contain_tabs_and_newlines(self) -> None:
        self.assertEqual(parse_clipboard_text('A\t"B\tC"\r\n'), [["A", "B\tC"]])
        self.assertEqual(parse_clipboard_text('A\t"B\nC"\r\n'), [["A", "B\nC"]])


class RuleConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_size_and_regex_condition_must_both_match(self) -> None:
        rule = rule_from_dict(
            make_document(
                rows=1,
                columns=1,
                conditions=[{"cell": [0, 0], "regex": "[0-9]{3,}"}],
            ),
            registry=self.registry,
        )
        self.assertTrue(rule.matches([["1234"]]))
        self.assertFalse(rule.matches([["x1234"]]))
        self.assertFalse(rule.matches([["12"]]))
        self.assertFalse(rule.matches([["1234", "extra"]]))

    def test_ragged_input_does_not_match_a_configured_shape(self) -> None:
        rule = rule_from_dict(make_document(rows=2, columns=2), registry=self.registry)
        self.assertFalse(rule.matches([["a", "b"], ["c"]]))

    def test_invalid_rule_and_unknown_action_are_rejected(self) -> None:
        invalid_regex = make_document(conditions=[{"cell": [0, 0], "regex": "["}])
        with self.assertRaises(ConfigError):
            rule_from_dict(invalid_regex, registry=self.registry)

        unknown_action = make_document(actions=[{"action": "not_registered"}])
        with self.assertRaises(ConfigError):
            rule_from_dict(unknown_action, registry=self.registry)

    def test_invalid_callback_path_is_reported_as_config_error(self) -> None:
        document = make_document(
            actions=[
                {
                    "action": "http_request",
                    "method": "GET",
                    "url": "https://example.com",
                    "callback": {"value": "res.data["},
                }
            ]
        )
        with self.assertRaises(ConfigError):
            rule_from_dict(document, registry=self.registry)

    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rule.json"
            document = make_document(
                name="中文规则", actions=[{"action": "notify", "message": "你好"}]
            )
            saved = save_rule_file(path, document, registry=self.registry)
            loaded = load_rule_file(path, registry=self.registry)
            self.assertEqual(saved.to_dict(), loaded.to_dict())
            self.assertIn("中文规则", path.read_text(encoding="utf-8"))

    def test_dynamic_action_can_be_registered_and_executed(self) -> None:
        registry = build_default_registry()

        def set_flag(action: Any, context: Any) -> None:
            context.set_variable("flag", action["value"])

        registry.register("set_flag", set_flag, label="测试动作")
        rule = rule_from_dict(
            make_document(actions=[{"action": "set_flag", "value": True}]), registry=registry
        )
        result = RuleEngine(registry=registry).execute(rule, [["x"]])
        self.assertTrue(result.variables["flag"])


class RuleExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_actions_run_in_order_with_templating_and_http_callback(self) -> None:
        events: list[Any] = []
        interaction = FakeInteraction(answers=["2"], events=events)
        clipboard = FakeClipboard(events=events)
        http = FakeHttp(body={"res": {"data": ["server-value"]}}, events=events)
        actions = [
            {"action": "extract_cell", "cell": [0, 0], "variable": "id"},
            {
                "action": "http_request",
                "method": "post",
                "url": "https://example.test/items/{{id}}",
                "headers": {"X-Id": "{{id}}"},
                "body": {"item": "{{id}}"},
                "timeout_ms": 3210,
                "callback": {"newData": "res.data[0]"},
            },
            {"action": "user_input", "prompt": "pick for {{id}}", "variable": "index"},
            {"action": "notify", "message": "new={{newData}}, index={{index}}"},
            {
                "action": "clipboard_write",
                "type": "table",
                "data": [["{{id}}", "{{newData}}", "{{index}}"]],
            },
        ]
        rule = rule_from_dict(make_document(actions=actions), registry=self.registry)

        result = RuleEngine(
            registry=self.registry,
            interaction=interaction,
            clipboard=clipboard,
            http_client=http,
        ).execute(rule, [["12345"]])

        request = http.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "https://example.test/items/12345")
        self.assertEqual(request["headers"], {"X-Id": "12345"})
        self.assertEqual(request["body"], {"item": "12345"})
        self.assertEqual(request["timeout_ms"], 3210)
        self.assertEqual(interaction.prompts, ["pick for 12345"])
        self.assertEqual(interaction.notifications, ["new=server-value, index=2"])
        self.assertEqual(clipboard.writes, ["12345\tserver-value\t2\r\n"])
        self.assertEqual(result.variables["res"], {"data": ["server-value"]})
        self.assertEqual(result.variables["response"], {"res": {"data": ["server-value"]}})
        self.assertEqual(result.variables["newData"], "server-value")
        self.assertEqual(result.steps_executed, 5)
        self.assertEqual([event[0] for event in events], ["http", "prompt", "notify", "clipboard"])

    def test_csv_table_clipboard_data_is_written_as_excel_tsv(self) -> None:
        clipboard = FakeClipboard()
        rule = rule_from_dict(
            make_document(
                actions=[
                    {"action": "clipboard_write", "type": "table", "data": 'Name,Value\n"A, B",7'}
                ]
            ),
            registry=self.registry,
        )
        RuleEngine(registry=self.registry, clipboard=clipboard).execute(rule, [["x"]])
        self.assertEqual(clipboard.writes, ["Name\tValue\r\nA, B\t7\r\n"])

    def test_timeout_or_request_failure_stops_later_actions(self) -> None:
        interaction = FakeInteraction()
        http = FakeHttp(error=TimeoutError("timed out"))
        rule = rule_from_dict(
            make_document(
                actions=[
                    {
                        "action": "http_request",
                        "method": "GET",
                        "url": "https://example.test",
                        "timeout_ms": 10,
                    },
                    {"action": "notify", "message": "must not run"},
                ]
            ),
            registry=self.registry,
        )
        with self.assertRaisesRegex(ActionExecutionError, "步骤 1.*timed out"):
            RuleEngine(registry=self.registry, interaction=interaction, http_client=http).execute(
                rule, [["x"]]
            )
        self.assertEqual(interaction.notifications, [])

    def test_missing_template_variable_stops_execution(self) -> None:
        interaction = FakeInteraction()
        rule = rule_from_dict(
            make_document(actions=[{"action": "notify", "message": "{{notCreated}}"}]),
            registry=self.registry,
        )
        with self.assertRaisesRegex(ActionExecutionError, "尚未定义的变量"):
            RuleEngine(registry=self.registry, interaction=interaction).execute(rule, [["x"]])
        self.assertEqual(interaction.notifications, [])

    def test_cancelled_user_input_stops_later_steps(self) -> None:
        interaction = FakeInteraction(answers=[None])
        rule = rule_from_dict(
            make_document(
                actions=[
                    {"action": "user_input", "prompt": "输入", "variable": "answer"},
                    {"action": "notify", "message": "must not run"},
                ]
            ),
            registry=self.registry,
        )
        with self.assertRaisesRegex(ActionExecutionError, "取消了输入"):
            RuleEngine(registry=self.registry, interaction=interaction).execute(rule, [["x"]])
        self.assertEqual(interaction.notifications, [])

    def test_step_limit_protects_future_nested_flow_actions(self) -> None:
        registry = build_default_registry()

        def repeat_children(action: Any, context: Any) -> None:
            context.run_steps(action["steps"])

        registry.register("repeat", repeat_children)
        rule = rule_from_dict(
            make_document(
                actions=[{"action": "repeat", "steps": [{"action": "repeat", "steps": []}]}]
            ),
            registry=registry,
        )
        # Empty nested blocks do not consume further steps, so the root action completes.
        result = RuleEngine(registry=registry, max_steps=2).execute(rule, [["x"]])
        self.assertEqual(result.steps_executed, 2)


class DispatcherAndReloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_dispatcher_uses_highest_priority_enabled_match_only(self) -> None:
        low = rule_from_dict(
            make_document(name="low", priority=1, actions=[{"action": "notify", "message": "low"}]),
            registry=self.registry,
        )
        high = rule_from_dict(
            make_document(
                name="high", priority=2, actions=[{"action": "notify", "message": "high"}]
            ),
            registry=self.registry,
        )
        disabled = rule_from_dict(
            make_document(
                name="disabled",
                priority=10,
                enabled=False,
                actions=[{"action": "notify", "message": "bad"}],
            ),
            registry=self.registry,
        )
        interaction = FakeInteraction()
        outcome = RuleDispatcher(
            RuleEngine(registry=self.registry, interaction=interaction)
        ).process([["value"]], [low, disabled, high])
        self.assertEqual(outcome.matched_rule.name, "high")
        self.assertEqual(interaction.notifications, ["high"])

    def test_repository_hot_add_update_invalid_edit_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            first_path = directory / "first.json"
            save_rule_file(first_path, make_document(name="first"), registry=self.registry)
            repository = RuleRepository(directory, registry=self.registry)
            self.assertEqual([rule.name for rule in repository.rules], ["first"])

            second_path = directory / "second.json"
            save_rule_file(
                second_path, make_document(name="second", priority=3), registry=self.registry
            )
            self.assertTrue(repository.reload_if_changed())
            self.assertEqual([rule.name for rule in repository.rules], ["second", "first"])

            # Invalid edits report an error but retain last-known-good rule.
            first_path.write_text("{ bad json", encoding="utf-8")
            self.assertTrue(repository.reload_if_changed())
            self.assertIn(first_path, repository.errors)
            self.assertIn("first", [rule.name for rule in repository.rules])

            save_rule_file(first_path, make_document(name="first-updated"), registry=self.registry)
            self.assertTrue(repository.reload_if_changed())
            self.assertNotIn(first_path, repository.errors)
            self.assertIn("first-updated", [rule.name for rule in repository.rules])

            second_path.unlink()
            self.assertTrue(repository.reload_if_changed())
            self.assertNotIn("second", [rule.name for rule in repository.rules])

    def test_duplicate_rule_names_are_not_both_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            save_rule_file(directory / "a.json", make_document(name="same"), registry=self.registry)
            save_rule_file(directory / "b.json", make_document(name="same"), registry=self.registry)
            repository = RuleRepository(directory, registry=self.registry)
            self.assertEqual(len(repository.rules), 1)
            self.assertTrue(repository.errors)

    def test_monitor_ignores_initial_payload_and_duplicate_poll(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rule.json"
            save_rule_file(
                path,
                make_document(
                    conditions=[{"cell": [0, 0], "regex": "^X$"}],
                    actions=[{"action": "notify", "message": "triggered"}],
                ),
                registry=self.registry,
            )
            repository = RuleRepository(temp_dir, registry=self.registry)
            clipboard = FakeClipboard("X")
            interaction = FakeInteraction()
            monitor = ClipboardMonitor(
                clipboard,
                repository,
                RuleDispatcher(RuleEngine(registry=self.registry, interaction=interaction)),
                ignore_initial_clipboard=True,
            )
            self.assertIsNone(monitor.poll_once())  # existing content is only a baseline
            self.assertEqual(interaction.notifications, [])
            clipboard.text = "Y"
            self.assertFalse(monitor.poll_once().executed)
            clipboard.text = "X"
            self.assertTrue(monitor.poll_once().executed)
            self.assertIsNone(monitor.poll_once())
            self.assertEqual(interaction.notifications, ["triggered"])

    def test_monitor_reprocesses_same_text_after_explicit_change_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            save_rule_file(
                Path(temp_dir) / "rule.json",
                make_document(actions=[{"action": "notify", "message": "triggered"}]),
                registry=self.registry,
            )
            repository = RuleRepository(temp_dir, registry=self.registry)
            clipboard = FakeClipboard("X")
            interaction = FakeInteraction()
            monitor = ClipboardMonitor(
                clipboard,
                repository,
                RuleDispatcher(RuleEngine(registry=self.registry, interaction=interaction)),
            )
            self.assertIsNone(monitor.poll_once())
            monitor.reset_payload_cache()
            self.assertTrue(monitor.poll_once().executed)
            self.assertEqual(interaction.notifications, ["triggered"])

    def test_monitor_with_initially_unavailable_clipboard_runs_first_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            save_rule_file(
                Path(temp_dir) / "rule.json",
                make_document(actions=[{"action": "notify", "message": "triggered"}]),
                registry=self.registry,
            )
            repository = RuleRepository(temp_dir, registry=self.registry)
            clipboard = FakeClipboard(None)
            interaction = FakeInteraction()
            monitor = ClipboardMonitor(
                clipboard,
                repository,
                RuleDispatcher(RuleEngine(registry=self.registry, interaction=interaction)),
            )
            self.assertIsNone(monitor.poll_once())
            clipboard.text = "new copy"
            self.assertTrue(monitor.poll_once().executed)
            self.assertEqual(interaction.notifications, ["triggered"])


if __name__ == "__main__":
    unittest.main()
