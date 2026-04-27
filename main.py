"""
Application entry point for ChainPort Gateway.

This module creates the persistent app state, starts Qt, and opens the main
window with any requested launch actions.
"""

import sys
import os

# Ensure the project root is on the Python path for clean imports.
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from models.app_state import AppState
from app.ui_main_window import MainWindow
from app.ui_kit.theme import APP_STYLESHEET


def main() -> None:
    """Start the desktop application."""

    state_file = os.path.join(project_root, "state.json")
    app_state = AppState(state_file_path=state_file)

    qt_app = QApplication(sys.argv)

    # Cross-platform font stack – avoids hard-coding a CJK-only typeface.
    font = QFont()
    font.setFamilies(["Segoe UI", "Microsoft YaHei UI", "Noto Sans", "sans-serif"])
    font.setPointSize(9)
    qt_app.setFont(font)

    # Single source of truth for all QSS (P0 fix: no more cascade war).
    qt_app.setStyleSheet(APP_STYLESHEET)

    qt_app.setQuitOnLastWindowClosed(False)
    window = MainWindow(app_state)

    if not app_state.minimize_on_start:
        window.show()
    window.schedule_launch_actions()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
