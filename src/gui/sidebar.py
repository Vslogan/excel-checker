"""Modular vertical sidebar navigation widget (Level 1 Menu)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class NavButton(QPushButton):
    """Custom styled navigation button for the sidebar."""

    def __init__(self, page_id: str, title: str, icon_symbol: str = "", parent: Optional[QWidget] = None):
        label_text = f" {icon_symbol} {title}" if icon_symbol else f" {title}"
        super().__init__(label_text, parent)
        self.page_id = page_id
        self.title = title
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding-left: 14px;
                padding-right: 14px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                color: #475569;
                background-color: transparent;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                color: #0f172a;
            }
            QPushButton:checked {
                background-color: #e0f2fe;
                color: #0284c7;
                font-weight: bold;
                border-left: 4px solid #0284c7;
            }
        """)


class SidebarNav(QWidget):
    """Modular vertical sidebar navigation (Level 1 Menu).

    Allows dynamic registration of pages for easy future expansion.
    """

    page_changed = pyqtSignal(str, int)  # page_id, page_index

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(210)
        self.buttons: List[NavButton] = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 12, 8, 12)
        self.main_layout.setSpacing(6)

        # Header title
        header_layout = QHBoxLayout()
        header_title = QLabel(" 功能导航")
        header_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #94a3b8; text-transform: uppercase;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        self.main_layout.addLayout(header_layout)

        # Container for navigation buttons
        self.nav_container = QWidget()
        self.nav_layout = QVBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(0, 4, 0, 4)
        self.nav_layout.setSpacing(4)
        self.main_layout.addWidget(self.nav_container)

        self.main_layout.addStretch()

        # Bottom version / info badge
        self.footer_label = QLabel("Excel Checker v2.0")
        self.footer_label.setAlignment(Qt.AlignCenter)
        self.footer_label.setStyleSheet("color: #94a3b8; font-size: 11px; padding: 6px;")
        self.main_layout.addWidget(self.footer_label)

        self.setStyleSheet("""
            SidebarNav {
                background-color: #ffffff;
                border-right: 1px solid #e2e8f0;
            }
        """)

    def add_page(
        self,
        page_id: str,
        title: str,
        widget: QWidget,
        stacked_widget: QStackedWidget,
        icon_symbol: str = "•",
        is_default: bool = False,
    ) -> int:
        """Register a new modular page into the sidebar and stacked widget."""
        btn = NavButton(page_id, title, icon_symbol, self)
        page_index = stacked_widget.addWidget(widget)

        self.buttons.append(btn)
        self.button_group.addButton(btn)
        self.nav_layout.addWidget(btn)

        # Wire click event
        btn.clicked.connect(lambda: self._on_btn_clicked(btn, page_id, page_index, stacked_widget))

        if is_default or len(self.buttons) == 1:
            btn.setChecked(True)
            stacked_widget.setCurrentIndex(page_index)

        return page_index

    def _on_btn_clicked(self, btn: NavButton, page_id: str, page_index: int, stacked_widget: QStackedWidget):
        stacked_widget.setCurrentIndex(page_index)
        self.page_changed.emit(page_id, page_index)

    def set_current_page(self, page_id: str):
        """Switch active page programmatically."""
        for btn in self.buttons:
            if btn.page_id == page_id:
                btn.click()
                break
