"""Application entry point for Excel Checker."""
from __future__ import annotations

import argparse
import os
import sys

# Ensure local packages are on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_gui():
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QFontDatabase
    from PyQt5.QtWidgets import QApplication
    from src.gui.main_window import MainWindow

    # Enable High DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("表格数据检查辅助 (Excel Checker)")

    # Load Chinese font if available
    font_path = os.path.join(os.path.dirname(__file__), "assets", "fonts", "wqy-microhei.ttc")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id >= 0:
            app.setFont(QFont("WenQuanYi Micro Hei", 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


def run_simulation_cli(input_text: str, config_path: str):
    from src.core.config_model import RuleConfig
    from src.core.context import HeadlessUIDelegate
    from src.core.engine import WorkflowEngine
    from src.core.table_parser import TableData

    print(f"=== Excel Checker 模拟运行模式 ===")
    print(f"加载规则文件: {config_path}")
    rule = RuleConfig.load_from_file(config_path)
    print(f"规则名称: {rule.name}")
    print(f"期望表格尺寸: {rule.table_size[0]}x{rule.table_size[1]}")

    table = TableData.from_text(input_text)
    print(f"输入文本: {repr(input_text)}")
    print(f"解析尺寸: {table.rows}x{table.cols}")

    if not rule.matches(table):
        print(f"❌ 触发条件不满足，跳过执行。")
        return

    print(f"✅ 触发条件满足，开始执行流程...")
    engine = WorkflowEngine()
    delegate = HeadlessUIDelegate(predefined_inputs={"请输入要提取第几个索引 (例如: 1)": "1"})

    res = engine.execute_rule(rule, table, ui_delegate=delegate)
    print(f"\n执行结果: {'成功' if res.success else '失败'}")
    if res.error:
        print(f"错误信息: {res.error}")
    print("\n--- 变量列表 ---")
    for k, v in res.variables.items():
        if not k.startswith("_"):
            print(f"  {k} = {v}")
    print("\n--- 写入剪切板的内容 ---")
    print(delegate.get_clipboard())


def main():
    parser = argparse.ArgumentParser(description="表格数据检查辅助 (Excel Checker)")
    parser.add_argument("--simulate", type=str, help="CLI模式: 模拟运行剪切板文本")
    parser.add_argument("--config", type=str, default="configs/示例配置1.json", help="指定的配置文件路径")
    args = parser.parse_args()

    if args.simulate:
        run_simulation_cli(args.simulate, args.config)
    else:
        run_gui()


if __name__ == "__main__":
    main()
