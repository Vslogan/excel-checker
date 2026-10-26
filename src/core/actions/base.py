"""Base action definition and dynamic action registry."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type

from src.core.context import ExecutionContext, UIDelegate


@dataclass
class ActionResult:
    """Result of executing an action."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    jump_to: Optional[int] = None
    skip_after: Optional[Tuple[int, int]] = None

    @classmethod
    def ok(
        cls,
        output: Any = None,
        jump_to: Optional[int] = None,
        skip_after: Optional[Tuple[int, int]] = None,
    ) -> "ActionResult":
        return cls(success=True, output=output, error=None, jump_to=jump_to, skip_after=skip_after)

    @classmethod
    def fail(cls, error: str) -> "ActionResult":
        return cls(success=False, output=None, error=error, jump_to=None, skip_after=None)


class BaseAction(abc.ABC):
    """Abstract base class for all workflow actions."""

    action_type: str = "base"
    display_name: str = "基础动作"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @abc.abstractmethod
    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        """Execute the action given context and UI delegate."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize action to dictionary."""
        d = dict(self.config)
        d["action"] = self.action_type
        return d


class ActionRegistry:
    """Registry for dynamically creating and extending actions."""

    _registry: Dict[str, Type[BaseAction]] = {}
    _aliases: Dict[str, str] = {}

    @classmethod
    def register(cls, action_type: str, action_cls: Type[BaseAction], aliases: Optional[list] = None):
        cls._registry[action_type] = action_cls
        if aliases:
            for alias in aliases:
                cls._aliases[alias] = action_type

    @classmethod
    def get_action_class(cls, action_type: str) -> Optional[Type[BaseAction]]:
        resolved_type = cls._aliases.get(action_type, action_type)
        return cls._registry.get(resolved_type)

    @classmethod
    def create(cls, config: Dict[str, Any]) -> BaseAction:
        raw_type = (
            config.get("action")
            or config.get("动作")
            or config.get("action_type")
            or config.get("type")
            or "unknown"
        )
        action_cls = cls.get_action_class(str(raw_type))
        if not action_cls:
            raise ValueError(f"Unknown action type: '{raw_type}'. Available: {list(cls._registry.keys())}")
        return action_cls(config)

    @classmethod
    def list_actions(cls) -> Dict[str, Dict[str, Any]]:
        """Return available action types and metadata for UI building."""
        result = {}
        for k, v in cls._registry.items():
            result[k] = {
                "action_type": k,
                "display_name": getattr(v, "display_name", k),
                "description": getattr(v, "__doc__", "")
            }
        return result
