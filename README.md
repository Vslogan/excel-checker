# excel-checker

表格数据检查辅助桌面工具（Python 3.13 / PyQt5）。

## 能做什么

把“收到剪贴板里的 Excel 表格 → 校验大小/内容 → 按自定义规则处理”变成可配置、可视化、可热更新的流程：

1. 打开工具，读入或新建一条 JSON 配置规则
2. 在内置可视化编辑器里编辑规则（类低代码积木：触发前提 + 有序动作步骤）
3. 启动规则，工具后台轮询剪贴板
4. 收到表格时，先比表格大小，再比额外条件（如 `(0,0)` 格是否匹配正则 `[0-9]{3,}`）；全部满足后按顺序执行动作，网络请求同步等待，超时报错

普通纯文本会被兼容性地视为 `1x1` 表格，由后续条件判断是否真正匹配。

## 支持的动作（可持续扩展）

- `extract_cell`：提取某一格，暂存到变量
- `http_request`：发网络请求（GET/POST/…），URL/Header/Body 支持 `{{变量}}`；可选 `callback` 从返回 JSON 按路径（如 `res.data[0]`）提取变量
- `user_input`：弹出输入框，结果暂存到变量
- `alert`：弹出提示框，内容支持 `{{变量}}`
- `write_clipboard`：`text` 写纯文本；`table` 把二维数据按 CSV 格式写入剪贴板

后续可在 `engine.py` 增加 `_do_<动作名>` 并向 `config.KNOWN_ACTIONS` 注册名字，即可插入新动作（如文件读写）；条件/循环等结构也可在此框架下优化处理逻辑。

## 环境要求

- 目标运行环境：**Python 3.13**
- 代码对 **Python 3.11+** 向前兼容（本开发沙箱仅预装 3.11 且缺少 OpenSSL/FFI/Zlib 构建头文件，无法在此编译 3.13；所有代码已在 3.11 上自检通过，可直接在 3.13 运行）
- GUI 基于 PyQt5，需要桌面环境与 OpenGL 支持（本头less 沙箱缺 `libGL.so.1`，GUI 无法在此直接启动，可在普通 Windows/macOS/Linux 桌面运行）

依赖：`PyQt5>=5.15.9`、`requests>=2.31.0`

## 快速开始

不需要 `pip install -e .`，直接运行根目录下的独立入口即可启动所有服务：

```bash
# 创建虚拟环境（建议用 Python 3.13）
python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install PyQt5 requests

# 启动图形界面（主窗口：新建/打开/编辑配置、启动剪贴板监控）
python main.py

# 指定配置文件启动
python main.py --config configs/sample.json

# 头less 模式运行（仅后台监控剪贴板，适合服务/自检）
python main.py --config configs/sample.json --nogui
```

## 项目结构

```
excel_checker/
  config.py       规则配置模型：JSON 加载/校验，{{var}} 模板替换
  engine.py       可插拔动作执行引擎（extract_cell/http_request/user_input/alert/write_clipboard）
  clipboard.py    剪贴板监控与表格解析（CSV/纯文本/制表符，纯文本视为 1x1）
  controller.py   配置加载/热更新、剪贴板匹配与执行调度
  gui/
    main_window.py   主窗口：配置列表、监控开关、执行日志
    config_editor.py 可视化规则编辑器（积木卡片式）
  main.py         包内入口（供 import 使用）
main.py           项目独立启动入口（直接运行启动所有服务，无需 -e 安装）
configs/
  sample.json     示例配置
scripts/
  self_test.py                   配置/引擎/剪贴板解析单元自检
  test_controller_pipeline.py    控制器端到端管道自检
```

## 配置示例（configs/sample.json）

```json
{
  "name": "示例配置",
  "trigger": {
    "size": {"rows": 2, "cols": 2},
    "conditions": [{"cell": [0, 0], "pattern": "[0-9]{3,}"}]
  },
  "steps": [
    {"action": "extract_cell", "cell": [0, 0], "variable": "id"},
    {"action": "http_request", "method": "POST", "url": "http://example.com/{{id}}",
     "headers": {"X-Id": "{{id}}"}, "body": {"id": "{{id}}"}, "timeout": 10000,
     "callback": {"newData": "res.data[0]"}},
    {"action": "user_input", "prompt": "请输入要提取第几个", "variable": "index"},
    {"action": "alert", "content": "新内容为{{newData}}，索引: {{index}}"},
    {"action": "write_clipboard", "type": "table",
     "data": [["id", "newData", "index"], ["{{id}}", "{{newData}}", "{{index}}"]]}
  ]
}
```

## 自检

```bash
python scripts/self_test.py
python scripts/test_controller_pipeline.py
```

分批次开发中：本阶段完成了配置模型、引擎、剪贴板解析、控制器管道及全部 PyQt5 图形界面的搭建；后续可继续完善更多动作、条件/循环结构等。
