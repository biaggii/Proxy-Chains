"""
main.py — ChainPort Gateway 程式入口

這個檔案就做三件事：
  1. 建立 AppState（載入 state.json）
  2. 建立 PySide6 QApplication
  3. 顯示 MainWindow
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
    """程式主入口"""

    # ---------- 1. 建立 AppState ----------
    # state.json 放在跟 main.py 同目錄
    state_file = os.path.join(project_root, "state.json")
    app_state = AppState(state_file_path=state_file)

    # ---------- 2. 建立 QApplication ----------
    qt_app = QApplication(sys.argv)

    # 設定全域字型（支援中文）
    font = QFont("Microsoft YaHei UI", 9)
    qt_app.setFont(font)

    # 設定全域樣式（簡單美化）
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

    # ---------- 3. 顯示 MainWindow ----------
    qt_app.setQuitOnLastWindowClosed(False)
    window = MainWindow(app_state)
    
    if not app_state.minimize_on_start:
        window.show()
    else:
        # User requested to run silently in the system tray
        pass

    # ---------- 4. 進入事件迴圈 ----------
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
