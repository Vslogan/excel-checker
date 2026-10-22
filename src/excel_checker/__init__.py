"""Core library for configurable spreadsheet clipboard checking."""

from .builtin_actions import build_default_registry
from .clipboard import ClipboardMonitor
from .config import Rule, load_rule_file, rule_from_dict, save_rule_file
from .dispatcher import ProcessOutcome, RuleDispatcher
from .engine import ExecutionResult, RuleEngine
from .parsing import parse_clipboard_text
from .repository import RuleRepository

__all__ = [
    "ClipboardMonitor",
    "ExecutionResult",
    "ProcessOutcome",
    "Rule",
    "RuleDispatcher",
    "RuleEngine",
    "RuleRepository",
    "build_default_registry",
    "load_rule_file",
    "parse_clipboard_text",
    "rule_from_dict",
    "save_rule_file",
]
