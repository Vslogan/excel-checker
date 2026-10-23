"""Floating Toast Notification Window and Manager."""
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import QPoint, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor, QGuiApplication, QScreen
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)


class ToastWindow(QWidget):
    """Modern floating toast notification window."""

    closed = pyqtSignal()

    def __init__(
        self,
        content: str,
        duration_ms: int = 2000,
        position_mode: str = "bottom_center",
        target_screen: Optional[QScreen] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.content = content
        self.duration_ms = max(duration_ms, 200)
        self.position_mode = position_mode
        self.target_screen = target_screen or QApplication.primaryScreen()

        # Window flags: ToolTip, Frameless, Stays on Top, No Focus
        self.setWindowFlags(
            Qt.ToolTip
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._mouse_timer: Optional[QTimer] = None
        self.setup_ui()

    def setup_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Container card
        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 0.94);
                border: 1px solid #38bdf8;
                border-radius: 10px;
                padding: 10px 18px;
            }
        """)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(10)

        # Dot / Badge
        dot_label = QLabel("●")
        dot_label.setStyleSheet("color: #38bdf8; font-size: 13px;")
        card_layout.addWidget(dot_label)

        # Content Text
        self.label = QLabel(self.content)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("""
            color: #f8fafc;
            font-size: 13px;
            font-weight: 500;
            background: transparent;
        """)
        card_layout.addWidget(self.label)

        root_layout.addWidget(self.card)

        # Opacity effect for fade in/out
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.adjustSize()

    def show_toast(self):
        """Position and show toast with animations."""
        self.adjustSize()
        self._update_initial_position()

        self.show()

        # Fade in animation
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(160)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.start()

        # If follow mouse, start tracking timer
        if self.position_mode in ("follow_mouse", "持续跟随鼠标"):
            self._mouse_timer = QTimer(self)
            self._mouse_timer.setInterval(25)  # 40fps tracking
            self._mouse_timer.timeout.connect(self._track_mouse_position)
            self._mouse_timer.start()

        # Dismiss timer
        QTimer.singleShot(self.duration_ms, self.dismiss)

    def _update_initial_position(self):
        w = self.width()
        h = self.height()

        if self.position_mode in ("follow_mouse", "持续跟随鼠标"):
            pos = QCursor.pos()
            self.move(pos.x() + 16, pos.y() + 16)
            return

        screen = self.target_screen or QApplication.primaryScreen()
        geo = screen.geometry() if screen else QApplication.desktop().geometry()

        if self.position_mode in ("top_center", "顶部居中"):
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + 60
        elif self.position_mode in ("center", "正中间"):
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2
        else:  # default bottom_center
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + geo.height() - h - 80

        self.move(x, y)

    def _track_mouse_position(self):
        """Follow cursor smoothly and stay on screen."""
        pos = QCursor.pos()
        target_x = pos.x() + 18
        target_y = pos.y() + 18

        screen = QGuiApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            # Prevent going off right or bottom edges
            if target_x + self.width() > geo.right() - 10:
                target_x = pos.x() - self.width() - 10
            if target_y + self.height() > geo.bottom() - 10:
                target_y = pos.y() - self.height() - 10

        self.move(target_x, target_y)

    def dismiss(self):
        """Fade out and close."""
        if self._mouse_timer:
            self._mouse_timer.stop()

        self.fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out.setDuration(180)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self._on_fade_out_finished)
        self.fade_out.start()

    def _on_fade_out_finished(self):
        self.close()
        self.closed.emit()
        self.deleteLater()


class ToastManager:
    """Manages active toast instances across screens and blocking states."""

    _active_toasts: List[ToastWindow] = []

    @classmethod
    def show(
        cls,
        content: str,
        duration_ms: int = 2000,
        blocking: bool = False,
        screen_mode: str = "cursor",
        position_mode: str = "bottom_center",
        on_finished_cb: Optional[Callable[[], None]] = None,
    ):
        if not content or not content.strip():
            if on_finished_cb:
                on_finished_cb()
            return

        is_follow_mouse = position_mode in ("follow_mouse", "持续跟随鼠标")

        # Determine target screens
        target_screens: List[QScreen] = []
        if is_follow_mouse:
            # When follow_mouse, ignore screen selection and spawn one window
            target_screens = [QGuiApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()]
        elif screen_mode in ("all", "所有屏幕"):
            target_screens = QApplication.screens()
            if not target_screens:
                target_screens = [QApplication.primaryScreen()]
        else:
            # Cursor screen
            scr = QGuiApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            target_screens = [scr]

        remaining_count = [len(target_screens)]

        def _on_single_closed():
            remaining_count[0] -= 1
            if remaining_count[0] <= 0:
                if on_finished_cb:
                    on_finished_cb()

        for screen in target_screens:
            toast = ToastWindow(
                content=content,
                duration_ms=duration_ms,
                position_mode=position_mode,
                target_screen=screen,
            )
            toast.closed.connect(_on_single_closed)
            cls._active_toasts.append(toast)
            toast.show_toast()

    @classmethod
    def close_all(cls):
        """Close and cleanup all active toast windows."""
        for toast in list(cls._active_toasts):
            try:
                toast.close()
            except Exception:
                pass
        cls._active_toasts.clear()

