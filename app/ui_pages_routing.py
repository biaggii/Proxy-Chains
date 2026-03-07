from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from models.app_state import AppState


class RoutingPage(QWidget):
    def __init__(self, app_state: AppState, chains_page: QWidget, ports_page: QWidget, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.chains_page = chains_page
        self.ports_page = ports_page
        self._build_ui()
        if hasattr(self.chains_page, "data_changed"):
            self.chains_page.data_changed.connect(self.refresh_table)
        if hasattr(self.ports_page, "data_changed"):
            self.ports_page.data_changed.connect(self.refresh_table)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        intro = QLabel(
            "Routing is where you turn raw nodes into usable traffic paths. "
            "Build chains first, then expose them as local ports or choose one for TUN mode."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 13px; color: #465158; padding: 8px 4px;")
        layout.addWidget(intro)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 12px; color: #5c676c; padding: 0 4px 4px 4px;")
        layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.chains_page)
        splitter.addWidget(self.ports_page)
        splitter.setSizes([360, 420])
        layout.addWidget(splitter, 1)

        self.refresh_table()

    def refresh_table(self) -> None:
        if hasattr(self.chains_page, "refresh_table"):
            self.chains_page.refresh_table()
        if hasattr(self.ports_page, "refresh_table"):
            self.ports_page.refresh_table()

        tun_state = "On" if self.app_state.enable_tun else "Off"
        self.summary_label.setText(
            f"{len(self.app_state.chains)} chain(s) • "
            f"{len(self.app_state.port_mappings)} port binding(s) • "
            f"TUN {tun_state}"
        )
