"""Extract cell action implementation."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate
from src.core.expression import validate_variable_name


def parse_cell_position(pos: Any) -> Tuple[Any, Any]:
    """Parse raw cell position from tuple, list, dict, or string."""
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return pos[0], pos[1]
    if isinstance(pos, dict):
        r = pos.get("row", pos.get("r", pos.get("行", 0)))
        c = pos.get("col", pos.get("c", pos.get("列", 0)))
        return r, c
    if isinstance(pos, str):
        cleaned = pos.strip().strip("()[]")
        if "," in cleaned:
            parts = [p.strip() for p in cleaned.split(",", 1)]
            if parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
            return parts[0], parts[1]
        nums = re.findall(r"\d+", pos)
        if len(nums) >= 2:
            return int(nums[0]), int(nums[1])
    return 0, 0


def resolve_coordinate(val: Any, context: ExecutionContext, name: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Resolve coordinate to an integer:
    - Accepts integers directly
    - Accepts template strings e.g. '{{row_var}}'
    - Accepts direct variable names e.g. 'row_var'
    - Automatically converts to integer
    - If non-numeric, returns an error string
    """
    if val is None:
        return None, f"未指定{name}"

    if isinstance(val, int) and not isinstance(val, bool):
        return val, None

    if isinstance(val, float):
        return int(val), None

    s = str(val).strip()
    # Interpolate template string
    s = str(context.render_template(s)).strip()

    # If s matches a variable name in context
    if s in context.variables:
        var_val = context.variables[s]
        try:
            return int(float(str(var_val).strip())), None
        except (ValueError, TypeError):
            return None, f"{name}变量 '{s}' 的值 '{var_val}' 不是有效数字，无法用于提取单元格"

    try:
        return int(float(s)), None
    except (ValueError, TypeError):
        return None, f"{name}参数 '{val}' 不是有效数字，无法用于提取单元格 (解析结果: '{s}')"


class ExtractCellAction(BaseAction):
    """Action to extract data from a specific table cell into a context variable.
    Supports static numbers as well as variable names or {{variable}} templates."""

    action_type = "extract_cell"
    display_name = "提取某一格"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        cfg = self.config or {}
        self.raw_row = self._find_key(cfg, ["row", "行", "行号"])
        self.raw_col = self._find_key(cfg, ["col", "列", "列号"])
        self.position = self._find_key(cfg, ["position", "操作位置", "位置"])
        raw_var = self._find_key(cfg, ["variable", "暂存到的变量名", "暂存变量", "变量名"])
        self.variable = str(raw_var if raw_var is not None else "extracted_val").strip()

    @staticmethod
    def _find_key(cfg: Dict[str, Any], keys: list[str]) -> Any:
        for k in keys:
            if k in cfg and cfg[k] is not None:
                return cfg[k]
        return None

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        if not context.table_data:
            err = "表格数据为空，无法提取单元格"
            ui_delegate.log(f"[ExtractCell Error] {err}")
            return ActionResult.fail(err)

        if not validate_variable_name(self.variable):
            err = f"暂存变量名 '{self.variable}' 不合法: 必须以下划线或字母开头，只能包含字母、数字和下划线"
            ui_delegate.log(f"[ExtractCell Error] {err}")
            return ActionResult.fail(err)

        # Determine row and col candidate sources
        if self.raw_row is not None and self.raw_col is not None:
            r_candidate, c_candidate = self.raw_row, self.raw_col
        elif self.position is not None:
            r_candidate, c_candidate = parse_cell_position(self.position)
        else:
            r_candidate, c_candidate = 0, 0

        # Resolve coordinates with variable support and error checking
        row_num, err_r = resolve_coordinate(r_candidate, context, "行号")
        if err_r:
            ui_delegate.log(f"[ExtractCell Error] {err_r}")
            return ActionResult.fail(err_r)

        col_num, err_c = resolve_coordinate(c_candidate, context, "列号")
        if err_c:
            ui_delegate.log(f"[ExtractCell Error] {err_c}")
            return ActionResult.fail(err_c)

        val = context.table_data.get_cell(row_num, col_num)
        try:
            context.set_var(self.variable, val)
        except ValueError as e:
            return ActionResult.fail(str(e))

        msg = f"成功提取单元格 ({row_num}, {col_num}) 内容 -> 变量 '{self.variable}': '{val}'"
        ui_delegate.log(f"[ExtractCell] {msg}")
        return ActionResult.ok(val)
