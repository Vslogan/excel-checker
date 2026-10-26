"""Action package initialisation and registration."""
from src.core.actions.base import ActionRegistry, ActionResult, BaseAction
from src.core.actions.compute import ComputeAction
from src.core.actions.condition import ConditionAction
from src.core.actions.extract_cell import ExtractCellAction
from src.core.actions.file_ops import FileOpsAction
from src.core.actions.goto import GotoAction
from src.core.actions.http_request import HttpRequestAction
from src.core.actions.if_else import IfElseAction
from src.core.actions.show_message import ShowMessageAction
from src.core.actions.toast import ToastAction
from src.core.actions.user_input import UserInputAction
from src.core.actions.write_clipboard import WriteClipboardAction

# Register actions with standard names and Chinese aliases
ActionRegistry.register(
    "compute",
    ComputeAction,
    aliases=["计算", "算术运算", "四则运算", "calculate", "expr", "assignment", "赋值"],
)
ActionRegistry.register(
    "if_else",
    IfElseAction,
    aliases=["if", "ifelse", "如果", "条件选择", "选择结构"],
)
ActionRegistry.register(
    "goto",
    GotoAction,
    aliases=["跳转", "跳转行号", "jump"],
)
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
    "toast",
    ToastAction,
    aliases=["弹出冒泡窗", "冒泡窗", "toast", "notification", "bubble"],
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
    "ComputeAction",
    "IfElseAction",
    "GotoAction",
    "ExtractCellAction",
    "HttpRequestAction",
    "UserInputAction",
    "ShowMessageAction",
    "ToastAction",
    "WriteClipboardAction",
    "FileOpsAction",
    "ConditionAction",
]
