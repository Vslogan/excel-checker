"""剪贴板监控：把剪贴板内容解析为二维表格，供规则引擎消费。

兼容约定：
- 文本/CSV 等显式格式：按行/列解析为表格。
- 普通纯文本（部分软件把 1x1 表格复制为纯文本）：统一视为 1x1 表格，由后续规则条件做判断。
- 多行文本或含制表符的文本：按换行拆行、制表符/逗号拆列。

注意：PyQt5 的 QtGui 模块在按需导入，以便纯头less 环境也能导入本模块并
测试解析逻辑；真正实例化 ClipboardMonitor 时才需要 Qt 图形支持。
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from typing import Any

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


@dataclass
class ClipboardTable:
    rows: list[list[str]]
    source: str  # "csv" / "text"

    @property
    def size(self) -> tuple[int, int]:
        return (len(self.rows), max((len(r) for r in self.rows), default=0))


def _parse_csv_text(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    return [list(row) for row in reader]


def _parse_plain_text(text: str) -> list[list[str]]:
    """纯文本转表格：含制表符/换行则按表格解析，否则视为 1x1。"""
    if "\t" in text or "\n" in text or "\r" in text:
        rows: list[list[str]] = []
        for line in text.splitlines():
            if not line:
                continue
            if "\t" in line:
                rows.append(line.split("\t"))
            elif "," in line:
                rows.append([cell.strip() for cell in line.split(",")])
            else:
                rows.append([line])
        return rows if rows else [[]]
    return [[text]]


def parse_mime_data(mime: Any) -> ClipboardTable | None:
    """从剪贴板 MIME 数据解析表格；mime 需实现 hasFormat/data/hasText/text。
    无可用内容返回 None。
    """
    if mime.hasFormat("text/csv"):
        data = mime.data("text/csv")
        if isinstance(data, str):
            text = data
        else:
            text = bytes(data).decode("utf-8", errors="replace")
        return ClipboardTable(rows=_parse_csv_text(text), source="csv")
    if mime.hasText():
        text = mime.text()
        if text:
            return ClipboardTable(rows=_parse_plain_text(text), source="text")
    return None


class ClipboardMonitor(QObject):
    """后台轮询剪贴板，内容变化时发出 newTable 信号。"""

    newTable = pyqtSignal(object)  # ClipboardTable
    error = pyqtSignal(str)

    def __init__(self, interval_ms: int = 1000, parent: QObject | None = None) -> None:
        # QtGui 按需导入：headless 环境下可不实例化此类
        from PyQt5.QtGui import QGuiApplication  # noqa: PLC0415

        super().__init__(parent)
        app = QGuiApplication.instance()
        if app is None:
            raise RuntimeError("ClipboardMonitor 需要先创建 QGuiApplication/QApplication")
        self._clipboard = app.clipboard()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self._last_key: str | None = None

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        try:
            mime = self._clipboard.mimeData()
        except Exception as exc:  # pragma: no cover - 平台剪贴板异常
            self.error.emit(str(exc))
            return
        key = self._mime_key(mime)
        if key == self._last_key:
            return
        table = parse_mime_data(mime)
        if table is None:
            return
        self._last_key = key
        self.newTable.emit(table)

    @staticmethod
    def _mime_key(mime: Any) -> str:
        formats = ",".join(sorted(mime.formats()))
        text = mime.text() if mime.hasText() else ""
        digest = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
        return f"{formats}|{digest}"
