"""
Application entry point for ChainPort Gateway.

This module creates the persistent app state, starts Qt, and opens the main
window with any requested launch actions.
"""

import sys
import os

# 把專案根目錄加入 Python 路徑（確保 import 不出錯）
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from models.app_state import AppState
from app.ui_main_window import MainWindow


def main() -> None:
    """Start the desktop application."""

    state_file = os.path.join(project_root, "state.json")
    app_state = AppState(state_file_path=state_file)

    qt_app = QApplication(sys.argv)

    font = QFont("Microsoft YaHei UI", 9)
    qt_app.setFont(font)

    qt_app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #ccc;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QPushButton {
            padding: 5px 12px;
            border: 1px solid #aaa;
            border-radius: 3px;
            background-color: #fff;
        }
        QPushButton:hover {
            background-color: #e8e8e8;
        }
        QTableWidget {
            gridline-color: #ddd;
            selection-background-color: #cce5ff;
        }
        QTabWidget::pane {
            border: 1px solid #ccc;
        }
        QTabBar::tab {
            padding: 6px 16px;
        }
        QTabBar::tab:selected {
            background: #fff;
            border-bottom: 2px solid #3498db;
        }
    """)

    qt_app.setQuitOnLastWindowClosed(False)
    window = MainWindow(app_state)
    
    if not app_state.minimize_on_start:
        window.show()
    window.schedule_launch_actions()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
