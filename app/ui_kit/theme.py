"""
Centralised stylesheet for ChainPort Gateway.

Every QSS rule lives here so that nothing in main.py, MainWindow, or
individual pages can accidentally override these tokens.  Import
``APP_STYLESHEET`` and apply it once in ``main.py`` via
``QApplication.setStyleSheet()``.
"""

# ── Colour palette ────────────────────────────────────────────────
_BG_WINDOW = "#f3f5f9"
_BG_CARD = "#ffffff"
_BORDER_CARD = "#d8dfeb"
_TAB_IDLE = "#dde4ef"
_TAB_ACTIVE_BG = "#1f4b99"
_TAB_ACTIVE_FG = "#ffffff"
_ACCENT_PRIMARY = "#1f4b99"
_ACCENT_SUCCESS = "#2d7d46"
_ACCENT_DANGER = "#c0392b"
_ACCENT_WARNING = "#f59e0b"
_TEXT_PRIMARY = "#1f2b33"
_TEXT_SECONDARY = "#465158"
_TEXT_MUTED = "#64748b"
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
/* ── Window ────────────────────────────────────────── */
QMainWindow {{
    background: {_BG_WINDOW};
}}

/* ── Group boxes ───────────────────────────────────── */
QGroupBox {{
    font-weight: bold;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

/* ── Buttons ───────────────────────────────────────── */
QPushButton {{
    padding: 5px 12px;
    border: 1px solid #aaa;
    border-radius: 3px;
    background-color: #fff;
}}
QPushButton:hover {{
    background-color: #e8e8e8;
}}

/* ── Tables ────────────────────────────────────────── */
QTableWidget {{
    gridline-color: {_GRID_LINE};
    selection-background-color: {_SELECTION_BG};
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

/* ── Dashboard hero / cards ────────────────────────── */
QFrame#dashboardHero,
QFrame#dashboardPanel,
QFrame#dashboardStatCard,
QFrame#dashboardMetricCard {{
    background: {_BG_CARD};
    border: 1px solid {_BORDER_CARD};
    border-radius: 14px;
}}
QLabel#dashboardHeroTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {_TEXT_PRIMARY};
}}
QLabel#dashboardHeroSubtitle {{
    color: {_TEXT_SECONDARY};
}}
QLabel#dashboardPanelTitle,
QLabel#dashboardStatTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {_TEXT_MUTED};
    text-transform: uppercase;
}}
QLabel#dashboardStatValue {{
    font-size: 24px;
    font-weight: 700;
    color: #102646;
}}
QLabel#dashboardPreflightTitle {{
    font-size: 18px;
    font-weight: 700;
    color: #102646;
}}

/* ── Routing workspace cards & nested tabs ─────────── */
QFrame#routingStatCard {{
    background: {_BG_CARD};
    border: 1px solid {_BORDER_CARD};
    border-radius: 12px;
}}
QTabWidget#routingTabs::pane {{
    border: 1px solid {_BORDER_CARD};
    border-radius: 12px;
    background: {_BG_CARD};
    margin-top: 6px;
}}
QTabWidget#routingTabs > QTabBar::tab {{
    min-width: 160px;
    padding: 10px 14px;
    margin-right: 6px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    background: #e8edf5;
}}
QTabWidget#routingTabs > QTabBar::tab:selected {{
    background: {_TAB_ACTIVE_BG};
    color: {_TAB_ACTIVE_FG};
}}

/* ── Log area ──────────────────────────────────────── */
QPlainTextEdit#logArea {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 12px;
}}
"""
