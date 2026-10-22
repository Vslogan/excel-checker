"""Rule model, JSON parsing, validation, and atomic persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import ConfigError
from .parsing import rectangular_dimensions

if TYPE_CHECKING:
    from .registry import ActionRegistry


@dataclass(frozen=True)
class CellCondition:
    row: int
    column: int
    regex: str


@dataclass(frozen=True)
class Rule:
    name: str
    table_rows: int
    table_columns: int
    actions: tuple[Mapping[str, Any], ...]
    conditions: tuple[CellCondition, ...] = ()
    enabled: bool = True
    priority: int = 0
    source: Path | None = None

    @property
    def table_size(self) -> tuple[int, int]:
        return self.table_rows, self.table_columns

    def matches(self, table: Sequence[Sequence[object]]) -> bool:
        dimensions = rectangular_dimensions(table)
        if dimensions != self.table_size:
            return False
        for condition in self.conditions:
            try:
                value = str(table[condition.row][condition.column])
            except IndexError:
                return False
            if re.fullmatch(condition.regex, value) is None:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "trigger": {
                "table_size": {"rows": self.table_rows, "columns": self.table_columns},
                "conditions": [
                    {"cell": [condition.row, condition.column], "regex": condition.regex}
                    for condition in self.conditions
                ],
            },
            "actions": deepcopy(list(self.actions)),
        }


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{label} 必须是 JSON 对象")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{label} 必须是大于 0 的整数")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"{label} 必须是大于或等于 0 的整数")
    return value


def rule_from_dict(
    document: Any,
    *,
    source: Path | None = None,
    registry: ActionRegistry | None = None,
) -> Rule:
    """Validate a parsed JSON value and return an immutable rule shell."""
    root = _mapping(document, "配置根节点")
    version = root.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ConfigError(f"不支持的配置版本：{version!r}（当前支持 version=1）")

    name = root.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("配置字段 name 必须是非空字符串")

    enabled = root.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError("配置字段 enabled 必须是布尔值")

    priority = root.get("priority", 0)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ConfigError("配置字段 priority 必须是整数")

    trigger = _mapping(root.get("trigger"), "trigger")
    table_size = _mapping(trigger.get("table_size"), "trigger.table_size")
    rows = _positive_int(table_size.get("rows"), "trigger.table_size.rows")
    columns = _positive_int(table_size.get("columns"), "trigger.table_size.columns")

    raw_conditions = trigger.get("conditions", [])
    if not isinstance(raw_conditions, list):
        raise ConfigError("trigger.conditions 必须是数组")
    conditions: list[CellCondition] = []
    for index, raw_condition in enumerate(raw_conditions):
        condition = _mapping(raw_condition, f"trigger.conditions[{index}]")
        cell = condition.get("cell")
        if not isinstance(cell, list) or len(cell) != 2:
            raise ConfigError(f"trigger.conditions[{index}].cell 必须是 [行, 列]")
        row = _non_negative_int(cell[0], f"trigger.conditions[{index}].cell[0]")
        column = _non_negative_int(cell[1], f"trigger.conditions[{index}].cell[1]")
        if row >= rows or column >= columns:
            raise ConfigError(f"trigger.conditions[{index}].cell 超出了配置的表格大小")
        pattern = condition.get("regex")
        if not isinstance(pattern, str) or not pattern:
            raise ConfigError(f"trigger.conditions[{index}].regex 必须是非空字符串")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"trigger.conditions[{index}].regex 无效：{exc}") from exc
        conditions.append(CellCondition(row, column, pattern))

    raw_actions = root.get("actions")
    if not isinstance(raw_actions, list):
        raise ConfigError("actions 必须是数组")
    actions: list[Mapping[str, Any]] = []
    for index, raw_action in enumerate(raw_actions):
        action = _mapping(raw_action, f"actions[{index}]")
        action_name = action.get("action")
        if not isinstance(action_name, str) or not action_name.strip():
            raise ConfigError(f"actions[{index}].action 必须是非空字符串")
        copied = deepcopy(dict(action))
        if registry is not None:
            try:
                registry.validate(copied)
            except ConfigError as exc:
                raise ConfigError(f"actions[{index}]：{exc}") from exc
        actions.append(copied)

    return Rule(
        name=name.strip(),
        table_rows=rows,
        table_columns=columns,
        actions=tuple(actions),
        conditions=tuple(conditions),
        enabled=enabled,
        priority=priority,
        source=source,
    )


def load_rule_file(path: str | Path, *, registry: ActionRegistry | None = None) -> Rule:
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件 {file_path}：{exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"JSON 格式错误（{file_path}:{exc.lineno}:{exc.colno}）：{exc.msg}"
        ) from exc
    try:
        return rule_from_dict(document, source=file_path, registry=registry)
    except ConfigError as exc:
        raise ConfigError(f"配置文件 {file_path} 无效：{exc}") from exc


def save_rule_file(
    path: str | Path,
    document: Mapping[str, Any] | Rule,
    *,
    registry: ActionRegistry | None = None,
) -> Rule:
    """Validate and atomically write one UTF-8 JSON rule file."""
    file_path = Path(path)
    data = document.to_dict() if isinstance(document, Rule) else deepcopy(dict(document))
    rule = rule_from_dict(data, source=file_path, registry=registry)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(rule.to_dict(), ensure_ascii=False, indent=2) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(serialized)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, file_path)
    except OSError as exc:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ConfigError(f"无法保存配置文件 {file_path}：{exc}") from exc
    return rule
