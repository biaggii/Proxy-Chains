from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from models.app_state import AppState


class _RoutingStatCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("routingStatCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #16386c;")
        layout.addWidget(self.value_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.4px;")
        layout.addWidget(title_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


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
            "Build chains first, then switch to Ports and TUN when you are ready to publish local endpoints."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 13px; color: #465158; padding: 8px 4px 0 4px;")
        layout.addWidget(intro)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 12px; color: #5c676c; padding: 0 4px 2px 4px;")
        layout.addWidget(self.summary_label)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)

        self.card_chains = _RoutingStatCard("CHAINS")
        self.card_bindings = _RoutingStatCard("BINDINGS")
        self.card_tun = _RoutingStatCard("TUN")
        self.card_nodes = _RoutingStatCard("NODES AVAILABLE")

        stats_row.addWidget(self.card_chains)
        stats_row.addWidget(self.card_bindings)
        stats_row.addWidget(self.card_tun)
        stats_row.addWidget(self.card_nodes)
        layout.addLayout(stats_row)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setDocumentMode(True)
        self.workspace_tabs.setStyleSheet(
            """
            QFrame#routingStatCard {
              background: white;
              border: 1px solid #d8dfeb;
              border-radius: 12px;
            }
            QTabWidget::pane {
              border: 1px solid #d8dfeb;
              border-radius: 12px;
              background: white;
              margin-top: 6px;
            }
            QTabBar::tab {
              min-width: 160px;
              padding: 10px 14px;
              margin-right: 6px;
              border-top-left-radius: 10px;
              border-top-right-radius: 10px;
              background: #e8edf5;
            }
            QTabBar::tab:selected {
              background: #1f4b99;
              color: white;
            }
            """
        )
        self.workspace_tabs.addTab(self.chains_page, "Chains")
        self.workspace_tabs.addTab(self.ports_page, "Ports & TUN")
        layout.addWidget(self.workspace_tabs, 1)

        self.refresh_table()

    def refresh_table(self) -> None:
        if hasattr(self.chains_page, "refresh_table"):
            self.chains_page.refresh_table()
        if hasattr(self.ports_page, "refresh_table"):
            self.ports_page.refresh_table()

        tun_state = "On" if self.app_state.enable_tun else "Off"
        self.summary_label.setText(
            "Use the tabs below to focus on one routing task at a time. "
            "Start with Chains, then move to Ports & TUN."
        )
        self.card_chains.set_value(str(len(self.app_state.chains)))
        self.card_bindings.set_value(str(len(self.app_state.port_mappings)))
        self.card_tun.set_value(tun_state)
        self.card_nodes.set_value(str(len(self.app_state.nodes)))
