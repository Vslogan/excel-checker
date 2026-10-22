# Excel Checker（PyQt5 桌面版）

一个面向 Excel / WPS / 表格网页复制内容的规则处理工具。规则引擎通过第一阶段验收后，本阶段补上了 PyQt5 桌面配置器和剪切板监控控制界面。

## 当前能力

- PyQt5 桌面界面支持新建/导入/删除规则、切换规则目录、配置触发条件、按顺序增删编辑动作积木，并启用/停用规则。
- 在界面中开启监控后，Qt 定时读取系统剪切板；匹配的动作按顺序在后台串行执行，HTTP 等待不会冻结窗口，用户输入/提示框/剪切板写入通过 GUI 主线程处理。
- 对复制内容按行、列解析；Excel 常见的 TSV/CRLF 可直接处理。普通文本按 **1×1 表格**处理。
- 规则可要求精确行列数，并可附加单元格正则条件（正则对整个单元格做匹配）。
- 顺序执行提取单元格、同步 HTTP 请求、用户输入、提示、剪切板写入。
- `{{变量名}}` 可用于 URL、Header、Body、提示内容和剪切板内容。HTTP JSON 响应可通过 `res.data[0]` 这样的安全路径表达式提取；不使用 `eval`。
- 规则目录热加载：新增、修改、删除 JSON 文件后，下次剪切板轮询自动生效。编辑中的 JSON 暂时无效时，继续保留该文件上一次有效规则，并报告错误。
- 动作通过注册表动态扩展；每个动作可同时声明执行处理器、配置校验器和表单元数据，为后续积木式编辑器、条件/循环及文件读写动作预留接口。

## 环境

项目目标版本为 **Python 3.13+**，核心引擎不依赖第三方运行库。当前开发容器提供的是 Python 3.11.2，核心测试和 PyQt5 5.15.11 的离屏界面/剪切板工作流测试均已运行通过；但这里没有 Python 3.13 解释器和完整桌面环境，因此尚未做 Python 3.13 桌面系统的端到端验证。

```bash
# Python 3.13 环境
python -m pip install -e '.[desktop]'
excel-checker gui
```

桌面版依赖 PyQt5，并通过 Qt 自带的剪切板接口读写数据。CLI 的 `watch` 命令另需安装 `system-clipboard` 额外依赖；某些 Linux 桌面还需要系统提供 `xclip`、`xsel` 或 Wayland 剪切板工具。也可一次安装两种可选依赖：`python -m pip install -e '.[desktop,system-clipboard]'`。

## 桌面界面

```bash
excel-checker gui
# 或直接启动桌面入口
excel-checker-gui
```

默认规则目录是当前工作目录下的 `rules/`，也可在界面顶部切换。左侧可新建、导入 JSON、删除和启停规则；右侧配置表格尺寸、正则条件，以及按顺序排列的动作积木（添加/编辑/删除/上移/下移）；点击“保存规则”后写入 JSON。勾选“监控剪切板”开始监听，已有剪切板内容仅设为基线，不会刚启动就误触发。

## CLI 验收

```bash
# 校验 JSON 配置、动作参数和正则
excel-checker validate examples/id_lookup.json

# 离线演示：输入 12345，通知并预览将写入剪切板的表格
excel-checker run examples/offline_demo.json --text '12345'

# 网络动作示例会真实请求配置中的 URL；user_input 在终端读取
excel-checker run examples/id_lookup.json --text '12345'

# 监控一个规则目录；启动时现有剪切板仅作为基线，不会误触发
excel-checker watch ./rules
```

也可以在源码目录直接执行：

```bash
PYTHONPATH=src python -m excel_checker validate examples/id_lookup.json
```

## JSON 规则格式（version 1）

```json
{
  "version": 1,
  "name": "示例配置",
  "enabled": true,
  "priority": 0,
  "trigger": {
    "table_size": {"rows": 1, "columns": 1},
    "conditions": [
      {"cell": [0, 0], "regex": "^[0-9]{3,}$"}
    ]
  },
  "actions": [
    {"action": "extract_cell", "cell": [0, 0], "variable": "id"},
    {
      "action": "http_request",
      "method": "POST",
      "url": "https://example.com/{{id}}",
      "headers": {"X-ID": "{{id}}"},
      "body": {"id": "{{id}}"},
      "timeout_ms": 10000,
      "callback": {"newData": "res.data[0]"}
    },
    {"action": "user_input", "prompt": "请输入序号", "variable": "index"},
    {"action": "notify", "message": "新内容为 {{newData}}"},
    {"action": "clipboard_write", "type": "table", "data": [["{{id}}", "{{newData}}"]]}
  ]
}
```

- 行列坐标从 0 开始；`table_size` 必填且严格匹配。额外条件可省略，多个条件需全部满足。
- `regex` 使用 Python 正则并对整个单元格匹配；若要查找子串，请自行使用 `.*` 包围。
- 若多个启用规则同时匹配，只执行 `priority` 较高的一条；同优先级按配置名、文件路径稳定排序，避免重复发请求。
- HTTP 请求同步等待响应；`timeout_ms` 单位为毫秒。非成功 HTTP 状态、超时或回调路径不存在都会停止后续步骤并报告错误。
- 回调表达式支持对象字段和数组序号，例如 `res.data[0]`、`res['data'][0]`；`response` 保存完整 HTTP JSON 响应，路径根 `res` 默认指向响应本身，若响应最外层有 `res` 字段则自动指向该字段内容。
- `clipboard_write` 的 `table` 可传二维数组，也可传 CSV（逗号）或 TSV 文本；会写为制表符分隔格式，便于粘贴回电子表格。
- `enabled: false` 的规则不会触发。`priority` 默认为 0。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试覆盖规则校验与匹配、动作顺序、HTTP 超时/失败中断、热加载和剪切板解析。安装 `.[desktop]` 后还会运行 Qt 表单、规则启停及后台执行/剪切板写入测试；没有可加载的 PyQt5/Qt 运行库时，这 4 项会被跳过。后续可在现有动作注册接口上继续增加文件读写、条件和循环积木。
