"""程序入口。

默认启动图形界面；--nogui 为头less 运行（用于功能自检）。
"""

from __future__ import annotations

import argparse
import sys

from .controller import AppController


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
        help="不启动图形界面，仅启动剪贴板监控与规则执行（用于自检）",
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

    # 图形界面主窗口
    from .gui.main_window import MainWindow

    window = MainWindow(controller)
    window.show()
    if args.config:
        window.statusBar().showMessage(f"已加载 {len(controller.config_paths())} 条配置")
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
