"""File read and write actions for future extensibility."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate


class FileOpsAction(BaseAction):
    """Action to read or write local files."""

    action_type = "file_ops"
    display_name = "文件读写"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.operation = (
            self.config.get("operation")
            or self.config.get("操作")
            or "write"
        ).lower()
        self.file_path = (
            self.config.get("path")
            or self.config.get("file_path")
            or self.config.get("文件路径")
            or ""
        )
        self.content = (
            self.config.get("content")
            or self.config.get("内容")
            or ""
        )
        self.variable = (
            self.config.get("variable")
            or self.config.get("暂存变量")
            or "file_content"
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        rendered_path = context.render_template(self.file_path)
        if not rendered_path:
            return ActionResult.fail("文件路径不能为空")

        try:
            if self.operation in ("read", "读取"):
                if not os.path.exists(rendered_path):
                    return ActionResult.fail(f"文件不存在: {rendered_path}")
                with open(rendered_path, "r", encoding="utf-8") as f:
                    content = f.read()
                context.set_var(self.variable, content)
                ui_delegate.log(f"[FileOps] Read {len(content)} chars from {rendered_path} -> '{self.variable}'")
                return ActionResult.ok(content)
            elif self.operation in ("write", "写入", "overwrite"):
                os.makedirs(os.path.dirname(os.path.abspath(rendered_path)), exist_ok=True)
                rendered_content = context.render_template(self.content)
                with open(rendered_path, "w", encoding="utf-8") as f:
                    f.write(rendered_content)
                ui_delegate.log(f"[FileOps] Wrote to {rendered_path}")
                return ActionResult.ok(rendered_content)
            elif self.operation in ("append", "追加"):
                os.makedirs(os.path.dirname(os.path.abspath(rendered_path)), exist_ok=True)
                rendered_content = context.render_template(self.content)
                with open(rendered_path, "a", encoding="utf-8") as f:
                    f.write(rendered_content)
                ui_delegate.log(f"[FileOps] Appended to {rendered_path}")
                return ActionResult.ok(rendered_content)
            else:
                return ActionResult.fail(f"不支持的文件操作类型: {self.operation}")
        except Exception as e:
            return ActionResult.fail(f"文件操作失败: {str(e)}")
