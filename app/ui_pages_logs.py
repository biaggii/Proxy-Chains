"""
ui_pages_logs.py — 核心 Log 顯示頁面

功能：
  - 顯示核心 stdout/stderr 的即時 log
  - 清除 log
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QApplication,
)
from PySide6.QtCore import Signal, Slot, QTimer


class LogsPage(QWidget):
    """Log 顯示頁面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_buffer = []
        self._init_ui()
        
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_logs)
        self._flush_timer.start(100)  # Flush logs every 100ms to prevent UI freezing

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.summary_label = QLabel(
            "Runtime output appears here while applying, verifying, or running the selected core."
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # Log 文字區域（唯讀）
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(3000)  # Reduce from 5000 to 3000 to save memory
        self.log_area.setStyleSheet(
            "QPlainTextEdit { "
            "  background-color: #1e1e1e; "
            "  color: #d4d4d4; "
            "  font-family: Consolas, 'Courier New', monospace; "
            "  font-size: 12px; "
            "}"
        )
        layout.addWidget(self.log_area)

        # 按鈕
        btn_row = QHBoxLayout()
        btn_clear = QPushButton("🧹 Clear Logs")
        btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(btn_clear)

        btn_copy = QPushButton("Copy Snapshot")
        btn_copy.clicked.connect(self._on_copy_snapshot)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    @Slot(str)
    def append_log(self, text: str) -> None:
        """Buffer a log line (callable from background threads via signal)"""
        self._log_buffer.append(text)
        # Cap pending buffer size to prevent out of memory on severe floods
        if len(self._log_buffer) > 1500:
            self._log_buffer = self._log_buffer[-1500:]

    def _flush_logs(self) -> None:
        if not self._log_buffer:
            return
        
        text = "\n".join(self._log_buffer)
        self._log_buffer.clear()
        self.log_area.appendPlainText(text)

    def _on_clear(self) -> None:
        """清除所有 log"""
        self.log_area.clear()

    def _on_copy_snapshot(self) -> None:
        text = self.log_area.toPlainText().strip()
        if not text:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    def refresh_table(self) -> None:
        """LogsPage 不需要刷新表格，但介面統一需要這個方法"""
        pass
