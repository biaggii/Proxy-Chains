"""Single chain-node workspace: create, add, edit, remove, and select TUN route."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.dialogs.chain_editor_dialog import ChainEditorDialog
from models.app_state import AppState
from models.chain import Chain
from models.port_mapping import PortMapping


class ChainsPage(QWidget):
    """The only route list. Each row is a reusable chain node."""

    data_changed = Signal()
    runtime_config_changed = Signal()
    bind_tun_requested = Signal(str)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._row_chains: list[Chain] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        heading = QHBoxLayout()
        title = QLabel("Chain Nodes")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        heading.addStretch()
        layout.addLayout(heading)

        summary_row = QHBoxLayout()
        self.summary = QLabel("Create a chain from your imported base nodes.")
        self.summary.setObjectName("pageSubtitle")
        summary_row.addWidget(self.summary)
        summary_row.addStretch()
        self.btn_create = QPushButton("Create")
        self.btn_create.setMinimumSize(104, 40)
        self.btn_create.clicked.connect(self._create_chain)
        summary_row.addWidget(self.btn_create)
        layout.addLayout(summary_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Route", "Local Port", "Hops", "TUN Node"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(lambda *_: self._edit_selected())
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 180)
        layout.addWidget(self.table, 1)


    def refresh(self) -> None:
        selected = self._selected_chain()
        selected_id = selected.chain_id if selected else ""
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._row_chains = list(self.app_state.chains)
        for chain in self._row_chains:
            mapping = next(
                (item for item in self.app_state.port_mappings if item.chain_id == chain.chain_id),
                None,
            )
            if mapping is None:
                mapping = self._create_mapping(chain.chain_id)
            hops = self.app_state.get_nodes_for_chain(chain)
            route = " → ".join(node.name for node in hops) if hops else "Invalid route"
            tun_node = self.app_state.get_tun_node()
            bound_node_name = tun_node.name if tun_node and tun_node.node_id in chain.hop_node_ids else ""
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [chain.name, route, f"127.0.0.1:{mapping.listen_port}", str(len(hops)), bound_node_name]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, chain.chain_id)
                self.table.setItem(row, column, item)
            if not hops:
                self.table.item(row, 1).setToolTip("This chain contains a missing or invalid node reference.")

        if selected_id:
            for row, chain in enumerate(self._row_chains):
                if chain.chain_id == selected_id:
                    self.table.selectRow(row)
                    break
        self.table.blockSignals(False)
        self.summary.setText(
            f"{len(self.app_state.chains)} chain node(s) · "
            f"{len(self.app_state.nodes)} base node(s) · "
            f"{sum(1 for item in self.app_state.port_mappings if item.chain_id in {c.chain_id for c in self.app_state.chains})} local chain ports"
        )
        self._sync_actions()

    def _create_mapping(self, chain_id: str) -> PortMapping:
        used = {self.app_state.base_node_listen_port}
        used.update(item.listen_port for item in self.app_state.port_mappings)
        port = 20001
        while port in used:
            port += 1
        mapping = PortMapping(listen_port=port, chain_id=chain_id)
        self.app_state.port_mappings.append(mapping)
        return mapping

    def _selected_chain(self) -> Chain | None:
        row = self.table.currentRow()
        return self._row_chains[row] if 0 <= row < len(self._row_chains) else None

    def _sync_actions(self) -> None:
        self._row_chains = list(self.app_state.chains)

    def _on_selection_changed(self) -> None:
        self._sync_actions()

    def _create_chain(self) -> None:
        dialog = ChainEditorDialog(self.app_state, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        name, hop_ids = dialog.result_values()
        chain = Chain(name=name, hop_node_ids=hop_ids)
        self.app_state.chains.append(chain)
        self._create_mapping(chain.chain_id)
        self.refresh()
        self.table.selectRow(len(self.app_state.chains) - 1)
        self.data_changed.emit()
        self.runtime_config_changed.emit()

    def _edit_selected(self) -> None:
        chain = self._selected_chain()
        if chain is None:
            return
        dialog = ChainEditorDialog(self.app_state, chain=chain, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        chain.name, chain.hop_node_ids = dialog.result_values()
        self.refresh()
        self.data_changed.emit()
        self.runtime_config_changed.emit()

    def _remove_selected(self) -> None:
        chain = self._selected_chain()
        if chain is None:
            return
        reply = QMessageBox.question(
            self, "Remove chain", f"Remove '{chain.name}' and its local port binding?"
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.app_state.chains = [item for item in self.app_state.chains if item.chain_id != chain.chain_id]
        self.app_state.port_mappings = [
            item for item in self.app_state.port_mappings if item.chain_id != chain.chain_id
        ]
        self.refresh()
        self.data_changed.emit()
        self.runtime_config_changed.emit()

    def _show_context_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row >= 0:
            self.table.selectRow(row)
        menu = self._build_context_menu()
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        chain = self._selected_chain()
        if chain:
            edit_action = menu.addAction("Edit")
            edit_action.triggered.connect(self._edit_selected)
            remove_action = menu.addAction("Remove")
            remove_action.triggered.connect(self._remove_selected)
            menu.addSeparator()
            hops_menu = menu.addMenu("Bind TUN to hop")
            for node in self.app_state.get_nodes_for_chain(chain):
                action = QAction(node.name, hops_menu)
                action.setCheckable(True)
                action.setChecked(node.node_id == self.app_state.tun_node_id)
                action.triggered.connect(
                    lambda checked=False, node_id=node.node_id: self.bind_tun_requested.emit(node_id)
                )
                hops_menu.addAction(action)
        return menu
