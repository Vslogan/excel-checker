"""配置规则数据模型：JSON 加载/校验、变量模板替换。

配置文件示例（JSON）：

{
  "name": "示例配置",
  "trigger": {
    "size": {"rows": 2, "cols": 2},              # 必须：剪贴板表格大小
    "conditions": [                              # 可选：额外前置条件
      {"cell": [0, 0], "pattern": "[0-9]{3,}"}   # (0,0) 格须匹配正则
    ]
  },
  "steps": [                                     # 触发后按顺序执行的动作
    {"action": "extract_cell", "cell": [0, 0], "variable": "id"},
    {"action": "http_request", "method": "POST", "url": "http://example.com/{{id}}",
     "headers": {}, "body": {}, "timeout": 10000,
     "callback": {"newData": "res.data[0]"}},
    {"action": "user_input", "prompt": "请输入要提取第几个", "variable": "index"},
    {"action": "alert", "content": "新内容为{{newData}}"},
    {"action": "write_clipboard", "type": "table", "data": []}
  ]
}
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any

VAR_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class ConfigError(Exception):
    """配置文件格式或内容错误。"""


def substitute_template(text: str, variables: dict[str, Any]) -> str:
    """把文本中的 {{var}} 替换为变量值；找不到的变量保持原样，便于后续动作自行处理。"""

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return str(variables[name])
        return match.group(0)

    return VAR_PLACEHOLDER_RE.sub(_replace, text)


def substitute_in_value(value: Any, variables: dict[str, Any]) -> Any:
    """递归替换字符串/字典/列表中的模板变量（用于 header/body 等结构化参数）。"""
    if isinstance(value, str):
        return substitute_template(value, variables)
    if isinstance(value, dict):
        return {key: substitute_in_value(val, variables) for key, val in value.items()}
    if isinstance(value, list):
        return [substitute_in_value(item, variables) for item in value]
    return value


@dataclass
class Size:
    """触发前提中对表格大小的要求。"""

    rows: int
    cols: int

    @classmethod
    def from_dict(cls, data: Any) -> "Size":
        if not isinstance(data, dict) or "rows" not in data or "cols" not in data:
            raise ConfigError(f"触发条件 size 必须包含 rows/cols: {data!r}")
        rows = int(data["rows"])
        cols = int(data["cols"])
        if rows <= 0 or cols <= 0:
            raise ConfigError("size 的 rows/cols 必须为正整数")
        return cls(rows=rows, cols=cols)

    def to_dict(self) -> dict[str, int]:
        return {"rows": self.rows, "cols": self.cols}

    def matches(self, rows: int, cols: int) -> bool:
        return self.rows == rows and self.cols == cols


@dataclass
class CellCondition:
    """单元格额外条件：cell 位置的文本须匹配 pattern 正则。"""

    cell: tuple[int, int]
    pattern: str
    _compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._compiled = re.compile(self.pattern)

    def matches(self, table: list[list[str]]) -> bool:
        r, c = self.cell
        if r < 0 or r >= len(table):
            return False
        if c < 0 or c >= len(table[r]):
            return False
        return bool(self._compiled.search(table[r][c]))

    @classmethod
    def from_dict(cls, data: Any) -> "CellCondition":
        if not isinstance(data, dict) or "cell" not in data or "pattern" not in data:
            raise ConfigError(f"条件必须包含 cell 与 pattern: {data!r}")
        cell = data["cell"]
        if not (isinstance(cell, list) and len(cell) == 2):
            raise ConfigError(f"cell 必须是 [行, 列]: {cell!r}")
        return cls(cell=(int(cell[0]), int(cell[1])), pattern=str(data["pattern"]))

    def to_dict(self) -> dict[str, Any]:
        return {"cell": [self.cell[0], self.cell[1]], "pattern": self.pattern}


@dataclass
class Trigger:
    """触发前提：表格大小（必须）+ 额外单元格条件（可选）。"""

    size: Size
    conditions: list[CellCondition] = field(default_factory=list)

    def check(self, table: list[list[str]]) -> bool:
        rows = len(table)
        cols = max((len(r) for r in table), default=0)
        if not self.size.matches(rows, cols):
            return False
        return all(cond.matches(table) for cond in self.conditions)

    @classmethod
    def from_dict(cls, data: Any) -> "Trigger":
        if not isinstance(data, dict) or "size" not in data:
            raise ConfigError(f"触发条件必须包含 size: {data!r}")
        return cls(
            size=Size.from_dict(data["size"]),
            conditions=[CellCondition.from_dict(c) for c in data.get("conditions", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"size": self.size.to_dict(),
                "conditions": [c.to_dict() for c in self.conditions]}


# 支持的动作类型。后续新增动作只需在此集合加名，并在 Engine 里补 _do_<action> 方法即可。
KNOWN_ACTIONS = {
    "extract_cell",
    "http_request",
    "user_input",
    "alert",
    "write_clipboard",
}


@dataclass
class RuleConfig:
    """一条完整规则：名称 + 触发前提 + 动作步骤列表。"""

    name: str
    trigger: Trigger
    steps: list[dict[str, Any]]
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger.to_dict(),
            "steps": copy.deepcopy(self.steps),
        }

    @classmethod
    def from_dict(cls, data: Any, source_path: str | None = None) -> "RuleConfig":
        if not isinstance(data, dict):
            raise ConfigError(f"配置根必须是对象: {data!r}")
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("配置缺少 name")
        trigger = Trigger.from_dict(data.get("trigger", {}))
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            raise ConfigError("steps 必须是列表")
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "action" not in step:
                raise ConfigError(f"步骤 {i} 必须包含 action 字段")
            if step["action"] not in KNOWN_ACTIONS:
                raise ConfigError(f"步骤 {i} 未知动作: {step['action']!r}")
        return cls(name=name.strip(), trigger=trigger, steps=steps, source_path=source_path)

    @classmethod
    def load_file(cls, path: str) -> "RuleConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, source_path=path)

    def save_file(self, path: str | None = None) -> None:
        target = path or self.source_path
        if not target:
            raise ConfigError("未指定保存路径")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        self.source_path = target
