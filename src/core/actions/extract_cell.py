"""Extract cell action implementation."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate


def parse_cell_position(pos: Any) -> Tuple[int, int]:
    """Parse cell position from tuple, list, or string e.g. (0,0), [0, 0], '0,0'."""
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return int(pos[0]), int(pos[1])
    if isinstance(pos, str):
        nums = re.findall(r"\d+", pos)
        if len(nums) >= 2:
            return int(nums[0]), int(nums[1])
    if isinstance(pos, dict):
        r = pos.get("row", pos.get("r", 0))
        c = pos.get("col", pos.get("c", 0))
        return int(r), int(c)
    return 0, 0


class ExtractCellAction(BaseAction):
    """Action to extract data from a specific table cell into a context variable."""

    action_type = "extract_cell"
    display_name = "提取某一格"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.position = (
            self.config.get("position")
            or self.config.get("操作位置")
            or [0, 0]
        )
        self.variable = (
            self.config.get("variable")
            or self.config.get("暂存到的变量名")
            or "extracted_val"
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        row, col = parse_cell_position(self.position)
        if not context.table_data:
            err = "表格数据为空，无法提取单元格"
            ui_delegate.log(f"[ExtractCell Error] {err}")
            return ActionResult.fail(err)

        val = context.table_data.get_cell(row, col)
        context.set_var(self.variable, val)
        msg = f"成功提取单元格 ({row}, {col}) 内容 -> 变量 '{self.variable}': '{val}'"
        ui_delegate.log(f"[ExtractCell] {msg}")
        return ActionResult.ok(val)
