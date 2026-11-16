"""Node Groups workspace with separate Base Nodes and Chain Nodes lists."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.ui_pages_base_nodes import BaseNodesPage
from app.ui_pages_chains import ChainsPage
from models.app_state import AppState


class NodeGroupsPage(QWidget):
    data_changed = Signal()
    active_node_changed = Signal(str)
    runtime_config_changed = Signal()

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.base_page = BaseNodesPage(app_state)
        self.chain_page = ChainsPage(app_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(16)
        self.sections = QTabWidget()
        self.sections.setDocumentMode(True)
        self.sections.setContentsMargins(0, 6, 0, 0)
        self.sections.setStyleSheet(
            "QTabWidget::pane { border: 0; background: transparent; }"
            "QTabBar::tab { margin-top: 2px; margin-bottom: 4px; }"
        )
        self.sections.addTab(self.base_page, "Base")
        self.sections.addTab(self.chain_page, "Chain")
        layout.addWidget(self.sections)

        self.base_page.data_changed.connect(self.data_changed.emit)
        self.base_page.runtime_config_changed.connect(self.runtime_config_changed.emit)
        self.chain_page.data_changed.connect(self.data_changed.emit)
        self.chain_page.runtime_config_changed.connect(self.runtime_config_changed.emit)
        self.base_page.active_node_changed.connect(self.active_node_changed.emit)
        self.base_page.bind_tun_requested.connect(self.bind_tun_node)
        self.chain_page.bind_tun_requested.connect(self.bind_tun_node)

    def refresh(self) -> None:
        self.base_page.refresh()
        self.chain_page.refresh()

    def bind_tun_node(self, node_id: str) -> None:
        node = self.app_state.find_node_by_id(node_id)
        if node is None:
            return
        self.app_state.tun_node_id = node.node_id
        self.app_state.enable_tun = True
        self.refresh()
        self.data_changed.emit()
        self.runtime_config_changed.emit()

