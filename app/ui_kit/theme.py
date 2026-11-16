"""
Centralised stylesheet for ChainPort Gateway.

Every QSS rule lives here so that nothing in main.py, MainWindow, or
individual pages can accidentally override these tokens.  Import
``APP_STYLESHEET`` and apply it once in ``main.py`` via
``QApplication.setStyleSheet()``.
"""

# ── Colour palette ────────────────────────────────────────────────
_BG_WINDOW = "#f3f5f9"
_BG_SURFACE = "#ffffff"
_BG_SUBTLE = "#f4f7fb"
_BORDER_CARD = "#d8dfeb"
_TAB_IDLE = "#dde4ef"
_TAB_ACTIVE_BG = "#1f4b99"
_TAB_ACTIVE_FG = "#ffffff"
_TEXT_PRIMARY = "#1f2b33"
_TEXT_SECONDARY = "#465158"
_TEXT_DISABLED = "#687586"
_SELECTION_BG = "#cce5ff"
_GRID_LINE = "#ddd"

# ── Feedback banner colours (used by set_feedback_banner) ─────────
FEEDBACK_COLORS: dict[str, tuple[str, str]] = {
    "success": ("#ecfdf3", "#166534"),
    "warning": ("#fff7ed", "#9a3412"),
    "error":   ("#fef2f2", "#991b1b"),
    "info":    ("#eff6ff", "#1d4ed8"),
}

# ── Single source of truth for all QSS ────────────────────────────
APP_STYLESHEET = f"""
/* Explicit foreground/background colours avoid unreadable platform palettes. */
QWidget {{
    color: {_TEXT_PRIMARY};
    font-size: 16px;
}}
QMainWindow, QWidget#centralWidget, QTabWidget::pane {{
    background-color: {_BG_WINDOW};
}}
QDialog, QMessageBox {{
    color: {_TEXT_PRIMARY};
    background-color: {_BG_WINDOW};
}}
QLabel {{
    color: {_TEXT_PRIMARY};
    background: transparent;
}}
QLabel#pageTitle {{
    color: {_TEXT_PRIMARY};
    font-size: 24px;
    font-weight: 700;
}}
QLabel#pageSubtitle {{
    color: {_TEXT_SECONDARY};
    font-size: 14px;
}}
QGroupBox {{
    color: {_TEXT_PRIMARY};
    background-color: {_BG_SURFACE};
    border: 1px solid {_BORDER_CARD};
    border-radius: 8px;
    margin-top: 13px;
    padding: 18px 12px 12px 12px;
}}
QGroupBox::title {{
    color: {_TEXT_PRIMARY};
    background-color: {_BG_SURFACE};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    font-weight: 700;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    color: {_TEXT_PRIMARY};
    background: #ffffff;
    selection-background-color: {_SELECTION_BG};
    selection-color: {_TEXT_PRIMARY};
    border: 1px solid #aeb9c8;
    border-radius: 5px;
    padding: 6px 8px;
    min-height: 25px;
}}
QTableWidget, QListWidget, QTreeWidget {{
    color: {_TEXT_PRIMARY};
    background: #ffffff;
    alternate-background-color: {_BG_SUBTLE};
    gridline-color: {_GRID_LINE};
    selection-background-color: {_SELECTION_BG};
    selection-color: {_TEXT_PRIMARY};
    border: 1px solid {_BORDER_CARD};
}}
QScrollArea, QScrollArea > QWidget > QWidget, QAbstractScrollArea::viewport {{
    color: {_TEXT_PRIMARY};
    background-color: {_BG_WINDOW};
}}
QHeaderView::section {{
    color: {_TEXT_PRIMARY};
    background: #e9eef5;
    padding: 9px 10px;
    border: 0;
    border-bottom: 1px solid {_BORDER_CARD};
    font-weight: 600;
}}
QCheckBox {{
    color: {_TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox:disabled {{
    color: {_TEXT_DISABLED};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid #77869a;
    border-radius: 4px;
    background-color: #ffffff;
}}
QCheckBox::indicator:checked {{
    background-color: #1f4b99;
    border: 1px solid #1f4b99;
}}
QCheckBox::indicator:disabled {{
    background-color: #e3e8ef;
    border-color: #b9c2ce;
}}
QPushButton {{
    color: {_TEXT_PRIMARY};
    background-color: {_BG_SURFACE};
    min-height: 30px;
    padding: 6px 14px;
    border: 1px solid #aeb9c8;
    border-radius: 5px;
}}
QPushButton:hover {{
    background-color: #eaf1fb;
    border-color: #7894b8;
}}
QPushButton:pressed {{
    background-color: #dce8f7;
}}
QPushButton:disabled {{
    color: {_TEXT_DISABLED};
    background-color: #edf0f4;
    border-color: #d5dbe3;
}}
QMenu {{
    color: {_TEXT_PRIMARY};
    background-color: #ffffff;
    border: 1px solid #aeb9c8;
    padding: 5px;
}}
QMenu::item {{
    color: {_TEXT_PRIMARY};
    background-color: transparent;
    padding: 8px 28px 8px 12px;
    min-width: 230px;
}}
QMenu::item:selected {{
    color: #ffffff;
    background-color: #1f4b99;
    border-radius: 3px;
}}
QMenu::item:disabled {{
    color: {_TEXT_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_BORDER_CARD};
    margin: 5px 6px;
}}
QComboBox QAbstractItemView {{
    color: {_TEXT_PRIMARY};
    background-color: #ffffff;
    selection-color: #ffffff;
    selection-background-color: #1f4b99;
    border: 1px solid #aeb9c8;
}}
QToolTip {{
    color: #ffffff;
    background-color: #263445;
    border: 1px solid #52647a;
    padding: 5px 7px;
}}
QTabBar::tab {{
    color: {_TEXT_PRIMARY};
}}
QStatusBar {{
    color: {_TEXT_PRIMARY};
}}
/* ── Top-level tab bar ─────────────────────────────── */
QTabWidget::pane {{
    border: 0;
    background: transparent;
}}
QTabBar::tab {{
    background: {_TAB_IDLE};
    padding: 10px 16px;
    border-radius: 10px;
    margin-right: 6px;
}}
QTabBar::tab:selected {{
    background: {_TAB_ACTIVE_BG};
    color: {_TAB_ACTIVE_FG};
}}

/* ── Banner label ──────────────────────────────────── */
QLabel#bannerLabel {{
    border-radius: 10px;
    padding: 10px 14px;
    font-weight: 600;
}}

/* ── Log area ──────────────────────────────────────── */
QPlainTextEdit#logArea {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 12px;
}}
"""
