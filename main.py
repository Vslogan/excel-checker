#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""excel-checker 独立启动入口。

无需 `pip install -e .`，直接运行即可启动所有服务（GUI + 剪贴板监控）：

    python main.py
    python main.py --config configs/sample.json
    python main.py --config configs/sample.json --nogui

把项目根目录加入 sys.path，确保在任何工作目录下直接运行都能找到
excel_checker 包。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 将本文件所在目录（项目根）加入 sys.path，避免依赖 editable 安装
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from excel_checker.controller import AppController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="excel-checker",
        description="表格数据检查辅助工具：监控剪贴板中的 Excel 表格，按 JSON 规则自动处理",
    )
    parser.add_argument(
        "--config",
        action="append",
        metavar="PATH",
        help="规则 JSON 文件路径，可重复指定多个",
    )
    parser.add_argument(
        "--nogui",
        action="store_true",
        help="不启动图形界面，仅启动剪贴板监控与规则执行（用于自检/后台服务）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from PyQt5.QtWidgets import QApplication  # 剪贴板访问需要 Qt 应用

    app = QApplication(sys.argv)
    app.setApplicationName("excel-checker")

    controller = AppController()
    if args.config:
        for path in args.config:
            try:
                controller.load_config(path)
            except Exception as exc:  # 配置加载失败不应直接崩溃
                print(f"[错误] 加载配置 {path} 失败: {exc}", file=sys.stderr)
                return 1

    if args.nogui:
        print("[excel-checker] 头less 模式运行，监控剪贴板中... (Ctrl+C 退出)")
        controller.start()
        try:
            return app.exec_()
        except KeyboardInterrupt:
            controller.stop()
            print("\n[excel-checker] 已退出")
            return 0

    # 图形界面主窗口：启动所有服务（配置管理、剪贴板监控、规则执行）
    from excel_checker.gui.main_window import MainWindow

    window = MainWindow(controller)
    window.show()
    if args.config:
        window.statusBar().showMessage(f"已加载 {len(controller.config_paths())} 条配置")
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
