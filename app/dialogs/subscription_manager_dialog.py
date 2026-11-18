"""v2rayN-style subscription group manager."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from app.dialogs.subscription_edit_dialog import SubscriptionEditDialog
from models.app_state import AppState


class SubscriptionManagerDialog(QDialog):
    changed = Signal()
    update_requested = Signal(str)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.setWindowTitle("Subscription Group Settings")
        self.resize(1040, 650)
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_delete = QPushButton("Delete")
        self.btn_edit = QPushButton("Edit")
        self.btn_share = QPushButton("Share")
        self.btn_update = QPushButton("Update")
        self.btn_update_all = QPushButton("Update All")
        self.btn_close = QPushButton("Close")
        for button, callback in (
            (self.btn_add, self._add),
            (self.btn_delete, self._delete),
            (self.btn_edit, self._edit),
            (self.btn_share, self._share),
            (self.btn_update, self._update_selected),
            (self.btn_update_all, self._update_all),
            (self.btn_close, self.accept),
        ):
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Remarks", "URL", "Enable update", "Automatic update (min)", "User Agent", "Sort", "Nodes",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda *_: self._edit())
        self.table.horizontalHeader().setStretchLastSection(False)
        for column, width in {0: 170, 1: 360, 2: 105, 3: 175, 4: 190, 5: 65, 6: 75}.items():
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self._selected_id()
        self.app_state.subscriptions.sort(key=lambda sub: (sub.sort, sub.name.casefold()))
        self.table.setRowCount(0)
        for sub in self.app_state.subscriptions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            node_count = sum(1 for node in self.app_state.nodes if node.source_sub == sub.name)
            values = [
                sub.name, sub.url, "On" if sub.enable_update else "Off",
                str(sub.update_interval), sub.user_agent, str(sub.sort), str(node_count),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, sub.sub_id)
                self.table.setItem(row, column, item)
            if sub.sub_id == selected_id:
                self.table.selectRow(row)
        if self.table.currentRow() < 0 and self.table.rowCount():
            self.table.selectRow(0)
        selected = self._selected_subscription() is not None
        self.btn_delete.setEnabled(selected)
        self.btn_edit.setEnabled(selected)
        self.btn_share.setEnabled(selected)
        selected_sub = self._selected_subscription()
        self.btn_update.setEnabled(bool(selected_sub and selected_sub.url.strip()))
        self.btn_share.setEnabled(bool(selected_sub and selected_sub.url.strip()))

    def _selected_id(self) -> str:
        item = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def _selected_subscription(self):
        sub_id = self._selected_id()
        return next((sub for sub in self.app_state.subscriptions if sub.sub_id == sub_id), None)

    def _add(self) -> None:
        dialog = SubscriptionEditDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        subscription = dialog.build_subscription()
        if any(sub.name.casefold() == subscription.name.casefold() for sub in self.app_state.subscriptions):
            QMessageBox.warning(self, "Duplicate group", "A subscription group with this name already exists.")
            return
        self.app_state.subscriptions.append(subscription)
        self.changed.emit()
        self.refresh()
        if subscription.url.strip():
            self.update_requested.emit(subscription.sub_id)

    def _edit(self) -> None:
        subscription = self._selected_subscription()
        if subscription is None:
            return
        old_name = subscription.name
        dialog = SubscriptionEditDialog(subscription, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dialog.remarks.text().strip()
        if any(sub.sub_id != subscription.sub_id and sub.name.casefold() == new_name.casefold() for sub in self.app_state.subscriptions):
            QMessageBox.warning(self, "Duplicate group", "A subscription group with this name already exists.")
            return
        dialog.build_subscription()
        for node in self.app_state.nodes:
            if node.source_sub == old_name:
                node.source_sub = subscription.name
        self.changed.emit()
        self.refresh()
        if subscription.url.strip():
            self.update_requested.emit(subscription.sub_id)

    def _delete(self) -> None:
        subscription = self._selected_subscription()
        if subscription is None:
            return
        old_nodes = [node for node in self.app_state.nodes if node.source_sub == subscription.name]
        node_ids = {node.node_id for node in old_nodes}
        used_by = [chain.name for chain in self.app_state.chains if node_ids.intersection(chain.hop_node_ids)]
        if used_by:
            QMessageBox.warning(self, "Subscription in use", f"Remove its nodes from these chains first: {', '.join(used_by[:8])}")
            return
        if QMessageBox.question(self, "Delete subscription", f"Delete '{subscription.name}' and its {len(old_nodes)} node(s)?") != QMessageBox.StandardButton.Yes:
            return
        self.app_state.nodes = [node for node in self.app_state.nodes if node.node_id not in node_ids]
        self.app_state.subscriptions = [sub for sub in self.app_state.subscriptions if sub.sub_id != subscription.sub_id]
        if self.app_state.active_base_node_id in node_ids:
            self.app_state.active_base_node_id = self.app_state.nodes[0].node_id if self.app_state.nodes else ""
        if self.app_state.tun_node_id in node_ids:
            self.app_state.tun_node_id = ""
            self.app_state.enable_tun = False
        if self.app_state.enable_tun and not self.app_state.get_tun_chain():
            self.app_state.enable_tun = False
        self.changed.emit()
        self.refresh()

    def _share(self) -> None:
        subscription = self._selected_subscription()
        if subscription and subscription.url.strip():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(subscription.url)
            QMessageBox.information(self, "Share", "Subscription URL copied to clipboard.")

    def _update_selected(self) -> None:
        subscription = self._selected_subscription()
        if subscription:
            self.update_requested.emit(subscription.sub_id)

    def _update_all(self) -> None:
        for subscription in self.app_state.subscriptions:
            if subscription.url.strip():
                self.update_requested.emit(subscription.sub_id)

    def _context_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row >= 0:
            self.table.selectRow(row)
        menu = QMenu(self)
        for label, callback in (
            ("Update", self._update_selected),
            ("Edit", self._edit),
            ("Delete", self._delete),
            ("Share URL", self._share),
        ):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.exec(self.table.viewport().mapToGlobal(position))
