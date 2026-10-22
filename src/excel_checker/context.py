"""Mutable per-run context shared by dynamically registered actions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .interfaces import ClipboardWritePort, HttpClientPort, InteractionPort
from .templates import render_templates

ActionSpec = Mapping[str, Any]
StepRunner = Callable[[Sequence[ActionSpec]], None]


@dataclass
class ExecutionContext:
    table: list[list[str]]
    variables: dict[str, Any]
    interaction: InteractionPort
    clipboard: ClipboardWritePort
    http_client: HttpClientPort
    max_steps: int = 1000
    steps_executed: int = 0
    _step_runner: StepRunner | None = field(default=None, repr=False)

    def render(self, value: Any) -> Any:
        return render_templates(value, self.variables)

    def set_variable(self, name: str, value: Any) -> None:
        self.variables[name] = value

    def run_steps(self, steps: Sequence[ActionSpec]) -> None:
        """Run nested steps; this is the extension point for future flow blocks."""
        if self._step_runner is None:
            raise RuntimeError("本次执行没有配置嵌套步骤执行器")
        self._step_runner(steps)
