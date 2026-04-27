"""
Live log display page.

Responsibilities:
  - Show core stdout/stderr in real time
  - Clear and copy log snapshots
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QApplication,
)
from PySide6.QtCore import Slot, QTimer


class LogsPage(QWidget):
    """Real-time log viewer for the running core process."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_buffer: list[str] = []
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

        self.log_area = QPlainTextEdit()
        self.log_area.setObjectName("logArea")
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(3000)
        # Styling is handled by the centralised theme via #logArea.
        layout.addWidget(self.log_area)

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
        """Buffer a log line (callable from background threads via signal)."""
        self._log_buffer.append(text)
        if len(self._log_buffer) > 1500:
            self._log_buffer = self._log_buffer[-1500:]

    def _flush_logs(self) -> None:
        if not self._log_buffer:
            return
        text = "\n".join(self._log_buffer)
        self._log_buffer.clear()
        self.log_area.appendPlainText(text)

    def _on_clear(self) -> None:
        """Clear all log output."""
        self.log_area.clear()

    def _on_copy_snapshot(self) -> None:
        text = self.log_area.toPlainText().strip()
        if not text:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    def refresh(self) -> None:
        """No-op — logs do not need table-style refreshing."""
        pass
