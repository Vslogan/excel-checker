"""
VS Code style overview ruler / minimap vertical scrollbar for PyQt5.

Renders modern transparent acrylic track with real-time visual representation of:
- Current visible viewport (frosted glass thumb with accent indicator)
- Current visible action cards (illuminated with vibrant high-opacity colors and crisp borders)
- Current invisible action cards (elegantly rendered with semi-transparent pastel colors)
- Full interactivity: click to jump, drag to scroll, click marker to scroll card into view, and hover tooltips.
"""

from typing import Any, Callable, List, Optional
from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPen
from PyQt5.QtWidgets import QScrollBar, QScrollArea, QWidget


class VSCodeScrollBar(QScrollBar):
    """
    Modern transparent vertical scrollbar mimicking VS Code's editor overview ruler and minimap.
    """

    def __init__(
        self,
        scroll_area: QScrollArea,
        cards_getter: Optional[Callable[[], List[Any]]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(Qt.Vertical, parent)
        self.scroll_area = scroll_area
        self.cards_getter = cards_getter

        # Geometry and mouse tracking
        self.setFixedWidth(24)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        # Interaction state
        self._dragging: bool = False
        self._is_hovered: bool = False
        self._hovered_idx: Optional[int] = None
        self._drag_offset_y: float = 0.0

        # Minimal stylesheet to prevent OS native clunky buttons and margins
        self.setStyleSheet("""
            QScrollBar:vertical {
                width: 24px;
                background: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QScrollBar::handle:vertical {
                background: transparent;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        # Tooltip default
        self.setToolTip("VS Code 风格概览滚动条 (点击跳转 / 拖拽滚动)")

    # --- Geometry Calculation Helpers ---

    def _get_total_content_height(self) -> int:
        """Calculate total virtual content height."""
        container = self.scroll_area.widget()
        if container and container.height() > 0:
            return max(container.height(), self.maximum() - self.minimum() + self.pageStep())
        return max(1, self.maximum() - self.minimum() + self.pageStep())

    def _get_thumb_rect(self, track_w: float, track_h: float, total_h: float) -> QRectF:
        """Calculate the geometry of the visible viewport thumb."""
        if total_h <= 0 or self.maximum() <= self.minimum():
            return QRectF(2, 0, track_w - 4, track_h)

        scroll_y = float(self.value())
        viewport_h = float(max(1, self.pageStep()))

        thumb_top = (scroll_y / total_h) * track_h
        thumb_bottom = ((scroll_y + viewport_h) / total_h) * track_h
        thumb_h = max(24.0, thumb_bottom - thumb_top)

        if thumb_top + thumb_h > track_h:
            thumb_top = max(0.0, track_h - thumb_h)

        return QRectF(2.0, thumb_top, track_w - 4.0, thumb_h)

    def _get_card_markers(self, track_w: float, track_h: float, total_h: float):
        """
        Calculate track geometries and visibility for all action cards.
        Returns list of dict: {idx, card, rect, is_visible, color}
        """
        cards = self.cards_getter() if self.cards_getter else []
        markers = []
        if not cards or total_h <= 0:
            return markers

        scroll_y = float(self.value())
        viewport_h = float(max(1, self.pageStep()))
        visible_top = scroll_y
        visible_bottom = scroll_y + viewport_h

        for idx, card in enumerate(cards):
            try:
                card_y = float(card.pos().y())
                card_h = float(card.height())
            except Exception:
                continue

            card_bottom = card_y + card_h
            # Check if card is in visible viewport
            is_visible = not (card_bottom < visible_top or card_y > visible_bottom)

            # Map to scrollbar track coordinates
            m_top = (card_y / total_h) * track_h + 1.5
            m_h = max((card_h / total_h) * track_h - 3.0, 10.0)

            if m_top + m_h > track_h:
                m_h = max(4.0, track_h - m_top)

            # Pill width
            m_x = 3.5 if is_visible else 4.5
            m_w = (track_w - 7.0) if is_visible else (track_w - 9.0)
            rect = QRectF(m_x, m_top, m_w, m_h)

            color_str = getattr(card, "color_border", "#0284c7")
            markers.append({
                "idx": idx,
                "card": card,
                "rect": rect,
                "is_visible": is_visible,
                "color": QColor(color_str),
                "title": getattr(card, "display_title", f"步骤 {idx + 1}"),
            })

        return markers

    # --- Custom Painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        total_h = float(self._get_total_content_height())

        # 1. Modern Translucent Track Background (Subtle Acrylic Mica)
        track_bg = (
            QColor(241, 245, 249, 180) if self._is_hovered
            else QColor(248, 250, 252, 95)
        )
        painter.fillRect(self.rect(), track_bg)

        # Left separator line (delicate glass border)
        painter.setPen(QPen(QColor(226, 232, 240, 220), 1))
        painter.drawLine(0, 0, 0, int(h))

        # 2. Geometry calculations
        thumb_rect = self._get_thumb_rect(w, h, total_h)
        markers = self._get_card_markers(w, h, total_h)

        # 3. Layer A: Draw INVISIBLE cards (Outside thumb - soft translucent styling)
        for m in markers:
            if not m["is_visible"]:
                col = m["color"]
                # Soft translucent fill
                trans_col = QColor(col.red(), col.green(), col.blue(), 85)
                border_col = QColor(col.red(), col.green(), col.blue(), 135)

                painter.setBrush(QBrush(trans_col))
                painter.setPen(QPen(border_col, 1))
                painter.drawRoundedRect(m["rect"], 3.5, 3.5)

                # Muted step number if height permits
                if m["rect"].height() >= 13.0:
                    font = QFont("Arial", 7, QFont.Bold)
                    painter.setFont(font)
                    painter.setPen(QColor(255, 255, 255, 175))
                    painter.drawText(m["rect"], Qt.AlignCenter, str(m["idx"] + 1))

        # 4. Layer B: Draw Viewport Thumb (Frosted Glass with VS Code accent edge)
        thumb_fill = (
            QColor(100, 116, 139, 110) if self._dragging
            else (QColor(148, 163, 184, 85) if self._is_hovered else QColor(148, 163, 184, 60))
        )
        painter.setBrush(QBrush(thumb_fill))
        painter.setPen(QPen(QColor(148, 163, 184, 180), 1))
        painter.drawRoundedRect(thumb_rect, 4.5, 4.5)

        # Left accent neon line (VS Code viewport indicator)
        accent_h = max(4.0, thumb_rect.height() - 2.0)
        accent_rect = QRectF(2.0, thumb_rect.y() + 1.0, 2.5, accent_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(2, 132, 199, 240)))
        painter.drawRoundedRect(accent_rect, 1.0, 1.0)

        # 5. Layer C: Draw VISIBLE cards (Inside thumb - vibrant colors, illuminated glow)
        for m in markers:
            if m["is_visible"]:
                col = m["color"]
                vibrant_col = QColor(col.red(), col.green(), col.blue(), 245)

                painter.setBrush(QBrush(vibrant_col))
                # Crisp bright border for maximum clarity and glow
                painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
                painter.drawRoundedRect(m["rect"], 4.0, 4.0)

                # Step number in bold white
                if m["rect"].height() >= 13.0:
                    font = QFont("Arial", 8, QFont.Bold)
                    painter.setFont(font)
                    painter.setPen(QColor(255, 255, 255, 255))
                    painter.drawText(m["rect"], Qt.AlignCenter, str(m["idx"] + 1))

        # 6. Layer D: Highlight Hovered Card
        if self._hovered_idx is not None and 0 <= self._hovered_idx < len(markers):
            hovered_m = markers[self._hovered_idx]
            glow_pen = QPen(QColor(255, 255, 255, 240), 1.5)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(hovered_m["rect"].adjusted(-1, -1, 1, 1), 4.5, 4.5)

        painter.end()

    # --- Mouse & Interaction Handling ---

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        click_pos = event.pos()
        w = float(self.width())
        h = float(self.height())
        total_h = float(self._get_total_content_height())
        thumb_rect = self._get_thumb_rect(w, h, total_h)
        markers = self._get_card_markers(w, h, total_h)

        # 1. Did user click on a specific card marker?
        for m in markers:
            if m["rect"].contains(QPoint(click_pos.x(), click_pos.y())):
                # Immediately scroll that card into view
                card = m["card"]
                try:
                    card_y = card.pos().y()
                    self.setValue(max(self.minimum(), min(self.maximum(), int(card_y))))
                except Exception:
                    self.scroll_area.ensureWidgetVisible(card)
                self.update()
                return

        # 2. Did user click inside thumb? Start dragging
        if thumb_rect.contains(QPoint(click_pos.x(), click_pos.y())):
            self._dragging = True
            self._drag_offset_y = click_pos.y() - thumb_rect.y()
            self.update()
            return

        # 3. User clicked on empty track: center viewport at clicked position
        if h > 0:
            click_ratio = click_pos.y() / h
            viewport_h = float(max(1, self.pageStep()))
            target_val = int(click_ratio * total_h - viewport_h / 2.0)
            self.setValue(max(self.minimum(), min(self.maximum(), target_val)))
            self._dragging = True
            self._drag_offset_y = thumb_rect.height() / 2.0
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.pos()
        w = float(self.width())
        h = float(self.height())
        total_h = float(self._get_total_content_height())
        markers = self._get_card_markers(w, h, total_h)

        # If dragging thumb
        if self._dragging and h > 0:
            new_thumb_y = pos.y() - self._drag_offset_y
            viewport_h = float(max(1, self.pageStep()))
            scrollable_track_h = max(1.0, h - self._get_thumb_rect(w, h, total_h).height())
            scroll_ratio = max(0.0, min(1.0, new_thumb_y / scrollable_track_h))

            new_val = int(scroll_ratio * (self.maximum() - self.minimum()) + self.minimum())
            self.setValue(max(self.minimum(), min(self.maximum(), new_val)))
            self.update()
            return

        # Check marker hover & update rich tooltips
        found_idx = None
        for m in markers:
            if m["rect"].contains(QPoint(pos.x(), pos.y())):
                found_idx = m["idx"]
                status_str = "当前在页面内可见 (Visible)" if m["is_visible"] else "当前不可见 (Offscreen - 点击跳转直达)"
                color_hex = m["color"].name()
                tip = (
                    f"<b>第 {m['idx'] + 1} 步 · {m['title']}</b><br/>"
                    f"标识颜色: <span style='color:{color_hex}; font-weight:bold;'>■ {color_hex}</span><br/>"
                    f"视口状态: <b>{status_str}</b><br/>"
                    f"<i>点击积木条可立即滚动并定位至该步骤</i>"
                )
                self.setToolTip(tip)
                break

        if found_idx is None:
            self._hovered_idx = None
            self.setToolTip("VS Code 风格概览滚动条 (点击跳转 / 拖拽滚动)")
        else:
            self._hovered_idx = found_idx

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.update()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._hovered_idx = None
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        # Forward wheel event smoothly to parent scrollbar
        super().wheelEvent(event)
        self.update()
