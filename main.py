#!/usr/bin/env python3
"""Direct source-tree launcher; no editable/package installation is required."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"


def main() -> int:
    # Make the checkout importable when launched as `python main.py`.
    source_path = str(SOURCE_ROOT)
    if source_path not in sys.path:
        sys.path.insert(0, source_path)
    arguments = sys.argv[1:]
    if arguments:
        if arguments[0] == "gui":
            os.chdir(PROJECT_ROOT)
        try:
            from excel_checker.cli import main as start_cli
        except ImportError as exc:
            print(f"无法加载 Excel Checker 服务：{exc}", file=sys.stderr)
            return 2
        return start_cli(arguments)

    os.chdir(PROJECT_ROOT)
    try:
        from excel_checker.qt_app import main as start_desktop_app
    except ImportError as exc:
        print(
            "无法加载桌面依赖。请先在当前 Python 环境执行 "
            f"`python -m pip install -r {PROJECT_ROOT / 'requirements.txt'}`。\n"
            f"详细信息：{exc}",
            file=sys.stderr,
        )
        return 2

    # Pass only the app name to Qt; command-line arguments are not interpreted
    # by the desktop application.
    return start_desktop_app([str(PROJECT_ROOT / "main.py")])


if __name__ == "__main__":
    raise SystemExit(main())
