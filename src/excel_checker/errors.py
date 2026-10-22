"""Domain exceptions used by the core and its adapters."""

from __future__ import annotations


class ExcelCheckerError(Exception):
    """Base class for errors that are safe to report to an end user."""


class ConfigError(ExcelCheckerError):
    """A rule configuration is malformed or cannot be loaded."""


class ActionError(ExcelCheckerError):
    """An action could not complete."""


class TemplateError(ActionError):
    """A template variable or response path could not be resolved."""


class UserCancelledError(ActionError):
    """The user cancelled an interactive action."""


class ActionExecutionError(ActionError):
    """An action failed while a rule was running."""

    def __init__(self, message: str, *, step_index: int | None = None, action: str | None = None):
        self.step_index = step_index
        self.action = action
        if step_index is not None:
            label = f"步骤 {step_index}"
            if action:
                label += f"（{action}）"
            message = f"{label}执行失败：{message}"
        super().__init__(message)


class ClipboardError(ExcelCheckerError):
    """The system clipboard could not be read or written."""
