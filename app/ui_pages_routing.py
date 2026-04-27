"""
Routing workspace page.

A lightweight container that hosts the Chains and Ports sub-tabs.
Duplicate metric cards have been removed — the Dashboard is the
single source for at-a-glance stats.
"""

from PySide6.QtWidgets import (
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from models.app_state import AppState


class RoutingPage(QWidget):
    """Combined routing workspace hosting Chains and Ports tabs."""

    def __init__(self, app_state: AppState, chains_page: QWidget, ports_page: QWidget, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.chains_page = chains_page
        self.ports_page = ports_page
        self._build_ui()
        if hasattr(self.chains_page, "data_changed"):
            self.chains_page.data_changed.connect(self.refresh)
        if hasattr(self.ports_page, "data_changed"):
            self.ports_page.data_changed.connect(self.refresh)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # One-line summary replaces the verbose paragraph + duplicate metric cards.
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #465158; padding: 8px 4px 0 4px;")
        layout.addWidget(self.summary_label)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("routingTabs")
        self.workspace_tabs.setDocumentMode(True)
        # No inline QSS — the centralised theme handles routingTabs styling.
        self.workspace_tabs.addTab(self.chains_page, "Chains")
        self.workspace_tabs.addTab(self.ports_page, "Ports & TUN")
        layout.addWidget(self.workspace_tabs, 1)

        self.refresh()

    def refresh(self) -> None:
        """Refresh child pages and the summary label."""
        if hasattr(self.chains_page, "refresh"):
            self.chains_page.refresh()
        if hasattr(self.ports_page, "refresh"):
            self.ports_page.refresh()

        chains = len(self.app_state.chains)
        bindings = len(self.app_state.port_mappings)
        tun_state = "enabled" if self.app_state.enable_tun else "disabled"
        self.summary_label.setText(
            f"{chains} chain(s) · {bindings} binding(s) · TUN {tun_state}"
        )
