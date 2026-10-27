"""Toast notification action implementation."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import decode_escape_sequences


def parse_duration_ms(val: Any, default: int = 2000) -> int:
    """Parse duration value in ms or seconds."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        # If <= 30, assume seconds
        return int(val * 1000) if val <= 30 else int(val)
    if isinstance(val, str):
        cleaned = val.replace(",", "").strip().lower()
        if cleaned.endswith("ms"):
            nums = re.findall(r"[\d.]+", cleaned)
            return int(float(nums[0])) if nums else default
        elif cleaned.endswith("s"):
            nums = re.findall(r"[\d.]+", cleaned)
            return int(float(nums[0]) * 1000) if nums else default
        else:
            nums = re.findall(r"[\d.]+", cleaned)
            if nums:
                f = float(nums[0])
                return int(f * 1000) if f <= 30 else int(f)
    return default


class ToastAction(BaseAction):
    """Action to display an ephemeral floating toast notification."""

    action_type = "toast"
    display_name = "弹出冒泡窗"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.content = (
            self.config.get("content")
            if "content" in self.config
            else self.config.get("内容", "通知: 数据处理完成")
        )
        self.duration = (
            self.config.get("duration")
            or self.config.get("持续时间")
            or 2000
        )
        self.blocking = bool(
            self.config.get("blocking", self.config.get("是否阻塞", False))
        )
        self.screen = (
            self.config.get("screen")
            or self.config.get("显示的屏幕")
            or "cursor"
        )
        self.position = (
            self.config.get("position")
            or self.config.get("显示的位置")
            or "bottom_center"
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        # 1. Variable interpolation & escape decoding
        raw_rendered = context.render_template(self.content)
        if raw_rendered is None:
            rendered_content = ""
        else:
            rendered_content = decode_escape_sequences(str(raw_rendered)).strip()

        # Requirement 1: Supports empty content -> skip popup
        if not rendered_content:
            msg = "[Toast] 提示内容为空，已跳过显示弹窗"
            ui_delegate.log(msg)
            return ActionResult.ok({"skipped": True, "reason": "empty_content"})

        duration_ms = parse_duration_ms(self.duration)

        ui_delegate.log(
            f"[Toast] 弹出冒泡窗: '{rendered_content}' (时长={duration_ms}ms, 阻塞={self.blocking}, 屏幕={self.screen}, 位置={self.position})"
        )

        # Call delegate
        if hasattr(ui_delegate, "show_toast"):
            ui_delegate.show_toast(
                content=rendered_content,
                duration_ms=duration_ms,
                blocking=self.blocking,
                screen=self.screen,
                position=self.position,
            )
        else:
            ui_delegate.log(f"[Toast Display] {rendered_content}")

        return ActionResult.ok(rendered_content)
