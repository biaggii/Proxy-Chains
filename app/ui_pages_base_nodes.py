"""v2rayN-style base-node list with one shared local proxy endpoint and TUN."""

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QTabBar,
    QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

from models.app_state import AppState
from models.node import Node


class BaseNodesPage(QWidget):
    data_changed = Signal()
    active_node_changed = Signal(str)
    runtime_config_changed = Signal()
    bind_tun_requested = Signal(str)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._visible_nodes: list[Node] = []
        self._subscription_workers = {}
        self._build_ui()
        self.refresh()
        self.auto_update_timer = QTimer(self)
        self.auto_update_timer.setInterval(30_000)
        self.auto_update_timer.timeout.connect(self._check_auto_updates)
        self.auto_update_timer.start()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        title = QLabel("Base Nodes")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        self.endpoint_label = QLabel("Active Base Node: None")
        self.endpoint_label.setObjectName("pageSubtitle")
        heading.addWidget(self.endpoint_label)
        heading.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter nodes by name, address or protocol…")
        self.search.textChanged.connect(self.refresh)
        self.search.setMinimumWidth(260)
        self.search.setMaximumWidth(620)
        heading.addWidget(self.search, 2)
        layout.addLayout(heading)

        self.group_tabs = QTabBar()
        self.group_tabs.setObjectName("baseSubscriptionTabs")
        self.group_tabs.setExpanding(False)
        self.group_tabs.setDrawBase(False)
        self.group_tabs.currentChanged.connect(self.refresh)
        self.group_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.group_tabs.customContextMenuRequested.connect(self._show_group_context_menu)
        self._group_keys: list[str] = ["ALL"]
        group_row = QHBoxLayout()
        group_row.addWidget(self.group_tabs, 1)
        self.btn_subscriptions = QPushButton("Subscriptions…")
        self.btn_subscriptions.setMinimumHeight(34)
        self.btn_subscriptions.clicked.connect(self._manage_subscriptions)
        group_row.addWidget(self.btn_subscriptions)
        layout.addLayout(group_row)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Type", "Remarks", "Address", "Port", "Transport", "TLS", "Subscription Group", "Delay (ms)", "Active", "TUN",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(lambda *_: self._edit_selected())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        for column, width in {0: 105, 3: 85, 4: 110, 5: 70, 7: 100, 8: 80, 9: 80}.items():
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)


    def refresh(self) -> None:
        selected_id = self.app_state.active_base_node_id
        current_group = self._group_keys[self.group_tabs.currentIndex()] if 0 <= self.group_tabs.currentIndex() < len(self._group_keys) else "ALL"
        ordered_subscriptions = sorted(self.app_state.subscriptions, key=lambda sub: (sub.sort, sub.name.casefold()))
        source_groups = [sub.name for sub in ordered_subscriptions]
        source_groups.extend(sorted({
            (node.source_sub or "Manual").strip() or "Manual" for node in self.app_state.nodes
        } - set(source_groups)))
        group_keys = ["ALL"]
        group_labels = ["ALL"]
        if any(self._is_custom_group(group) for group in source_groups):
            group_keys.append("CUSTOMS")
            group_labels.append("Customs")
        for group in source_groups:
            if self._is_custom_group(group):
                continue
            group_keys.append(group)
            group_labels.append(group)
        self.group_tabs.blockSignals(True)
        if group_keys != self._group_keys or [self.group_tabs.tabText(i) for i in range(self.group_tabs.count())] != group_labels:
            while self.group_tabs.count():
                self.group_tabs.removeTab(self.group_tabs.count() - 1)
            for label in group_labels:
                self.group_tabs.addTab(label)
            self._group_keys = group_keys
        target_index = self._group_keys.index(current_group) if current_group in self._group_keys else 0
        self.group_tabs.setCurrentIndex(target_index)
        self.group_tabs.blockSignals(False)

        query = self.search.text().strip().casefold()
        selected_group = self._group_keys[self.group_tabs.currentIndex()] if self._group_keys else "ALL"
        self._visible_nodes = [
            node for node in self.app_state.nodes
            if (
                selected_group == "ALL"
                or (selected_group == "CUSTOMS" and self._is_custom_group(node.source_sub or "Manual"))
                or (selected_group not in {"ALL", "CUSTOMS"} and (node.source_sub or "Manual") == selected_group)
            )
            and (not query or query in " ".join((node.name or "", node.server or "", node.node_type or "", node.source_sub or "")).casefold())
        ]

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for node in self._visible_nodes:
            row = self.table.rowCount()
            self.table.insertRow(row)
            delay = node.extra.get("delay_ms", node.extra.get("delay", "—"))
            values = [
                node.node_type.upper(),
                f"[STALE] {node.name}" if node.extra.get("subscription_stale") else node.name,
                node.server, str(node.port),
                node.network or "tcp", "TLS" if node.tls_enabled else "—",
                node.source_sub or "Manual", str(delay),
                "ACTIVE" if node.node_id == selected_id else "",
                "BOUND" if node.node_id == self.app_state.tun_node_id else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, node.node_id)
                if node.extra.get("subscription_stale"):
                    item.setToolTip("This profile disappeared from the latest subscription update but is retained because a Chain, Active Base, or TUN still references it.")
                self.table.setItem(row, column, item)
            if node.node_id == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)

        if not selected_id and self._visible_nodes:
            self.app_state.active_base_node_id = self._visible_nodes[0].node_id
            self.table.selectRow(0)
        self.endpoint_label.setText(
            f"Active Base Node: {self.app_state.get_active_base_node().name if self.app_state.get_active_base_node() else 'None'}"
        )

    @staticmethod
    def _is_custom_group(name: str) -> bool:
        value = (name or "Manual").strip().casefold()
        return value in {"manual", "custom", "customs"}

    def _selected_node(self) -> Node | None:
        row = self.table.currentRow()
        return self._visible_nodes[row] if 0 <= row < len(self._visible_nodes) else None

    def _on_selection_changed(self) -> None:
        node = self._selected_node()
        if node is None or node.node_id == self.app_state.active_base_node_id:
            return
        self.app_state.active_base_node_id = node.node_id
        self.refresh()
        self.data_changed.emit()
        self.active_node_changed.emit(node.node_id)

    def _show_context_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row >= 0:
            self.table.selectRow(row)
        menu = self._build_context_menu()
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        bind_action = QAction("Bind TUN to this node", menu)
        bind_action.setCheckable(True)
        node = self._selected_node()
        bind_action.setChecked(bool(node and node.node_id == self.app_state.tun_node_id))
        bind_action.triggered.connect(self._bind_tun_selected)
        menu.addAction(bind_action)
        for label, callback in (
            ("Use as active node", self._set_active),
            ("Edit", self._edit_selected),
            ("Remove", self._remove_selected),
            ("Add / Import…", self._show_add_menu),
        ):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        return menu

    def _show_group_context_menu(self, position) -> None:
        index = self.group_tabs.tabAt(position)
        if index >= 0:
            self.group_tabs.setCurrentIndex(index)
        menu = self._build_group_context_menu(index)
        menu.exec(self.group_tabs.mapToGlobal(position))

    def _build_group_context_menu(self, index: int) -> QMenu:
        menu = QMenu(self)
        if 0 < index < len(self._group_keys):
            edit = menu.addAction("Edit group…")
            edit.triggered.connect(self._edit_group)
            remove = menu.addAction("Remove group")
            remove.triggered.connect(self._remove_group)
        return menu

    def _current_group_name(self) -> str | None:
        index = self.group_tabs.currentIndex()
        if index <= 0 or index >= len(self._group_keys):
            return None
        key = self._group_keys[index]
        return "Customs" if key == "CUSTOMS" else key

    def _rename_group(self) -> None:
        old_name = self._current_group_name()
        if not old_name:
            return
        new_name, ok = QInputDialog.getText(self, "Rename group", "New group name:", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if any((node.source_sub or "Manual").casefold() == new_name.casefold() for node in self.app_state.nodes):
            QMessageBox.warning(self, "Group exists", "A group with that name already exists.")
            return
        old_values = (
            {node.source_sub or "Manual" for node in self.app_state.nodes if self._is_custom_group(node.source_sub or "Manual")}
            if old_name == "Customs" else {old_name}
        )
        for node in self.app_state.nodes:
            if (node.source_sub or "Manual") in old_values:
                node.source_sub = new_name
        for subscription in self.app_state.subscriptions:
            if subscription.name in old_values:
                subscription.name = new_name
        self.refresh()
        self.data_changed.emit()

    def _edit_group(self) -> None:
        group_name = self._current_group_name()
        subscription = next((sub for sub in self.app_state.subscriptions if sub.name == group_name), None)
        if subscription is None:
            self._rename_group()
            return
        from app.dialogs.subscription_edit_dialog import SubscriptionEditDialog

        old_name = subscription.name
        dialog = SubscriptionEditDialog(subscription, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        new_name = dialog.remarks.text().strip()
        if any(sub.sub_id != subscription.sub_id and sub.name.casefold() == new_name.casefold() for sub in self.app_state.subscriptions):
            QMessageBox.warning(self, "Duplicate group", "A subscription group with this name already exists.")
            return
        dialog.build_subscription()
        for node in self.app_state.nodes:
            if node.source_sub == old_name:
                node.source_sub = subscription.name
        self.refresh()
        self.data_changed.emit()
        self._request_subscription_update(subscription.sub_id)

    def _remove_group(self) -> None:
        group_name = self._current_group_name()
        if not group_name:
            return
        group_values = (
            {node.source_sub or "Manual" for node in self.app_state.nodes if self._is_custom_group(node.source_sub or "Manual")}
            if group_name == "Customs" else {group_name}
        )
        group_nodes = [node for node in self.app_state.nodes if (node.source_sub or "Manual") in group_values]
        node_ids = {node.node_id for node in group_nodes}
        used_by = [chain.name for chain in self.app_state.chains if node_ids.intersection(chain.hop_node_ids)]
        if used_by:
            QMessageBox.warning(self, "Group in use", f"Remove these nodes from chains first: {', '.join(used_by[:8])}")
            return
        if QMessageBox.question(self, "Remove group", f"Remove group '{group_name}', its subscription settings and {len(group_nodes)} node(s)?") != QMessageBox.StandardButton.Yes:
            return
        self.app_state.nodes = [node for node in self.app_state.nodes if node.node_id not in node_ids]
        self.app_state.subscriptions = [sub for sub in self.app_state.subscriptions if sub.name not in group_values]
        if self.app_state.active_base_node_id in node_ids:
            self.app_state.active_base_node_id = self.app_state.nodes[0].node_id if self.app_state.nodes else ""
        if self.app_state.tun_node_id in node_ids:
            self.app_state.tun_node_id = ""
            self.app_state.enable_tun = False
        self.refresh()
        self.data_changed.emit()
        self.active_node_changed.emit(self.app_state.active_base_node_id)

    def _bind_tun_selected(self) -> None:
        node = self._selected_node()
        if node:
            self.bind_tun_requested.emit(node.node_id)

    def _set_active(self) -> None:
        node = self._selected_node()
        if node and node.node_id != self.app_state.active_base_node_id:
            self.app_state.active_base_node_id = node.node_id
            self.refresh()
            self.data_changed.emit()
            self.active_node_changed.emit(node.node_id)

    def _show_add_menu(self) -> None:
        menu = QMenu(self)
        for label, callback in (
            ("Paste node URI…", self._import_uri),
            ("Create node manually…", self._create_manual_node),
        ):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.exec(self.table.viewport().mapToGlobal(self.table.viewport().rect().center()))

    def _manage_subscriptions(self) -> None:
        from app.dialogs.subscription_manager_dialog import SubscriptionManagerDialog

        dialog = SubscriptionManagerDialog(self.app_state, self)
        dialog.changed.connect(self._on_subscriptions_changed)
        dialog.update_requested.connect(self._request_subscription_update)
        self.data_changed.connect(dialog.refresh)
        dialog.exec()
        self.data_changed.disconnect(dialog.refresh)
        self.refresh()

    def _on_subscriptions_changed(self) -> None:
        self.refresh()
        self.data_changed.emit()
        self.runtime_config_changed.emit()

    def _request_subscription_update(self, sub_id: str) -> None:
        if sub_id in self._subscription_workers:
            return
        subscription = next((sub for sub in self.app_state.subscriptions if sub.sub_id == sub_id), None)
        if subscription is None or not subscription.url.strip():
            return
        from app.workers.subscription_update_worker import SubscriptionUpdateWorker

        worker = SubscriptionUpdateWorker(subscription, self)
        self._subscription_workers[sub_id] = worker
        worker.completed.connect(self._on_subscription_update_completed)
        worker.finished.connect(lambda sid=sub_id: self._subscription_workers.pop(sid, None))
        worker.start()

    @staticmethod
    def _node_identity(node: Node) -> tuple:
        return (
            node.node_type, node.server, node.port, node.uuid_str or "",
            node.username or "", node.encryption or "", node.path or "", node.network or "tcp",
        )

    def _on_subscription_update_completed(self, sub_id, new_nodes, errors, metadata) -> None:
        subscription = next((sub for sub in self.app_state.subscriptions if sub.sub_id == sub_id), None)
        if subscription is None:
            return
        if not new_nodes and errors:
            if metadata.get("last_update"):
                subscription.last_update = metadata["last_update"]
                self.data_changed.emit()
            if errors:
                QMessageBox.warning(self, f"Update failed: {subscription.name}", "\n".join(errors[:10]))
            return
        if not new_nodes and not metadata.get("last_update"):
            return

        old_nodes = [node for node in self.app_state.nodes if node.source_sub == subscription.name]
        reusable: dict[tuple, list[Node]] = {}
        reusable_by_name: dict[tuple, list[Node]] = {}
        for old in old_nodes:
            reusable.setdefault(self._node_identity(old), []).append(old)
            reusable_by_name.setdefault((old.node_type, old.name.casefold()), []).append(old)
        refreshed: list[Node] = []
        for node in new_nodes:
            candidates = reusable.get(self._node_identity(node), [])
            if candidates:
                reused = candidates.pop(0)
                node.node_id = reused.node_id
                named_candidates = reusable_by_name.get((node.node_type, node.name.casefold()), [])
                if reused in named_candidates:
                    named_candidates.remove(reused)
            else:
                named_candidates = reusable_by_name.get((node.node_type, node.name.casefold()), [])
                if named_candidates:
                    reused = named_candidates.pop(0)
                    node.node_id = reused.node_id
                    identity_candidates = reusable.get(self._node_identity(reused), [])
                    if reused in identity_candidates:
                        identity_candidates.remove(reused)
            node.source_sub = subscription.name
            node.extra.pop("subscription_stale", None)
            refreshed.append(node)

        retained_ids = {node.node_id for node in refreshed}
        referenced_ids = {node_id for chain in self.app_state.chains for node_id in chain.hop_node_ids}
        referenced_ids.update({self.app_state.active_base_node_id, self.app_state.tun_node_id})
        stale_nodes = [node for node in old_nodes if node.node_id not in retained_ids and node.node_id in referenced_ids]
        for node in stale_nodes:
            node.extra["subscription_stale"] = True
        old_ids = {node.node_id for node in old_nodes}
        self.app_state.nodes = [node for node in self.app_state.nodes if node.node_id not in old_ids]
        self.app_state.nodes.extend(stale_nodes)
        self.app_state.nodes.extend(refreshed)
        subscription.last_update = metadata.get("last_update")
        subscription.node_count = len(refreshed)
        self.refresh()
        self.data_changed.emit()
        self.runtime_config_changed.emit()
        if errors:
            self._show_import_result(len(refreshed), errors)

    def _check_auto_updates(self) -> None:
        now = datetime.now(timezone.utc)
        for subscription in self.app_state.subscriptions:
            if not subscription.enable_update or subscription.update_interval <= 0 or not subscription.url.strip():
                continue
            if subscription.sub_id in self._subscription_workers:
                continue
            if not subscription.last_update:
                self._request_subscription_update(subscription.sub_id)
                continue
            try:
                last = datetime.fromisoformat(subscription.last_update)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
            except ValueError:
                last = datetime.min.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() >= subscription.update_interval * 60:
                self._request_subscription_update(subscription.sub_id)

    def _import_uri(self) -> None:
        from parsers.subscription_fetcher import parse_text_only

        text, ok = QInputDialog.getMultiLineText(self, "Import nodes", "Paste one or more share URIs:")
        if not ok or not text.strip():
            return
        nodes, errors = parse_text_only(text, sub_name="Manual")
        self._append_nodes(nodes)
        self._show_import_result(len(nodes), errors)

    def _create_manual_node(self) -> None:
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
        self._append_nodes([node])

    def _append_nodes(self, nodes: list[Node]) -> None:
        known = {node.node_id for node in self.app_state.nodes}
        added = [node for node in nodes if node.node_id not in known]
        self.app_state.nodes.extend(added)
        active_changed = False
        if not self.app_state.active_base_node_id and added:
            self.app_state.active_base_node_id = added[0].node_id
            active_changed = True
        self.refresh()
        self.data_changed.emit()
        if active_changed:
            self.active_node_changed.emit(self.app_state.active_base_node_id)

    def _show_import_result(self, count: int, errors: list[str]) -> None:
        message = f"Imported {count} base node(s)."
        if errors:
            message += "\n\n" + "\n".join(errors[:8])
        QMessageBox.information(self, "Import complete", message)

    def closeEvent(self, event) -> None:
        self.shutdown_updates()
        super().closeEvent(event)

    def shutdown_updates(self) -> None:
        self.auto_update_timer.stop()
        for worker in list(self._subscription_workers.values()):
            if worker.isRunning():
                worker.wait(31_000)

    def _edit_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        from app.dialogs.node_edit_dialog import NodeEditDialog

        dialog = NodeEditDialog(node, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            dialog.save_changes()
            self.refresh()
            self.data_changed.emit()
            if node.node_id == self.app_state.active_base_node_id:
                self.active_node_changed.emit(node.node_id)
            elif any(node.node_id in chain.hop_node_ids for chain in self.app_state.chains):
                self.runtime_config_changed.emit()

    def _remove_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        used_by = [chain.name for chain in self.app_state.chains if node.node_id in chain.hop_node_ids]
        if used_by:
            QMessageBox.warning(self, "Node in use", f"Used by chain(s): {', '.join(used_by[:8])}")
            return
        if QMessageBox.question(self, "Remove node", f"Remove '{node.name}'?") != QMessageBox.StandardButton.Yes:
            return
        self.app_state.nodes = [item for item in self.app_state.nodes if item.node_id != node.node_id]
        if self.app_state.active_base_node_id == node.node_id:
            self.app_state.active_base_node_id = self.app_state.nodes[0].node_id if self.app_state.nodes else ""
        if self.app_state.tun_node_id == node.node_id:
            self.app_state.tun_node_id = ""
            self.app_state.enable_tun = False
        self.refresh()
        self.data_changed.emit()
        self.active_node_changed.emit(self.app_state.active_base_node_id)
