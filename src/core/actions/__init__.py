"""Action package initialisation and registration."""
from src.core.actions.base import ActionRegistry, ActionResult, BaseAction
from src.core.actions.condition import ConditionAction
from src.core.actions.extract_cell import ExtractCellAction
from src.core.actions.file_ops import FileOpsAction
from src.core.actions.http_request import HttpRequestAction
from src.core.actions.show_message import ShowMessageAction
from src.core.actions.user_input import UserInputAction
from src.core.actions.write_clipboard import WriteClipboardAction

# Register actions with standard names and Chinese aliases
ActionRegistry.register(
    "extract_cell",
    ExtractCellAction,
    aliases=["提取某一格", "提取单元格", "extract", "cell"],
)
ActionRegistry.register(
    "http_request",
    HttpRequestAction,
    aliases=["发网络请求", "网络请求", "http", "request", "post", "get"],
)
ActionRegistry.register(
    "user_input",
    UserInputAction,
    aliases=["用户输入", "输入框", "input", "alert_input", "prompt"],
)
ActionRegistry.register(
    "show_message",
    ShowMessageAction,
    aliases=["弹出提示框", "提示框", "show_alert", "alert", "message"],
)
ActionRegistry.register(
    "write_clipboard",
    WriteClipboardAction,
    aliases=["写入剪切板", "剪贴板", "clipboard", "copy"],
)
ActionRegistry.register(
    "file_ops",
    FileOpsAction,
    aliases=["文件读写", "文件操作", "file"],
)
ActionRegistry.register(
    "condition",
    ConditionAction,
    aliases=["条件判断", "条件分支", "if", "branch"],
)

__all__ = [
    "BaseAction",
    "ActionResult",
    "ActionRegistry",
    "ExtractCellAction",
    "HttpRequestAction",
    "UserInputAction",
    "ShowMessageAction",
    "WriteClipboardAction",
    "FileOpsAction",
    "ConditionAction",
]
