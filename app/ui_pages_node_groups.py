"""Single workspace for base nodes, reusable chain nodes, sources and routing."""

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget
from PySide6.QtCore import Signal

from models.app_state import AppState


class NodeGroupsPage(QWidget):
    """Keep node acquisition and composition under one top-level workspace."""

    data_changed = Signal()

    def __init__(
        self,
        app_state: AppState,
        base_nodes_page: QWidget,
        chain_nodes_page: QWidget,
        subscriptions_page: QWidget,
        routing_page: QWidget,
        parent=None,
    ):
        super().__init__(parent)
        self.app_state = app_state
        self.base_nodes_page = base_nodes_page
        self.chain_nodes_page = chain_nodes_page
        self.subscriptions_page = subscriptions_page
        self.routing_page = routing_page

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sections = QTabWidget()
        self.sections.setDocumentMode(True)
        self.sections.addTab(base_nodes_page, "Base Nodes")
        self.sections.addTab(chain_nodes_page, "Chain Nodes")
        self.sections.addTab(routing_page, "Create Chain / Ports")
        self.sections.addTab(subscriptions_page, "Subscriptions")
        layout.addWidget(self.sections)

        for page in (
            base_nodes_page,
            chain_nodes_page,
            subscriptions_page,
        ):
            signal = getattr(page, "data_changed", None)
            if signal is not None:
                signal.connect(self._on_child_changed)

        for page in (
            getattr(routing_page, "chains_page", None),
            getattr(routing_page, "ports_page", None),
        ):
            signal = getattr(page, "data_changed", None)
            if signal is not None:
                signal.connect(self._on_child_changed)

    def _on_child_changed(self) -> None:
        self.refresh()
        self.data_changed.emit()

    def refresh(self) -> None:
        """Refresh all sections without changing the selected section."""
        for page in (
            self.base_nodes_page,
            self.chain_nodes_page,
            self.subscriptions_page,
            self.routing_page,
        ):
            refresh = getattr(page, "refresh", None)
            if refresh:
                refresh()

    def open_section(self, key: str) -> None:
        """Navigate legacy dashboard actions into the matching inner section."""
        section_by_key = {
            "nodes": 0,
            "chain_nodes": 1,
            "chains": 2,
            "routing": 2,
            "ports": 2,
            "subscriptions": 3,
        }
        index = section_by_key.get(key)
        if index is not None:
            self.sections.setCurrentIndex(index)
        if key == "ports" and hasattr(self.routing_page, "workspace_tabs"):
            self.routing_page.workspace_tabs.setCurrentIndex(1)
        elif key in {"chains", "routing"} and hasattr(self.routing_page, "workspace_tabs"):
            self.routing_page.workspace_tabs.setCurrentIndex(0)
