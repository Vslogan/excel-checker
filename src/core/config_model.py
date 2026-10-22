"""Configuration model and validation for rules and workflows."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.actions.base import ActionRegistry
from src.core.actions.extract_cell import parse_cell_position
from src.core.table_parser import TableData


@dataclass
class ExtraCondition:
    """Extra cell matching condition based on regex."""
    row: int = 0
    col: int = 0
    regex: str = ""

    def matches(self, table: TableData) -> bool:
        if not self.regex:
            return True
        val = table.get_cell(self.row, self.col)
        try:
            return bool(re.search(self.regex, val))
        except re.error:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": [self.row, self.col],
            "regex": self.regex,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["ExtraCondition"]:
        if not data:
            return None
        if isinstance(data, dict):
            pos = data.get("position") or data.get("位置") or data.get("操作位置") or [0, 0]
            r, c = parse_cell_position(pos)
            rgx = data.get("regex") or data.get("正则表达式") or data.get("格式") or ""
            return cls(row=r, col=c, regex=str(rgx))
        if isinstance(data, (list, tuple)) and len(data) >= 2:
            r, c = parse_cell_position(data[0])
            return cls(row=r, col=c, regex=str(data[1]))
        return None


@dataclass
class RuleConfig:
    """Complete rule configuration containing trigger predicates and workflow actions."""

    name: str = "未命名规则"
    table_size: Tuple[int, int] = (1, 1)  # (rows, cols)
    extra_condition: Optional[ExtraCondition] = None
    workflow: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    file_path: Optional[str] = None

    def validate(self) -> List[str]:
        """Validate configuration integrity, returning list of validation errors."""
        errors: List[str] = []
        if not self.name.strip():
            errors.append("规则名称不能为空")

        if self.table_size[0] < 1 or self.table_size[1] < 1:
            errors.append(f"表格大小必须大于等于 1x1，当前为: {self.table_size[0]}x{self.table_size[1]}")

        if self.extra_condition and self.extra_condition.regex:
            try:
                re.compile(self.extra_condition.regex)
            except re.error as e:
                errors.append(f"额外条件的正则表达式无效: {e}")

        if not self.workflow:
            errors.append("流程中至少需要包含一个动作")
        else:
            for idx, act in enumerate(self.workflow):
                act_type = act.get("action") or act.get("动作") or act.get("action_type") or act.get("type")
                if not act_type:
                    errors.append(f"第 {idx + 1} 个动作缺少动作类型")
                elif not ActionRegistry.get_action_class(str(act_type)):
                    errors.append(f"第 {idx + 1} 个动作类型未知: '{act_type}'")

        return errors

    def matches(self, table: TableData) -> bool:
        """Check if clipboard table data matches this rule's trigger."""
        if not self.enabled:
            return False

        # 1. Check table size
        if not table.matches_size(self.table_size[0], self.table_size[1]):
            return False

        # 2. Check extra condition
        if self.extra_condition and not self.extra_condition.matches(table):
            return False

        return True

    def to_dict(self, use_chinese_keys: bool = False) -> Dict[str, Any]:
        """Serialize configuration to dict."""
        if use_chinese_keys:
            trigger_dict: Dict[str, Any] = {
                "表格大小": list(self.table_size)
            }
            if self.extra_condition and self.extra_condition.regex:
                trigger_dict["额外条件"] = {
                    "位置": [self.extra_condition.row, self.extra_condition.col],
                    "正则表达式": self.extra_condition.regex,
                }

            return {
                "配置名称": self.name,
                "触发该配置的前提": trigger_dict,
                "触发后的流程": self.workflow,
                "启用状态": self.enabled,
            }
        else:
            trigger_dict = {
                "table_size": list(self.table_size)
            }
            if self.extra_condition and self.extra_condition.regex:
                trigger_dict["extra_condition"] = self.extra_condition.to_dict()

            return {
                "name": self.name,
                "trigger": trigger_dict,
                "workflow": self.workflow,
                "enabled": self.enabled,
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], file_path: Optional[str] = None) -> "RuleConfig":
        """Parse dictionary with support for both Chinese and English keys."""
        # Rule Name
        name = (
            data.get("name")
            or data.get("配置名称")
            or data.get("规则名称")
            or "未命名规则"
        )

        # Trigger
        trigger_raw = (
            data.get("trigger")
            or data.get("触发该配置的前提")
            or data.get("前提")
            or {}
        )

        # Table Size
        size_raw = (
            trigger_raw.get("table_size")
            or trigger_raw.get("表格大小")
            or trigger_raw.get("大小")
            or [1, 1]
        )
        if isinstance(size_raw, (list, tuple)) and len(size_raw) >= 2:
            table_size = (int(size_raw[0]), int(size_raw[1]))
        elif isinstance(size_raw, dict):
            r = size_raw.get("rows", size_raw.get("row", 1))
            c = size_raw.get("cols", size_raw.get("col", 1))
            table_size = (int(r), int(c))
        elif isinstance(size_raw, str) and ("x" in size_raw or "*" in size_raw):
            parts = re.split(r"[x*]", size_raw)
            table_size = (int(parts[0].strip()), int(parts[1].strip()))
        else:
            table_size = (1, 1)

        # Extra condition
        extra_raw = (
            trigger_raw.get("extra_condition")
            or trigger_raw.get("额外条件")
            or trigger_raw.get("condition")
            or None
        )
        extra_cond = ExtraCondition.from_dict(extra_raw) if extra_raw else None

        # Workflow actions
        workflow_raw = (
            data.get("workflow")
            or data.get("触发后的流程")
            or data.get("流程")
            or data.get("actions")
            or []
        )
        if not isinstance(workflow_raw, list):
            workflow_raw = []

        # Enabled status
        enabled = data.get("enabled", data.get("启用状态", True))

        return cls(
            name=str(name),
            table_size=table_size,
            extra_condition=extra_cond,
            workflow=list(workflow_raw),
            enabled=bool(enabled),
            file_path=file_path,
        )

    def save_to_file(self, path: Optional[str] = None, use_chinese_keys: bool = False) -> str:
        """Save configuration to JSON file."""
        target_path = path or self.file_path
        if not target_path:
            raise ValueError("Target file path must be specified to save configuration.")

        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        content = self.to_dict(use_chinese_keys=use_chinese_keys)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

        self.file_path = target_path
        return target_path

    @classmethod
    def load_from_file(cls, path: str) -> "RuleConfig":
        """Load configuration from JSON file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls.from_dict(data, file_path=path)
