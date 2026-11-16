"""Single chain-node workspace: create, add, edit, remove, and select TUN route."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
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
from models.node import Node
from models.port_mapping import PortMapping


class ChainsPage(QWidget):
    """The only route list. Each row is a reusable chain node."""

    data_changed = Signal()

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
        self.tun_switch = QCheckBox("Use selected chain for system traffic (TUN)")
        self.tun_switch.setObjectName("tunSwitch")
        self.tun_switch.toggled.connect(self._on_tun_toggled)
        heading.addWidget(self.tun_switch)
        layout.addLayout(heading)

        self.summary = QLabel("Create a chain from your imported base nodes.")
        self.summary.setObjectName("pageSubtitle")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Route", "Local Port", "Hops"])
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
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.btn_create = QPushButton("Create")
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_remove = QPushButton("Remove")
        for button, callback in (
            (self.btn_create, self._create_chain),
            (self.btn_add, self._show_add_menu),
            (self.btn_edit, self._edit_selected),
            (self.btn_remove, self._remove_selected),
        ):
            button.setMinimumHeight(42)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self._sync_actions()

    def refresh(self) -> None:
        selected = self._selected_chain()
        selected_id = selected.chain_id if selected else ""
        if not selected_id and self.app_state.enable_tun:
            selected_id = self.app_state.tun_chain_id
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
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [chain.name, route, f"127.0.0.1:{mapping.listen_port}", str(len(hops))]
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
        self.tun_switch.blockSignals(True)
        self.tun_switch.setChecked(self.app_state.enable_tun)
        self.tun_switch.blockSignals(False)
        self.table.blockSignals(False)
        self.summary.setText(
            f"{len(self.app_state.chains)} chain node(s) · "
            f"{len(self.app_state.nodes)} base node(s) · "
            f"TUN {'On' if self.app_state.enable_tun else 'Off'}"
        )
        self._sync_actions()

    def _create_mapping(self, chain_id: str) -> PortMapping:
        used = {item.listen_port for item in self.app_state.port_mappings}
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
        selected = self._selected_chain() is not None
        self.btn_edit.setEnabled(selected)
        self.btn_remove.setEnabled(selected)
        self._row_chains = list(self.app_state.chains)

    def _on_selection_changed(self) -> None:
        chain = self._selected_chain()
        if self.app_state.enable_tun and chain:
            self.app_state.tun_chain_id = chain.chain_id
            self.data_changed.emit()
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
        if self.app_state.tun_chain_id == chain.chain_id:
            self.app_state.tun_chain_id = ""
            self.app_state.enable_tun = False
        self.refresh()
        self.data_changed.emit()

    def _show_context_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row >= 0:
            self.table.selectRow(row)
        menu = QMenu(self)
        for label, callback in (
            ("Create", self._create_chain),
            ("Add base node / subscription", self._show_add_menu),
            ("Edit", self._edit_selected),
            ("Remove", self._remove_selected),
        ):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _show_add_menu(self) -> None:
        menu = QMenu(self)
        actions = [
            ("Import subscription…", self._import_subscription),
            ("Paste node URI…", self._import_uri),
            ("Create base node…", self._create_base_node),
            ("Manage base nodes…", self._manage_base_nodes),
        ]
        for label, callback in actions:
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.exec(self.btn_add.mapToGlobal(self.btn_add.rect().bottomLeft()))

    def _create_base_node(self) -> None:
        from app.dialogs.node_edit_dialog import NodeEditDialog

        node = Node("New Node", "socks5", "", 1080)
        dialog = NodeEditDialog(node, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        dialog.save_changes()
        if not node.server or not 1 <= node.port <= 65535:
            QMessageBox.warning(self, "Invalid node", "Enter a valid server address and port.")
            return
        node.source_sub = "Manual"
        self._append_imported_nodes([node])

    def _import_uri(self) -> None:
        text, accepted = QInputDialog.getMultiLineText(self, "Import node", "Paste one share URI:")
        if not accepted or not text.strip():
            return
        from parsers.subscription_fetcher import parse_text_only

        nodes, errors = parse_text_only(text, sub_name="Manual")
        self._append_imported_nodes(nodes)
        self._show_import_result(len(nodes), errors)

    def _import_subscription(self) -> None:
        from models.subscription import Subscription
        from parsers.subscription_fetcher import fetch_and_parse

        name, accepted = QInputDialog.getText(self, "Import subscription", "Subscription name:")
        if not accepted or not name.strip():
            return
        url, accepted = QInputDialog.getText(self, "Import subscription", "Subscription URL:")
        if not accepted or not url.strip():
            return
        kind, accepted = QInputDialog.getItem(
            self, "Subscription format", "Format:", ["auto", "v2rayn", "clash"], 0, False
        )
        if not accepted:
            return
        subscription = Subscription(name=name.strip(), url=url.strip(), sub_type=kind)
        nodes, errors = fetch_and_parse(subscription)
        if nodes:
            self.app_state.subscriptions.append(subscription)
            self._append_imported_nodes(nodes)
        self._show_import_result(len(nodes), errors)

    def _append_imported_nodes(self, nodes) -> None:
        existing = {node.node_id for node in self.app_state.nodes}
        self.app_state.nodes.extend(node for node in nodes if node.node_id not in existing)
        self.data_changed.emit()

    def _show_import_result(self, count: int, errors: list[str]) -> None:
        message = f"Imported {count} base node(s)."
        if errors:
            message += "\n\n" + "\n".join(errors[:8])
        QMessageBox.information(self, "Import complete", message)

    def _manage_base_nodes(self) -> None:
        from app.dialogs.base_nodes_dialog import BaseNodesDialog

        dialog = BaseNodesDialog(self.app_state, self)
        dialog.data_changed.connect(self.data_changed.emit)
        dialog.exec()

    def _on_tun_toggled(self, checked: bool) -> None:
        chain = self._selected_chain()
        if checked and chain is None:
            QMessageBox.warning(self, "Select a chain", "Select a chain node first. TUN will use that route.")
            self.tun_switch.blockSignals(True)
            self.tun_switch.setChecked(False)
            self.tun_switch.blockSignals(False)
            return
        self.app_state.enable_tun = checked
        self.app_state.tun_chain_id = chain.chain_id if checked and chain else ""
        self.refresh()
        self.data_changed.emit()
