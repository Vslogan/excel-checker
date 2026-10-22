"""Registry for built-in and future plug-in action blocks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Any, Protocol

from .context import ExecutionContext
from .errors import ActionError, ConfigError

ActionValidator = Callable[[Mapping[str, Any]], None]


class ActionHandler(Protocol):
    def __call__(self, action: Mapping[str, Any], context: ExecutionContext) -> None: ...


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    label: str
    handler: ActionHandler
    validator: ActionValidator | None = None
    form_schema: Mapping[str, Any] | None = None


class ActionRegistry:
    """Name-to-handler map; GUI block metadata lives alongside each handler."""

    def __init__(self) -> None:
        self._definitions: dict[str, ActionDefinition] = {}
        self._lock = RLock()

    def register(
        self,
        name: str,
        handler: ActionHandler,
        *,
        label: str | None = None,
        validator: ActionValidator | None = None,
        form_schema: Mapping[str, Any] | None = None,
        replace: bool = False,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("action name must be a non-empty string")
        definition = ActionDefinition(
            name=name,
            label=label or name,
            handler=handler,
            validator=validator,
            form_schema=form_schema,
        )
        with self._lock:
            if name in self._definitions and not replace:
                raise ValueError(f"action {name!r} is already registered")
            self._definitions[name] = definition

    def get(self, name: str) -> ActionDefinition:
        with self._lock:
            definition = self._definitions.get(name)
        if definition is None:
            raise ActionError(f"没有注册动作：{name}")
        return definition

    def validate(self, action: Mapping[str, Any]) -> None:
        name = action.get("action")
        if not isinstance(name, str):
            raise ConfigError("动作缺少字符串字段 action")
        try:
            definition = self.get(name)
        except ActionError as exc:
            raise ConfigError(str(exc)) from exc
        if definition.validator is not None:
            definition.validator(action)

    def definitions(self) -> tuple[ActionDefinition, ...]:
        with self._lock:
            return tuple(self._definitions[name] for name in sorted(self._definitions))
