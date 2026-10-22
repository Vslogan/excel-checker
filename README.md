# 表格数据检查辅助 (Excel Table Checker)

基于 **Python 3.13** 与 **PyQt5** 开发的现代化桌面端自动化表格处理与数据核对辅助工具。

通过后台持续监听系统剪切板，自动捕获从 Excel / WPS / 网页中复制的表格数据，根据用户在低代码积木编辑器中配置的规则（尺寸前提、正则约束、网络请求、用户输入等），流水线式自动化执行后续数据处理，并将生成的新表格或文本以 Excel 原生格式自动写回剪切板。

---

## 核心功能与亮点

- **低代码积木式可视化编辑器 (Low-Code Block Programming)**：
  - 无需手写代码，拖拉拽式添加并排序各种处理动作。
  - 支持积木自由**上移 (▲)**、**下移 (▼)**、**一键复制 (克隆)** 与**删除**。
- **双向数据同步**：
  - 支持「低代码积木视图」与「JSON 源码视图」毫秒级双向同步。
  - 完美兼容**中文自然语义键名**（如 `"配置名称"`、`"触发该配置的前提"`、`"发网络请求"`）与**英文标准键名**。
- **后台持续化剪切板智能监控**：
  - 精准识别 Excel 原生表格格式（TSV），自动解析行列维度。
  - **1x1 表格完美兼容**：针对部分软件将 1x1 复制为纯文本的情况，工具自动将纯文本兼容视为 1x1 表格。
  - 内置防循环回环保护：程序写入剪切板的内容不会再次被触发。
- **前置触发过滤**：
  - **表格大小校验（必填）**：精确匹配 行数 × 列数。
  - **额外格式条件（可选）**：指定 `(行, 列)` 单元格正则匹配（如 `[0-9]{3,}`），并提供可视化**实时正则测试器**。
- **丰富的动作积木库 (持续动态扩展)**：
  1. `🧩 提取单元格 (extract_cell)`：提取指定位置单元格内容，存储到上下文变量。
  2. `🌐 发网络请求 (http_request)`：支持 GET/POST/PUT/DELETE，支持在 URL/Header/Body 模板化插入 `{{变量}}`，支持毫秒级超时控制，支持同步等待响应并根据 JSONPath 回调提取字段（如 `res.data[0]`）。
  3. `💬 用户输入 (user_input)`：弹出模态输入弹窗，由用户补充指定变量。
  4. `🔔 弹出提示框 (show_message)`：弹出提示窗口展示处理结果（支持 `{{变量}}` 插值）。
  5. `📋 写入剪切板 (write_clipboard)`：支持 `text`（纯文本）与 `table`（表格模式，将 CSV 自动转换为 Excel 原生 TSV 表格写入，粘贴时直接分行分列）。
  6. `📁 文件读写 (file_ops)`：扩展动作，支持本地文件读取、写入与追加。
  7. `🔀 条件判断 (condition)`：扩展动作，支持根据变量值进行分支条件执行。
- **内置表格模拟测试器 (Clipboard Simulator)**：
  - 无需频繁切换外部 Excel 即可在工具内输入样例数据进行端到端全流程仿真。
  - 运行时变量检查器 (Variables Inspector) 实时展示每个变量的状态与最终剪切板产物。
- **配置热更新 / 热插拔**：
  - 监控 `configs/` 目录的修改与新增，自动检测文件变动并热重载，无需重启软件。

---

## 整体工作流程

```mermaid
flowchart TD
    A[用户在 Excel/软件中按下 Ctrl+C 复制] --> B[后台剪切板监控拦截数据]
    B --> C{检查表格尺寸是否与当前规则匹配?}
    C -- 否 (或普通文本非1x1) --> D[跳过此次复制]
    C -- 是 --> E{是否配置额外条件?}
    E -- 否 --> G[触发条件全部满足]
    E -- 是 --> F{指定单元格是否符合正则表达式?}
    F -- 否 --> D
    F -- 是 --> G
    G --> H[按照积木顺序逐步执行流水线动作]
    H --> I[提取单元格内容至 {{id}}]
    I --> J[发送 HTTP 网络请求 (同步等待返回)]
    J -- 超时或失败 --> K[终止流水线并弹窗报错]
    J -- 成功 --> L[按回调表达式提取返回字段至 {{newData}}]
    L --> M[弹出输入框获取用户输入 {{index}}]
    M --> N[弹出提示框告知用户结果]
    N --> O[将重组数据以表格格式写入剪切板]
    O --> P[用户可在 Excel 中直接 Ctrl+V 粘贴新表格]
```

---

## 项目结构

```
excel-checker/
├── configs/                          # 规则配置存储目录 (支持热加载)
│   ├── 示例配置1.json                 # 题目要求的完整示例配置
│   ├── github_user_lookup.json       # GitHub 线上用户查询真实可测配置
│   └── order_processing.json         # 2x3 订单批量处理示例
├── src/
│   ├── core/                         # 核心执行引擎与数据层 (完全解耦)
│   │   ├── actions/                  # 动态动作库 (开放式注册架构)
│   │   │   ├── base.py               # BaseAction 抽象基类与 ActionRegistry 注册表
│   │   │   ├── extract_cell.py       # 提取单元格动作
│   │   │   ├── http_request.py       # HTTP 网络请求与回调 JSONPath 提取
│   │   │   ├── user_input.py         # 用户输入对话框动作
│   │   │   ├── show_message.py       # 消息提示弹窗动作
│   │   │   ├── write_clipboard.py    # 剪切板写入 (表格 TSV / 文本)
│   │   │   ├── file_ops.py           # 文件读写扩展动作
│   │   │   └── condition.py          # 条件分支扩展动作
│   │   ├── table_parser.py           # 剪切板 TSV / CSV / 纯文本解析器
│   │   ├── context.py                # 运行时变量管理、{{var}} 模板渲染、安全 JSONPath
│   │   ├── config_model.py           # 规则模型定义、双语字段序列化与完整性校验
│   │   ├── engine.py                 # 流程调度引擎、热加载检测与步骤分发
│   │   └── monitor.py                # 剪切板持续监控调度与防循环机制
│   └── gui/                          # PyQt5 图形界面层
│       ├── main_window.py            # 主程序窗口、工具栏、实时日志与监控开关
│       ├── block_editor.py           # 低代码积木编辑器容器与触发前提设置
│       ├── action_cards.py           # 各种动作积木卡片控件 (上移/下移/克隆/删除)
│       ├── json_editor_widget.py     # JSON 源码实时双向同步编辑器
│       ├── simulator_widget.py       # 表格模拟测试器与变量检查器
│       ├── qt_delegate.py            # Qt 原生对话框与剪切板桥接代理
│       └── style.py                  # 现代化扁平视觉主题与 QSS 样式表
├── tests/                            # 自动化测试套件 (覆盖率 100%)
│   ├── test_table_parser.py
│   ├── test_context.py
│   ├── test_config_model.py
│   ├── test_actions.py
│   ├── test_engine.py
│   ├── test_edge_cases.py
│   └── test_gui.py
├── main.py                           # 启动入口 (支持 GUI 模式与 CLI 仿真模式)
├── requirements.txt                  # 依赖清单
└── README.md
```

---

## 配置文件规范 (示例配置1.json)

工具支持如下格式的规则定义，保存在 `configs/` 目录下：

```json
{
  "配置名称": "用户ID数据查询与格式化示例",
  "触发该配置的前提": {
    "表格大小": [1, 1],
    "额外条件": {
      "位置": [0, 0],
      "正则表达式": "[0-9]{3,}"
    }
  },
  "触发后的流程": [
    {
      "动作": "提取某一格",
      "操作位置": [0, 0],
      "暂存到的变量名": "id"
    },
    {
      "动作": "发网络请求",
      "方法": "POST",
      "url": "https://example.com/api/user/{{id}}",
      "header": {
        "Content-Type": "application/json"
      },
      "body": "{\"id\": \"{{id}}\"}",
      "timeout": 10000,
      "callback": {
        "newData": "res.data[0]"
      }
    },
    {
      "动作": "用户输入",
      "提示文本": "请输入要提取第几个",
      "变量名": "index"
    },
    {
      "动作": "弹出提示框",
      "内容": "新内容为{{newData}}"
    },
    {
      "动作": "写入剪切板",
      "type": "table",
      "data": "{{id}},{{newData}},{{index}}"
    }
  ],
  "启用状态": true
}
```

---

## 快速上手与运行

### 1. 环境准备
确保已安装 Python 3.11+ / 3.13：
```bash
pip install -r requirements.txt
```

### 2. 启动图形化客户端 (GUI)
```bash
python3 main.py
```
操作步骤：
1. 顶部下拉框选择或者点击「新建」配置规则。
2. 在「低代码积木编辑器」中直观调整触发尺寸、正则规则与积木动作。
3. 点击顶部绿色按钮「开启该规则后台监控」。
4. 切换到 Excel 或其他文本编辑器复制表格，工具将自动捕获并执行全套流程！

### 3. CLI 仿真运行 (无头模式 / 脚本调试)
可以在终端中直接模拟剪切板输入，无需开启图形界面：
```bash
python3 main.py --simulate "888" --config configs/示例配置1.json
```
运行线上可用真实测试样例：
```bash
python3 main.py --simulate "octocat" --config configs/github_user_lookup.json
```

### 4. 运行全套自动化测试
```bash
python3 -m pytest -v
```
全套 34 个单元测试与图形化组件集成测试均可离线自动化运行并通过。
