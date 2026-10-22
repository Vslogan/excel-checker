"""Sequential rule execution engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .builtin_actions import build_default_registry
from .context import ExecutionContext
from .errors import ActionError, ActionExecutionError
from .http_client import UrllibHttpClient
from .interfaces import ClipboardWritePort, HttpClientPort, InteractionPort
from .registry import ActionRegistry


@dataclass(frozen=True)
class ExecutionResult:
    rule_name: str
    variables: Mapping[str, Any]
    steps_executed: int


class _MissingInteraction:
    def prompt(self, message: str) -> str | None:
        raise ActionError("当前运行环境没有配置用户输入界面")

    def notify(self, message: str) -> None:
        raise ActionError("当前运行环境没有配置提示界面")


class _MissingClipboard:
    def write_text(self, text: str) -> None:
        raise ActionError("当前运行环境没有配置剪切板写入接口")


class RuleEngine:
    """Execute actions in order and stop immediately on the first failure."""

    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        interaction: InteractionPort | None = None,
        clipboard: ClipboardWritePort | None = None,
        http_client: HttpClientPort | None = None,
        max_steps: int = 1000,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.registry = registry or build_default_registry()
        self.interaction = interaction or _MissingInteraction()
        self.clipboard = clipboard or _MissingClipboard()
        self.http_client = http_client or UrllibHttpClient()
        self.max_steps = max_steps

    def execute(self, rule: Any, table: Sequence[Sequence[object]]) -> ExecutionResult:
        context = ExecutionContext(
            table=[[str(cell) for cell in row] for row in table],
            variables={},
            interaction=self.interaction,
            clipboard=self.clipboard,
            http_client=self.http_client,
            max_steps=self.max_steps,
        )
        context._step_runner = lambda steps: self._execute_steps(steps, context)
        self._execute_steps(rule.actions, context)
        return ExecutionResult(
            rule_name=rule.name,
            variables=dict(context.variables),
            steps_executed=context.steps_executed,
        )

    def _execute_steps(self, steps: Sequence[Mapping[str, Any]], context: ExecutionContext) -> None:
        for index, action in enumerate(steps, start=1):
            action_name = action.get("action", "<unknown>")
            context.steps_executed += 1
            if context.steps_executed > context.max_steps:
                raise ActionExecutionError(
                    f"超过最大动作数限制 {context.max_steps}，已停止以防止无限循环",
                    step_index=index,
                    action=str(action_name),
                )
            try:
                definition = self.registry.get(str(action_name))
                definition.handler(action, context)
            except ActionExecutionError:
                raise
            except Exception as exc:
                raise ActionExecutionError(
                    str(exc) or type(exc).__name__,
                    step_index=index,
                    action=str(action_name),
                ) from exc
