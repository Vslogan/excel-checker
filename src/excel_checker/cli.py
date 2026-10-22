"""Small CLI used to validate and acceptance-test the engine before the Qt UI."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from typing import Any

from .builtin_actions import build_default_registry
from .clipboard import ClipboardMonitor
from .config import load_rule_file
from .dispatcher import RuleDispatcher
from .engine import RuleEngine
from .errors import ExcelCheckerError
from .parsing import parse_clipboard_text
from .repository import RuleRepository
from .system_clipboard import PyperclipAdapter


class ConsoleInteraction:
    def prompt(self, message: str) -> str | None:
        try:
            return input(f"{message}\n> ")
        except EOFError:
            return None

    def notify(self, message: str) -> None:
        print(f"[提示] {message}")


class StdoutClipboard:
    """Preview clipboard-write actions without changing the real clipboard."""

    def write_text(self, text: str) -> None:
        print("[剪切板内容开始]")
        print(text, end="" if text.endswith(("\n", "\r")) else "\n")
        print("[剪切板内容结束]")


def _engine(registry: Any, clipboard: Any) -> RuleEngine:
    return RuleEngine(
        registry=registry,
        interaction=ConsoleInteraction(),
        clipboard=clipboard,
    )


def _validate(args: argparse.Namespace) -> int:
    registry = build_default_registry()
    rule = load_rule_file(args.config, registry=registry)
    conditions = len(rule.conditions)
    print(
        f"配置有效：{rule.name}；触发表格 {rule.table_rows} 行 × {rule.table_columns} 列；"
        f"额外条件 {conditions} 条；动作 {len(rule.actions)} 个；"
        f"状态={'启用' if rule.enabled else '禁用'}"
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    registry = build_default_registry()
    rule = load_rule_file(args.config, registry=registry)
    text = args.text if args.text is not None else sys.stdin.read()
    table = parse_clipboard_text(text)
    if not rule.enabled:
        print(f"配置“{rule.name}”当前为禁用状态。")
        return 0
    if not rule.matches(table):
        print(f"未触发配置“{rule.name}”：输入数据为 {len(table)} 行。")
        return 0

    result = _engine(registry, StdoutClipboard()).execute(rule, table)
    print("执行完成。变量：")
    print(json.dumps(result.variables, ensure_ascii=False, indent=2, default=str))
    return 0


def _gui(_args: argparse.Namespace) -> int:
    try:
        from .qt_app import main as qt_main
    except ImportError as exc:
        raise ExcelCheckerError(
            f"无法加载 PyQt5 桌面依赖（{exc}）；请执行 python -m pip install -r requirements.txt"
        ) from exc
    return qt_main([])


def _watch(args: argparse.Namespace) -> int:
    registry = build_default_registry()
    clipboard = PyperclipAdapter()
    repository = RuleRepository(args.directory, registry=registry)
    engine = _engine(registry, clipboard)
    dispatcher = RuleDispatcher(engine)

    def report_result(outcome: Any) -> None:
        if outcome.matched_rule is None:
            return
        print(f"已触发配置：{outcome.matched_rule.name}")
        if outcome.execution is not None:
            print(json.dumps(outcome.execution.variables, ensure_ascii=False, default=str))

    def report_error(error: Exception) -> None:
        print(f"[错误] {error}", file=sys.stderr, flush=True)

    def report_config_errors(errors: dict[Any, str]) -> None:
        for path, message in errors.items():
            print(f"[配置警告] {path.name}: {message}", file=sys.stderr)

    report_config_errors(repository.errors)
    monitor = ClipboardMonitor(
        clipboard,
        repository,
        dispatcher,
        interval_seconds=args.interval,
        on_result=report_result,
        on_error=report_error,
        on_config_error=report_config_errors,
    )
    monitor.start()
    print(f"正在监控剪切板：{repository.directory.resolve()}（Ctrl+C 停止）", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="excel-checker",
        description="表格剪切板规则检查辅助工具（核心引擎验收版）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="检查 JSON 规则配置")
    validate.add_argument("config", help="规则 JSON 文件路径")
    validate.set_defaults(func=_validate)

    run = subparsers.add_parser("run", help="用一次性文本输入执行规则，便于验收")
    run.add_argument("config", help="规则 JSON 文件路径")
    run.add_argument("--text", help="输入文本；不传时从标准输入读取")
    run.set_defaults(func=_run)

    gui = subparsers.add_parser("gui", help="启动 PyQt5 桌面设置界面")
    gui.set_defaults(func=_gui)

    watch = subparsers.add_parser("watch", help="持续监控系统剪切板和规则目录")
    watch.add_argument("directory", help="包含一个或多个 .json 规则的目录")
    watch.add_argument("--interval", type=float, default=0.25, help="轮询间隔秒数（默认 0.25）")
    watch.set_defaults(func=_watch)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ExcelCheckerError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
