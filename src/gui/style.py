"""Modern QSS stylesheet and visual constants for the GUI."""

APP_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #f8fafc;
    color: #1e293b;
    font-family: "WenQuanYi Micro Hei", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}

QWidget {
    font-family: "WenQuanYi Micro Hei", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    color: #1e293b;
}

/* ToolBar & Top Bar */
QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 6px;
    spacing: 8px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #e2e8f0;
    background: #ffffff;
    border-radius: 6px;
}

QTabBar::tab {
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-bottom-color: #e2e8f0;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    margin-right: 4px;
    font-weight: 500;
    color: #475569;
}

QTabBar::tab:selected {
    background: #ffffff;
    border-color: #e2e8f0;
    border-bottom-color: #ffffff;
    color: #0284c7;
    font-weight: bold;
}

/* GroupBox */
QGroupBox {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 14px;
    padding: 16px;
    font-weight: bold;
    color: #0f172a;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background: #ffffff;
    color: #0284c7;
}

/* Buttons */
QPushButton {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 14px;
    color: #334155;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
}

QPushButton:pressed {
    background-color: #f1f5f9;
}

QPushButton#primaryBtn {
    background-color: #0284c7;
    border: 1px solid #0284c7;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#primaryBtn:hover {
    background-color: #0369a1;
}

QPushButton#successBtn {
    background-color: #10b981;
    border: 1px solid #10b981;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#successBtn:hover {
    background-color: #059669;
}

QPushButton#dangerBtn {
    background-color: #ef4444;
    border: 1px solid #ef4444;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#dangerBtn:hover {
    background-color: #dc2626;
}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 5px 8px;
    color: #1e293b;
    selection-background-color: #bae6fd;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0284c7;
    background-color: #f0f9ff;
}

/* Block Cards */
QFrame.actionCard {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #0284c7;
    border-radius: 8px;
    padding: 10px;
}

QFrame.actionCard:hover {
    border-color: #cbd5e1;
    border-left: 4px solid #0369a1;
}

/* ScrollArea */
QScrollArea {
    border: none;
    background-color: transparent;
}

/* Log view */
QPlainTextEdit#logConsole {
    background-color: #0f172a;
    color: #38bdf8;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    border-radius: 6px;
    border: 1px solid #334155;
}

/* Badges and Tags */
QLabel.badge {
    background-color: #e0f2fe;
    color: #0369a1;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: bold;
}

QLabel.badgeActive {
    background-color: #dcfce7;
    color: #15803d;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: bold;
}

QLabel.badgeInactive {
    background-color: #f1f5f9;
    color: #64748b;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
}
"""
