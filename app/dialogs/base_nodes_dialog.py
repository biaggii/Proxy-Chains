"""Compact inventory for editing and removing imported base nodes."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.dialogs.node_edit_dialog import NodeEditDialog
from models.app_state import AppState


class BaseNodesDialog(QDialog):
    """Manage source nodes without adding another main-window tab."""

    data_changed = Signal()

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.setWindowTitle("Manage Base Nodes")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Protocol", "Server", "Port"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.currentCellChanged.connect(lambda *_: self._sync_actions())
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.edit_button = QPushButton("Edit")
        self.remove_button = QPushButton("Remove")
        self.edit_button.clicked.connect(self._edit)
        self.remove_button.clicked.connect(self._remove)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.nodes = list(self.app_state.nodes)
        self.table.setRowCount(len(self.nodes))
        for row, node in enumerate(self.nodes):
            for column, value in enumerate((node.name, node.node_type, node.server, str(node.port))):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self._sync_actions()

    def _sync_actions(self) -> None:
        selected = self.table.currentRow() >= 0
        self.edit_button.setEnabled(selected)
        self.remove_button.setEnabled(selected)

    def _selected_node(self):
        row = self.table.currentRow()
        return self.nodes[row] if 0 <= row < len(self.nodes) else None

    def _edit(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        dialog = NodeEditDialog(node, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            dialog.save_changes()
            self.refresh()
            self.data_changed.emit()

    def _remove(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        used_by = [
            chain.name for chain in self.app_state.chains
            if node.node_id in chain.hop_node_ids
        ]
        if used_by:
            QMessageBox.warning(
                self,
                "Node is in use",
                f"'{node.name}' is used by: {', '.join(used_by[:8])}. Edit those chains first.",
            )
            return
        self.app_state.nodes = [item for item in self.app_state.nodes if item.node_id != node.node_id]
        self.refresh()
        self.data_changed.emit()
