"""规则可视化编辑器：类低代码积木编程。

编辑内容：配置名称、触发前提（表格大小 + 单元格正则条件）、
按顺序执行的动作步骤列表。每个动作以一张卡片呈现，字段随动作类型
动态切换，后续新增动作只需在 ACTION_SPECS/FIELD_SPECS 中注册。
"""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import CellCondition, RuleConfig, Size, Trigger


class KVTable(QWidget):
    """键值对表格编辑（用于 header / callback 等）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["键", "值"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        btns = QHBoxLayout()
        btn_add = QPushButton("添加行")
        btn_del = QPushButton("删除选中行")
        btn_add.clicked.connect(self._add_row)
        btn_del.clicked.connect(self._del_row)
        btns.addWidget(btn_add)
        btns.addWidget(btn_del)
        btns.addStretch()
        layout.addLayout(btns)

    def _add_row(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(""))
        self.table.setItem(r, 1, QTableWidgetItem(""))

    def _del_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def value(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for r in range(self.table.rowCount()):
            key_item = self.table.item(r, 0)
            val_item = self.table.item(r, 1)
            key = key_item.text().strip() if key_item else ""
            if not key:
                continue
            result[key] = val_item.text() if val_item else ""
        return result

    def set_value(self, data: dict[str, str]) -> None:
        self.table.setRowCount(0)
        for key, val in (data or {}).items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(key)))
            self.table.setItem(r, 1, QTableWidgetItem(str(val)))


class CellEdit(QWidget):
    """单元格位置编辑器：[行, 列]。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spin_row = QSpinBox()
        self.spin_row.setRange(0, 1000000)
        self.spin_col = QSpinBox()
        self.spin_col.setRange(0, 1000000)
        layout.addWidget(self.spin_row)
        layout.addWidget(QLabel(","))
        layout.addWidget(self.spin_col)
        layout.addStretch()

    def value(self) -> list[int]:
        return [self.spin_row.value(), self.spin_col.value()]

    def set_value(self, cell: list[int] | tuple[int, int]) -> None:
        self.spin_row.setValue(int(cell[0]))
        self.spin_col.setValue(int(cell[1]))


class StepCard(QGroupBox):
    """单个动作步骤的卡片：动作类型下拉 + 动态参数表单。"""

    # 键 -> (标签, 字段种类)
    FIELD_SPECS: dict[str, list[tuple[str, str, str]]] = {
        "extract_cell": [
            ("cell", "单元格位置 (行,列)", "cell"),
            ("variable", "暂存变量名", "text"),
        ],
        "http_request": [
            ("method", "请求方法", "method"),
            ("url", "URL（支持 {{var}}）", "url"),
            ("headers", "Header（键值对，支持 {{var}}）", "kv"),
            ("body", "Body（JSON 或文本，支持 {{var}}）", "body"),
            ("timeout", "超时时间（ms）", "timeout"),
            ("callback", "回调：变量名 <- JSON 路径", "callback"),
        ],
        "user_input": [
            ("prompt", "提示文本", "text"),
            ("variable", "变量名", "text"),
        ],
        "alert": [
            ("content", "提示内容（支持 {{var}}）", "text"),
        ],
        "write_clipboard": [
            ("type", "写入类型", "clipboard_type"),
            ("data", "数据", "clipboard_data"),
        ],
    }

    ACTIONS: list[tuple[str, str]] = [
        ("extract_cell", "提取单元格"),
        ("http_request", "发送网络请求"),
        ("user_input", "用户输入（弹出输入框）"),
        ("alert", "弹出提示框"),
        ("write_clipboard", "写入剪贴板"),
    ]

    def __init__(self, step: dict[str, Any] | None, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._step = dict(step) if step else {"action": "extract_cell"}
        self._widgets: dict[str, QWidget] = {}
        self.setTitle(f"步骤 {index + 1}")

        layout = QVBoxLayout(self)

        # 表头：动作类型 + 删除
        header = QHBoxLayout()
        self.lbl_index = QLabel(f"步骤 {index + 1}")
        self.combo_action = QComboBox()
        for key, label in self.ACTIONS:
            self.combo_action.addItem(label, key)
        self.combo_action.setCurrentText(
            next(label for key, label in self.ACTIONS if key == self._step.get("action"))
        )
        self.btn_remove = QPushButton("删除")
        header.addWidget(self.lbl_index)
        header.addWidget(QLabel("动作："))
        header.addWidget(self.combo_action)
        header.addStretch()
        header.addWidget(self.btn_remove)
        layout.addLayout(header)

        self.form = QFormLayout()
        layout.addLayout(self.form)

        self.combo_action.currentIndexChanged.connect(self._rebuild_fields)
        self.btn_remove.clicked.connect(self._on_remove)
        self._remove_callback = None  # type: ignore[assignment]
        self._rebuild_fields()

    def set_remove_callback(self, callback) -> None:
        self._remove_callback = callback

    def _on_remove(self) -> None:
        if self._remove_callback:
            self._remove_callback(self)

    def _rebuild_fields(self) -> None:
        # 清空旧字段
        while self.form.rowCount():
            self.form.removeRow(0)
        self._widgets = {}

        action = self.combo_action.currentData()
        specs = self.FIELD_SPECS.get(action, [])
        for key, label, kind in specs:
            widget = self._make_field(kind, key)
            self._widgets[key] = widget
            self.form.addRow(label, widget)

        self._fill_values()

    def _make_field(self, kind: str, key: str) -> QWidget:
        if kind == "text":
            widget = QLineEdit()
        elif kind == "url":
            widget = QLineEdit()
            widget.setPlaceholderText("如 http://example.com/{{id}}")
        elif kind == "method":
            widget = QComboBox()
            widget.addItems(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
        elif kind == "cell":
            widget = CellEdit()
        elif kind == "timeout":
            widget = QSpinBox()
            widget.setRange(1, 86400000)
            widget.setValue(10000)
        elif kind == "kv":
            widget = KVTable()
        elif kind == "callback":
            widget = KVTable()
        elif kind == "body":
            widget = QTextEdit()
            widget.setPlaceholderText('如 {"id": "{{id}}"} 或 纯文本内容')
        elif kind == "clipboard_type":
            widget = QComboBox()
            widget.addItems(["text", "table"])
        elif kind == "clipboard_data":
            widget = ClipboardDataEdit()
        else:
            widget = QLineEdit()
        return widget

    def _fill_values(self) -> None:
        action = self.combo_action.currentData()
        for key, widget in self._widgets.items():
            value = self._step.get(key)
            if isinstance(widget, CellEdit) and value:
                widget.set_value(value)
            elif isinstance(widget, KVTable) and isinstance(value, dict):
                widget.set_value(value)
            elif isinstance(widget, ClipboardDataEdit):
                widget.set_value(self._step.get("type", "text"), value)
            elif isinstance(widget, QComboBox) and not isinstance(widget, CellEdit):
                if key == "type" and isinstance(value, str):
                    widget.setCurrentText(value)
                elif isinstance(value, str):
                    widget.setCurrentText(value)
            elif isinstance(widget, QSpinBox) and isinstance(value, (int, float)):
                widget.setValue(int(value))
            elif isinstance(widget, (QLineEdit, QTextEdit)) and isinstance(value, str):
                if isinstance(widget, QTextEdit):
                    widget.setPlainText(value)
                else:
                    widget.setText(value)

    def collect(self) -> dict[str, Any]:
        action = self.combo_action.currentData()
        step: dict[str, Any] = {"action": action}
        for key, widget in self._widgets.items():
            if isinstance(widget, CellEdit):
                step[key] = widget.value()
            elif isinstance(widget, KVTable):
                step[key] = widget.value()
            elif isinstance(widget, ClipboardDataEdit):
                step["type"] = self._widgets["type"].currentText()  # type: ignore[index]
                step[key] = widget.value()
            elif isinstance(widget, QComboBox):
                if key == "type":
                    step[key] = widget.currentText()
                else:
                    step[key] = widget.currentText()
            elif isinstance(widget, QSpinBox):
                step[key] = widget.value()
            elif isinstance(widget, QTextEdit):
                text = widget.toPlainText()
                step[key] = text
            elif isinstance(widget, QLineEdit):
                step[key] = widget.text()
        # 步骤索引重排在外部收集时统一处理
        return step


class ClipboardDataEdit(QWidget):
    """write_clipboard 的数据编辑：text 用单行文本，table 用小表格。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QLineEdit()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["列1", "列2"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stack = None  # 由外部切换可见性
        self._widgets = (self.text_edit, self.table)
        for w in self._widgets:
            layout.addWidget(w)
        self.set_mode("text")

    def set_mode(self, mode: str) -> None:
        show_text = mode == "text"
        self.text_edit.setVisible(show_text)
        self.table.setVisible(not show_text)

    def set_value(self, mode: str, data: Any) -> None:
        self.set_mode(mode)
        if mode == "table" and isinstance(data, list):
            self.table.setRowCount(len(data))
            for r, row in enumerate(data):
                for c, cell in enumerate(row):
                    if c >= self.table.columnCount():
                        self.table.setColumnCount(c + 1)
                        self.table.setHorizontalHeaderItem(
                            c, QTableWidgetItem(f"列{c + 1}")
                        )
                    self.table.setItem(r, c, QTableWidgetItem(str(cell)))
        else:
            self.text_edit.setText(str(data or ""))

    def value(self) -> Any:
        if self.text_edit.isVisible():
            return self.text_edit.text()
        rows: list[list[str]] = []
        for r in range(self.table.rowCount()):
            row = []
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                row.append(item.text() if item else "")
            rows.append(row)
        return rows


class ConfigEditor(QDialog):
    """整条规则的可视化编辑器。"""

    def __init__(
        self, rule: RuleConfig | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._rule = (
            rule
            or RuleConfig(
                name="新配置",
                trigger=Trigger(size=Size(rows=1, cols=1)),
                steps=[],
            )
        )
        self._step_cards: list[StepCard] = []
        self.setWindowTitle("规则配置编辑器")
        self.resize(850, 750)
        self._build_ui()
        self._load_rule()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 配置名称
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("配置名称："))
        self.edit_name = QLineEdit()
        name_row.addWidget(self.edit_name)
        layout.addLayout(name_row)

        # 触发前提
        grp_trigger = QGroupBox("触发前提（必须全部满足）")
        fl = QFormLayout()
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 1000000)
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 1000000)
        fl.addRow("复制表格大小 - 行数", self.spin_rows)
        fl.addRow("复制表格大小 - 列数", self.spin_cols)
        grp_trigger.setLayout(fl)
        layout.addWidget(grp_trigger)

        # 额外条件
        grp_cond = QGroupBox("额外条件（可选，如 (0,0) 格须匹配正则 [0-9]{3,}）")
        cv = QVBoxLayout()
        self.tbl_conditions = QTableWidget(0, 3)
        self.tbl_conditions.setHorizontalHeaderLabels(["单元格行", "单元格列", "正则 pattern"])
        self.tbl_conditions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cv.addWidget(self.tbl_conditions)
        cb = QHBoxLayout()
        btn_add_cond = QPushButton("添加条件")
        btn_del_cond = QPushButton("删除选中条件")
        btn_add_cond.clicked.connect(self._add_cond_row)
        btn_del_cond.clicked.connect(self._del_cond_row)
        cb.addWidget(btn_add_cond)
        cb.addWidget(btn_del_cond)
        cb.addStretch()
        cv.addLayout(cb)
        grp_cond.setLayout(cv)
        layout.addWidget(grp_cond)

        # 动作步骤
        grp_steps = QGroupBox("触发后的动作步骤（按顺序执行）")
        sv = QVBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.steps_container = QWidget()
        self.steps_box = QVBoxLayout(self.steps_container)
        self.steps_box.addStretch()
        self.scroll.setWidget(self.steps_container)
        sv.addWidget(self.scroll)
        hb = QHBoxLayout()
        self.btn_add_step = QPushButton("添加动作步骤")
        self.btn_add_step.clicked.connect(self._add_step)
        hb.addWidget(self.btn_add_step)
        hb.addStretch()
        sv.addLayout(hb)
        grp_steps.setLayout(sv)
        layout.addWidget(grp_steps)

        # 底部按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ 加载与收集

    def _load_rule(self) -> None:
        self.edit_name.setText(self._rule.name)
        self.spin_rows.setValue(self._rule.trigger.size.rows)
        self.spin_cols.setValue(self._rule.trigger.size.cols)
        for cond in self._rule.trigger.conditions:
            self._add_cond_row([cond.cell[0], cond.cell[1], cond.pattern])
        for step in self._rule.steps:
            self._append_step_card(step)

    def _add_cond_row(self, values: list[Any] | None = None) -> None:
        r = self.tbl_conditions.rowCount()
        self.tbl_conditions.insertRow(r)
        for c, v in enumerate((values or ["", "", ""])[:3]):
            self.tbl_conditions.setItem(r, c, QTableWidgetItem(str(v)))

    def _del_cond_row(self) -> None:
        r = self.tbl_conditions.currentRow()
        if r >= 0:
            self.tbl_conditions.removeRow(r)

    def _append_step_card(self, step: dict[str, Any] | None = None) -> None:
        index = len(self._step_cards)
        card = StepCard(step, index, self)
        card.set_remove_callback(self._remove_step_card)
        self._step_cards.append(card)
        self.steps_box.insertWidget(index, card)
        self._refresh_step_titles()

    def _add_step(self) -> None:
        action, ok = self._choose_action()
        if not ok:
            return
        self._append_step_card({"action": action})

    @staticmethod
    def _choose_action() -> tuple[str, bool]:
        labels = [label for _, label in StepCard.ACTIONS]
        from PyQt5.QtWidgets import QInputDialog

        item, ok = QInputDialog.getItem(
            None, "选择动作", "请选择要添加的动作类型：", labels, editable=False
        )
        if not ok or not item:
            return "", False
        for key, label in StepCard.ACTIONS:
            if label == item:
                return key, True
        return "", False

    def _remove_step_card(self, card: StepCard) -> None:
        if card in self._step_cards:
            self._step_cards.remove(card)
            card.setParent(None)
            card.deleteLater()
        self._refresh_step_titles()

    def _refresh_step_titles(self) -> None:
        for i, card in enumerate(self._step_cards):
            card.setTitle(f"步骤 {i + 1}")
            card.lbl_index.setText(f"步骤 {i + 1}")

    def _accept(self) -> None:
        try:
            rule = self._collect_rule()
        except ValueError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return
        self._rule = rule
        self.accept()

    def _collect_rule(self) -> RuleConfig:
        name = self.edit_name.text().strip()
        if not name:
            raise ValueError("配置名称不能为空")

        conditions = []
        for r in range(self.tbl_conditions.rowCount()):
            items = [
                self.tbl_conditions.item(r, c) for c in range(3)
            ]
            if not all(items) or not all(it.text().strip() for it in items):
                continue
            try:
                row = int(items[0].text())
                col = int(items[1].text())
            except ValueError:
                raise ValueError(f"第 {r + 1} 行条件的单元格行/列必须是整数")
            pattern = items[2].text().strip()
            conditions.append(CellCondition(cell=(row, col), pattern=pattern))

        steps = [card.collect() for card in self._step_cards]

        data: dict[str, Any] = {
            "name": name,
            "trigger": {
                "size": {"rows": self.spin_rows.value(), "cols": self.spin_cols.value()},
                "conditions": [
                    {"cell": [c.cell[0], c.cell[1]], "pattern": c.pattern}
                    for c in conditions
                ],
            },
            "steps": steps,
        }
        return RuleConfig.from_dict(data)

    def rule(self) -> RuleConfig:
        return self._rule
