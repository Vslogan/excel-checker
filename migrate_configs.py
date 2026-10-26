#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Excel Checker - Standalone Configuration Migration & Verification Tool.

This script upgrades older JSON configuration files to the newest schema format.
It is completely standalone with ZERO external dependencies (standard library only).

Usage:
    python3 migrate_configs.py                   # Migrate all configs in configs/
    python3 migrate_configs.py --file path.json  # Migrate a specific file
    python3 migrate_configs.py --check-only      # Dry-run check without writing files
    python3 migrate_configs.py --backup          # Create .bak backups before writing
    python3 migrate_configs.py --lang chinese    # Normalize all keys to Chinese
    python3 migrate_configs.py --lang english    # Normalize all keys to English
"""

import argparse
import copy
import glob
import json
import os
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple


IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Mapping of standard Chinese <-> English keys
ROOT_KEYS_EN_TO_ZH = {
    "name": "配置名称",
    "trigger": "触发该配置的前提",
    "workflow": "触发后的流程",
    "enabled": "启用状态",
}
ROOT_KEYS_ZH_TO_EN = {v: k for k, v in ROOT_KEYS_EN_TO_ZH.items()}

TRIGGER_KEYS_EN_TO_ZH = {
    "table_size": "表格大小",
    "fuzzy_row": "模糊行数",
    "fuzzy_col": "模糊列数",
    "extra_conditions": "额外条件列表",
    "extra_condition": "额外条件",
}
TRIGGER_KEYS_ZH_TO_EN = {v: k for k, v in TRIGGER_KEYS_EN_TO_ZH.items()}

ACTION_NAME_MAP = {
    # Chinese aliases -> Canonical Chinese
    "提取某一格": "提取某一格",
    "提取单元格": "提取某一格",
    "extract_cell": "提取某一格",
    "发网络请求": "发网络请求",
    "网络请求": "发网络请求",
    "http_request": "发网络请求",
    "用户输入": "用户输入",
    "输入": "用户输入",
    "prompt_input": "用户输入",
    "弹出提示框": "弹出提示框",
    "提示框": "弹出提示框",
    "show_message": "弹出提示框",
    "写入剪切板": "写入剪切板",
    "写剪切板": "写入剪切板",
    "write_clipboard": "写入剪切板",
    "弹出冒泡窗": "弹出冒泡窗",
    "冒泡窗": "弹出冒泡窗",
    "toast": "弹出冒泡窗",
    "计算": "计算",
    "compute": "计算",
    "如果": "如果",
    "条件分支": "如果",
    "if_else": "如果",
    "跳转": "跳转",
    "跳转行号": "跳转",
    "goto": "跳转",
    "退出": "退出",
    "结束": "退出",
    "exit": "退出",
}

CANONICAL_ZH_TO_EN_ACTION = {
    "提取某一格": "extract_cell",
    "发网络请求": "http_request",
    "用户输入": "prompt_input",
    "弹出提示框": "show_message",
    "写入剪切板": "write_clipboard",
    "弹出冒泡窗": "toast",
    "计算": "compute",
    "如果": "if_else",
    "跳转": "goto",
    "退出": "exit",
}


def sanitize_identifier(name: str, fallback_prefix: str = "var") -> str:
    """Sanitize arbitrary string into a valid variable identifier."""
    if not name:
        return f"{fallback_prefix}_1"
    # Replace invalid chars with underscores
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip())
    # Strip leading/trailing underscores
    cleaned = cleaned.strip("_")
    if not cleaned:
        return f"{fallback_prefix}_1"
    # Cannot start with a digit
    if cleaned[0].isdigit():
        cleaned = f"v_{cleaned}"
    return cleaned


class ConfigMigrationReport:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.changes: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.modified: bool = False

    def add_change(self, msg: str):
        self.changes.append(msg)
        self.modified = True

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_error(self, msg: str):
        self.errors.append(msg)

    @property
    def is_ok(self) -> bool:
        return len(self.errors) == 0


class ConfigMigrator:
    def __init__(self, lang: str = "keep"):
        """Args: lang: 'keep' (preserves original language), 'chinese', or 'english'."""
        self.lang = lang

    def migrate(self, raw_data: Dict[str, Any], report: ConfigMigrationReport) -> Dict[str, Any]:
        """Upgrade and validate a configuration dictionary."""
        # 1. Detect language preference
        has_zh_keys = any(k in raw_data for k in ("配置名称", "触发该配置的前提", "触发后的流程"))
        target_zh = True if self.lang == "chinese" else (False if self.lang == "english" else has_zh_keys)

        # 2. Extract and upgrade root fields
        name = str(raw_data.get("配置名称") or raw_data.get("name") or "未命名规则").strip()
        enabled = raw_data.get("启用状态") if "启用状态" in raw_data else raw_data.get("enabled", True)
        if not isinstance(enabled, bool):
            enabled = True
            report.add_change("规范化 '启用状态' 为布尔值: True")

        # 3. Extract and upgrade Trigger
        trigger_raw = (
            raw_data.get("触发该配置的前提")
            or raw_data.get("trigger")
            or raw_data.get("前提")
            or {}
        )
        if not isinstance(trigger_raw, dict):
            trigger_raw = {}
            report.add_change("触发前提不是对象字典，已初始化为空字典")

        upgraded_trigger = self._migrate_trigger(trigger_raw, target_zh, report)

        # 4. Extract and upgrade Workflow
        workflow_raw = (
            raw_data.get("触发后的流程")
            or raw_data.get("workflow")
            or raw_data.get("流程")
            or []
        )
        if not isinstance(workflow_raw, list):
            workflow_raw = []
            report.add_change("触发后的流程不是列表，已重置为空列表")

        upgraded_workflow = self._migrate_workflow(workflow_raw, target_zh, report)

        # 5. Assemble final dictionary
        if target_zh:
            final_data = {
                "配置名称": name,
                "触发该配置的前提": upgraded_trigger,
                "触发后的流程": upgraded_workflow,
                "启用状态": enabled,
            }
        else:
            final_data = {
                "name": name,
                "trigger": upgraded_trigger,
                "workflow": upgraded_workflow,
                "enabled": enabled,
            }

        return final_data

    def _migrate_trigger(
        self, trigger_raw: Dict[str, Any], target_zh: bool, report: ConfigMigrationReport
    ) -> Dict[str, Any]:
        # Table size parsing
        size_raw = (
            trigger_raw.get("表格大小")
            or trigger_raw.get("table_size")
            or trigger_raw.get("大小")
            or [1, 1]
        )
        raw_row, raw_col = 1, 1
        if isinstance(size_raw, (list, tuple)) and len(size_raw) >= 2:
            raw_row, raw_col = size_raw[0], size_raw[1]
        elif isinstance(size_raw, str) and ("x" in size_raw or "*" in size_raw):
            parts = re.split(r"[x*]", size_raw)
            raw_row, raw_col = parts[0].strip(), parts[1].strip()
            report.add_change(f"解析字符串尺寸 '{size_raw}' 为维度: [{raw_row}, {raw_col}]")
        elif isinstance(size_raw, dict):
            raw_row = size_raw.get("rows", size_raw.get("row", size_raw.get("行", 1)))
            raw_col = size_raw.get("cols", size_raw.get("col", size_raw.get("列", 1)))

        fuzzy_row = bool(
            trigger_raw.get("模糊行数", False)
            or trigger_raw.get("fuzzy_row", False)
            or str(raw_row) in ("*", "-1", "模糊")
            or (isinstance(raw_row, (int, float)) and raw_row <= 0)
        )
        fuzzy_col = bool(
            trigger_raw.get("模糊列数", False)
            or trigger_raw.get("fuzzy_col", False)
            or str(raw_col) in ("*", "-1", "模糊")
            or (isinstance(raw_col, (int, float)) and raw_col <= 0)
        )

        try:
            row_dim = int(raw_row) if not fuzzy_row else 1
            if row_dim <= 0:
                row_dim = 1
                fuzzy_row = True
        except Exception:
            row_dim = 1

        try:
            col_dim = int(raw_col) if not fuzzy_col else 1
            if col_dim <= 0:
                col_dim = 1
                fuzzy_col = True
        except Exception:
            col_dim = 1

        if "模糊行数" not in trigger_raw and "fuzzy_row" not in trigger_raw:
            report.add_change(f"补充最新架构字段 '模糊行数' (当前值: {fuzzy_row})")
        if "模糊列数" not in trigger_raw and "fuzzy_col" not in trigger_raw:
            report.add_change(f"补充最新架构字段 '模糊列数' (当前值: {fuzzy_col})")

        # Extra conditions migration
        raw_extras = (
            trigger_raw.get("额外条件列表")
            or trigger_raw.get("extra_conditions")
            or trigger_raw.get("额外条件")
            or trigger_raw.get("extra_condition")
            or trigger_raw.get("conditions")
            or None
        )

        cond_list: List[Dict[str, Any]] = []
        if isinstance(raw_extras, list):
            for idx, cond_item in enumerate(raw_extras):
                if isinstance(cond_item, dict):
                    migrated_cond = self._migrate_condition_dict(cond_item, target_zh, report, idx + 1)
                    if migrated_cond:
                        cond_list.append(migrated_cond)
        elif isinstance(raw_extras, dict):
            migrated_cond = self._migrate_condition_dict(raw_extras, target_zh, report, 1)
            if migrated_cond:
                cond_list.append(migrated_cond)
            report.add_change("将旧版单一额外条件升级为最新 '额外条件列表' 数组格式")

        if target_zh:
            res: Dict[str, Any] = {
                "表格大小": [row_dim, col_dim],
                "模糊行数": fuzzy_row,
                "模糊列数": fuzzy_col,
            }
            if cond_list:
                res["额外条件列表"] = cond_list
                # Maintain backward compatibility single condition
                res["额外条件"] = cond_list[0]
            return res
        else:
            res = {
                "table_size": [row_dim, col_dim],
                "fuzzy_row": fuzzy_row,
                "fuzzy_col": fuzzy_col,
            }
            if cond_list:
                res["extra_conditions"] = cond_list
                res["extra_condition"] = cond_list[0]
            return res

    def _migrate_condition_dict(
        self, cond: Dict[str, Any], target_zh: bool, report: ConfigMigrationReport, idx: int
    ) -> Optional[Dict[str, Any]]:
        # Coordinate extraction
        pos = cond.get("位置") or cond.get("position")
        row, col = 0, 0
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            row, col = int(pos[0]), int(pos[1])
        else:
            row = int(cond.get("行") or cond.get("row") or 0)
            col = int(cond.get("列") or cond.get("col") or 0)

        regex = str(cond.get("正则表达式") or cond.get("regex") or "").strip()
        if not regex:
            report.add_warning(f"第 {idx} 个额外条件的正则表达式为空，已忽略该条件")
            return None

        # Validate regex syntax
        try:
            re.compile(regex)
        except re.error as e:
            report.add_error(f"第 {idx} 个额外条件的正则表达式 '{regex}' 语法无效: {e}")
            return None

        if target_zh:
            return {"位置": [row, col], "正则表达式": regex}
        else:
            return {"position": [row, col], "regex": regex}

    def _migrate_workflow(
        self, workflow_raw: List[Any], target_zh: bool, report: ConfigMigrationReport
    ) -> List[Dict[str, Any]]:
        upgraded_steps: List[Dict[str, Any]] = []

        for i, step in enumerate(workflow_raw):
            step_num = i + 1
            if not isinstance(step, dict):
                report.add_error(f"第 {step_num} 步格式无效 (非字典对象): {step}")
                continue

            raw_action = step.get("动作") or step.get("action") or ""
            canon_zh = ACTION_NAME_MAP.get(raw_action)
            if not canon_zh:
                report.add_error(f"第 {step_num} 步未知的动作类型: '{raw_action}'")
                upgraded_steps.append(step)
                continue

            act_key = "动作" if target_zh else "action"
            act_val = canon_zh if target_zh else CANONICAL_ZH_TO_EN_ACTION[canon_zh]

            migrated_step = self._migrate_single_action(
                canon_zh, step, target_zh, act_key, act_val, report, step_num, len(workflow_raw)
            )
            upgraded_steps.append(migrated_step)

        return upgraded_steps

    def _migrate_single_action(
        self,
        canon_zh: str,
        step: Dict[str, Any],
        target_zh: bool,
        act_key: str,
        act_val: str,
        report: ConfigMigrationReport,
        step_num: int,
        total_steps: int,
    ) -> Dict[str, Any]:
        res: Dict[str, Any] = {act_key: act_val}

        if canon_zh == "提取某一格":
            # Coordinate handling (supports int or dynamic string expression/variable)
            pos = step.get("操作位置") or step.get("position")
            r_val, c_val = None, None
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                r_val, c_val = pos[0], pos[1]
            if r_val is None:
                r_val = step.get("行") if "行" in step else step.get("row", 0)
            if c_val is None:
                c_val = step.get("列") if "列" in step else step.get("col", 0)

            # Target variable name
            var_name = str(
                step.get("暂存到的变量名")
                or step.get("variable")
                or step.get("变量名")
                or f"extracted_val_{step_num}"
            ).strip()

            if not IDENTIFIER_REGEX.match(var_name):
                sanitized = sanitize_identifier(var_name, f"extracted_val_{step_num}")
                report.add_change(f"第 {step_num} 步变量名 '{var_name}' 包含非法字符，已规范化为合法标识符: '{sanitized}'")
                var_name = sanitized

            if target_zh:
                res["行"] = r_val
                res["列"] = c_val
                res["暂存到的变量名"] = var_name
                # Keep 操作位置 for maximum compatibility if both are integers
                if isinstance(r_val, int) and isinstance(c_val, int):
                    res["操作位置"] = [r_val, c_val]
            else:
                res["row"] = r_val
                res["col"] = c_val
                res["variable"] = var_name
                if isinstance(r_val, int) and isinstance(c_val, int):
                    res["position"] = [r_val, c_val]

        elif canon_zh == "如果":
            cond = str(
                step.get("条件") or step.get("condition") or step.get("cond") or "1"
            ).strip()

            # Handle legacy 'has_else' / '是否有else' / '包含else'
            has_else_legacy = (
                step.get("是否有else")
                if "是否有else" in step
                else (step.get("has_else") if "has_else" in step else step.get("包含else"))
            )

            # Handle count fields
            then_count = step.get("then_count")
            if then_count is None:
                then_count = step.get("if下面有多少个积木", 1)
            try:
                then_count = max(0, int(then_count))
            except Exception:
                then_count = 1

            else_count = step.get("else_count")
            if else_count is None:
                else_count = step.get("else下面有多少个积木")

            if else_count is None:
                if has_else_legacy is True:
                    else_count = 1
                    report.add_change(f"第 {step_num} 步旧版配置 '是否有else: true' 已自动升级为最新架构 'else_count: 1'")
                else:
                    else_count = 0
            else:
                try:
                    else_count = max(0, int(else_count))
                except Exception:
                    else_count = 0

            if has_else_legacy is not None:
                report.add_change(f"第 {step_num} 步清理旧版废弃字段 '是否有else' / 'has_else'")

            if target_zh:
                res["条件"] = cond
                res["then_count"] = then_count
                res["else_count"] = else_count
            else:
                res["condition"] = cond
                res["then_count"] = then_count
                res["else_count"] = else_count

        elif canon_zh == "跳转":
            cond = str(step.get("条件") or step.get("condition") or "1").strip()
            target_line = step.get("目标行号") if "目标行号" in step else step.get("target_line", 1)
            try:
                target_line = max(1, int(target_line))
            except Exception:
                target_line = 1

            if target_line > total_steps:
                report.add_warning(
                    f"第 {step_num} 步跳转目标行 {target_line} 超出总步数 {total_steps}，执行时将直接结束流程"
                )

            if target_zh:
                res["条件"] = cond
                res["目标行号"] = target_line
            else:
                res["condition"] = cond
                res["target_line"] = target_line

        elif canon_zh == "计算":
            target_var = str(
                step.get("左值")
                or step.get("target_var")
                or step.get("variable")
                or f"calc_var_{step_num}"
            ).strip()

            if not IDENTIFIER_REGEX.match(target_var):
                sanitized = sanitize_identifier(target_var, f"calc_var_{step_num}")
                report.add_change(f"第 {step_num} 步计算目标变量 '{target_var}' 已规范化为: '{sanitized}'")
                target_var = sanitized

            expr = str(step.get("右值") or step.get("expression") or step.get("expr") or "0").strip()

            if target_zh:
                res["左值"] = target_var
                res["右值"] = expr
            else:
                res["target_var"] = target_var
                res["expression"] = expr

        elif canon_zh == "弹出冒泡窗":
            content = str(step.get("内容") or step.get("content") or "").strip()
            duration = step.get("持续时间") if "持续时间" in step else step.get("duration", 2000)
            try:
                duration = int(duration)
            except Exception:
                duration = 2000

            blocking = step.get("是否阻塞") if "是否阻塞" in step else step.get("blocking", False)
            screen = str(step.get("显示的屏幕") or step.get("screen") or "鼠标所在屏幕").strip()
            position = str(step.get("显示的位置") or step.get("position") or "底部居中").strip()

            if target_zh:
                res["内容"] = content
                res["持续时间"] = duration
                res["是否阻塞"] = bool(blocking)
                res["显示的屏幕"] = screen
                res["显示的位置"] = position
            else:
                res["content"] = content
                res["duration"] = duration
                res["blocking"] = bool(blocking)
                res["screen"] = screen
                res["position"] = position

        elif canon_zh == "弹出提示框":
            title = str(step.get("标题") or step.get("title") or "提示").strip()
            content = str(step.get("内容") or step.get("content") or "").strip()
            if target_zh:
                res["标题"] = title
                res["内容"] = content
            else:
                res["title"] = title
                res["content"] = content

        elif canon_zh == "用户输入":
            prompt = str(step.get("提示文本") or step.get("prompt") or "请输入").strip()
            var_name = str(step.get("变量名") or step.get("variable") or f"input_{step_num}").strip()
            if not IDENTIFIER_REGEX.match(var_name):
                sanitized = sanitize_identifier(var_name, f"input_{step_num}")
                report.add_change(f"第 {step_num} 步输入变量名 '{var_name}' 已规范化为: '{sanitized}'")
                var_name = sanitized
            default_val = str(step.get("默认值") if "默认值" in step else step.get("default", ""))

            if target_zh:
                res["提示文本"] = prompt
                res["变量名"] = var_name
                res["默认值"] = default_val
            else:
                res["prompt"] = prompt
                res["variable"] = var_name
                res["default"] = default_val

        elif canon_zh == "写入剪切板":
            clip_type = str(step.get("type") or step.get("类型") or "text").lower()
            if clip_type not in ("text", "table"):
                clip_type = "text"
            data = str(step.get("data") or step.get("数据") or step.get("content") or step.get("内容") or "")

            if target_zh:
                res["type"] = clip_type
                res["data"] = data
            else:
                res["type"] = clip_type
                res["data"] = data

        elif canon_zh == "发网络请求":
            method = str(step.get("方法") or step.get("method") or "GET").upper()
            url = str(step.get("url") or step.get("URL") or "").strip()
            headers = step.get("header") or step.get("headers") or {}
            body = step.get("body") or step.get("请求体")
            timeout = step.get("timeout") if "timeout" in step else step.get("超时时间", 10000)
            try:
                timeout = int(timeout)
            except Exception:
                timeout = 10000
            callback = step.get("callback") or step.get("回调变量映射") or {}

            if target_zh:
                res["方法"] = method
                res["url"] = url
                res["header"] = headers
                if body is not None:
                    res["body"] = body
                res["timeout"] = timeout
                res["callback"] = callback
            else:
                res["method"] = method
                res["url"] = url
                res["header"] = headers
                if body is not None:
                    res["body"] = body
                res["timeout"] = timeout
                res["callback"] = callback

        elif canon_zh == "退出":
            # Exit action needs no additional parameters
            pass

        return res


def migrate_file(
    file_path: str,
    migrator: ConfigMigrator,
    check_only: bool = False,
    backup: bool = False,
    verbose: bool = False,
) -> ConfigMigrationReport:
    """Migrate a single JSON configuration file."""
    report = ConfigMigrationReport(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            original_text = f.read()
            raw_data = json.loads(original_text)
    except Exception as e:
        report.add_error(f"无法读取或解析 JSON 文件: {e}")
        return report

    if not isinstance(raw_data, dict):
        report.add_error("根节点不是 JSON 对象字典")
        return report

    migrated_data = migrator.migrate(raw_data, report)

    # Format migrated JSON with clean indentation and UTF-8
    new_text = json.dumps(migrated_data, ensure_ascii=False, indent=2) + "\n"

    # Check if text actually changed
    if original_text.strip() != new_text.strip():
        report.modified = True

    if not report.is_ok:
        return report

    if report.modified and not check_only:
        if backup:
            bak_path = f"{file_path}.bak"
            shutil.copy2(file_path, bak_path)
            report.add_change(f"已创建备份文件: {bak_path}")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Excel Checker - Standalone Configuration Migration & Verification Tool"
    )
    parser.add_argument(
        "--dir",
        default="configs",
        help="Directory containing config files to inspect and upgrade (default: configs)",
    )
    parser.add_argument(
        "--file",
        help="Path to a single config file to inspect and upgrade",
    )
    parser.add_argument(
        "--check-only",
        "--dry-run",
        action="store_true",
        help="Inspect configs and check compatibility without modifying files",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create .bak backups before updating files",
    )
    parser.add_argument(
        "--lang",
        choices=["keep", "chinese", "english"],
        default="keep",
        help="Key language standardization: 'keep' (default), 'chinese', or 'english'",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed migration changes and logs",
    )

    args = parser.parse_args()
    files: List[str] = []

    if args.file:
        if not os.path.exists(args.file):
            print(f"❌ 错误: 指定的文件不存在: {args.file}", file=sys.stderr)
            return 1
        files.append(args.file)
    else:
        pattern = os.path.join(args.dir, "*.json")
        files = sorted(glob.glob(pattern))
        if not files:
            print(f"⚠️ 提示: 在目录 '{args.dir}' 下未找到任何 .json 配置文件。")
            return 0

    print("=" * 70)
    mode_desc = "【预检模式 (Check-Only / Dry-Run)】" if args.check_only else "【迁移模式 (Live Upgrade)】"
    print(f"🚀 Excel Checker 配置架构验证与升级迁移工具 {mode_desc}")
    print(f"📁 目标文件数: {len(files)} | 语言键策略: {args.lang} | 备份: {args.backup}")
    print("=" * 70)

    migrator = ConfigMigrator(lang=args.lang)
    total_modified = 0
    total_errors = 0
    total_warnings = 0

    for file_path in files:
        report = migrate_file(
            file_path,
            migrator=migrator,
            check_only=args.check_only,
            backup=args.backup,
            verbose=args.verbose,
        )

        status_icon = "❌" if not report.is_ok else ("🔄" if report.modified else "✅")
        status_text = "失败" if not report.is_ok else ("已升级并保存" if (report.modified and not args.check_only) else ("检测到可升级项" if report.modified else "已是最新架构规范"))

        print(f"\n{status_icon} [{status_text}] {os.path.basename(file_path)}")

        if report.changes:
            for ch in report.changes:
                print(f"   • [更新] {ch}")

        if report.warnings:
            total_warnings += len(report.warnings)
            for w in report.warnings:
                print(f"   ⚠️ [警告] {w}")

        if report.errors:
            total_errors += len(report.errors)
            for err in report.errors:
                print(f"   ❌ [错误] {err}")

        if report.modified:
            total_modified += 1

    print("\n" + "=" * 70)
    print(f"📊 汇总结果: 检查 {len(files)} 个文件 | 升级 {total_modified} 个 | 警告 {total_warnings} 个 | 错误 {total_errors} 个")
    if total_errors > 0:
        print("❌ 部分配置存在语法或结构错误，请检查上述错误信息。")
        return 1
    elif total_modified > 0 and args.check_only:
        print("💡 提示: 运行 `python3 migrate_configs.py` 即可自动完成升级写入。")
        return 0
    else:
        print("🎉 所有配置文件均已验证并符合最新的框架与字段定义！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
