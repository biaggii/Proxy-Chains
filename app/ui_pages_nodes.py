"""
Nodes management page.

Responsibilities:
  - Display all nodes (table: name, type, server, port, source, latency)
  - Search / filter by name or type
  - Add nodes manually via URI or the full editor dialog
  - Delete selected nodes
  - Batch-create chains from selected nodes
  - Copy / paste node URIs
  - TCP latency testing
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QLabel, QMessageBox,
    QGroupBox, QMenu, QInputDialog,
    QDialog, QApplication,
)
from PySide6.QtCore import Signal, Qt
from models.node import Node, NODE_TYPE_CHAIN
from models.app_state import AppState
from app.dialogs.node_edit_dialog import NodeEditDialog
from app.workers.tcp_ping_worker import TcpPingWorker
from utils.pattern_rename import expand_pattern


class NodesPage(QWidget):
    """Node review, manual import, URI copy/paste, and chain helpers."""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", node_group: str = "all", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.node_group = node_group
        self._sort_col = -1
        self._sort_reverse = False
        self._filtered_nodes: list[Node] = []
        self._table_row_to_node: dict[int, Node] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # ── Search / filter ────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter name keywords...")
        self.search_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.search_input)

        filter_row.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "vmess", "vless", "trojan", "shadowsocks", "socks5", "http", "wireguard", "chain"])
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.type_filter)

        layout.addLayout(filter_row)

        # ── Manual add ─────────────────────────────────
        add_group = QGroupBox("Add Node Manually")
        add_row = QHBoxLayout()
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("Paste a share URI here, for example socks5://user:pass@1.2.3.4:1080#Office")
        add_row.addWidget(self.manual_input)

        btn_manual_add = QPushButton("Import URI")
        btn_manual_add.clicked.connect(self._on_manual_add)
        add_row.addWidget(btn_manual_add)

        btn_add_node = QPushButton("Create Node")
        btn_add_node.clicked.connect(self._on_add_new_node)
        add_row.addWidget(btn_add_node)

        if self.node_group == "chain":
            add_group.setTitle("Reusable Chain Nodes")
            self.manual_input.hide()
            btn_manual_add.hide()
            btn_add_node.hide()
            self.type_filter.blockSignals(True)
            self.type_filter.setCurrentText("chain")
            self.type_filter.blockSignals(False)
        elif self.node_group == "base":
            add_group.setTitle("Import Base Nodes")

        add_group.setLayout(add_row)
        layout.addWidget(add_group)

        # ── Node table ─────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Type", "Server", "Port", "Source", "Latency"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.itemSelectionChanged.connect(self._sync_action_buttons)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._on_edit_node)
        btn_row.addWidget(self.btn_edit)

        self.btn_copy = QPushButton("Copy URI")
        self.btn_copy.clicked.connect(self._on_copy_nodes)
        btn_row.addWidget(self.btn_copy)

        self.btn_paste = QPushButton("Import Clipboard")
        self.btn_paste.clicked.connect(self._on_paste_nodes)
        btn_row.addWidget(self.btn_paste)

        self.btn_ping = QPushButton("Test Latency")
        self.btn_ping.clicked.connect(self._on_test_tcping)
        btn_row.addWidget(self.btn_ping)

        self.btn_batch_chain = QPushButton("Create Chain(s)")
        self.btn_batch_chain.clicked.connect(self._on_batch_create_chain)
        btn_row.addWidget(self.btn_batch_chain)

        if self.node_group == "chain":
            for button in (self.btn_edit, self.btn_copy, self.btn_paste, self.btn_ping, self.btn_batch_chain):
                button.hide()

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(self.btn_delete)

        lbl_count = QLabel("")
        self._lbl_count = lbl_count
        btn_row.addStretch()
        btn_row.addWidget(lbl_count)

        layout.addLayout(btn_row)
        self._sync_action_buttons()

    # ── Sorting ───────────────────────────────────────

    def _on_header_clicked(self, logical_index: int) -> None:
        """Toggle sort order on header click."""
        if self._sort_col == logical_index:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = logical_index
            self._sort_reverse = False
        self.refresh()

    # ── Refresh ───────────────────────────────────────

    def refresh(self) -> None:
        """Reload the table with filtering and sorting applied."""
        keyword = self.search_input.text().strip().lower()
        type_filter = self.type_filter.currentText()

        filtered = [
            node
            for node in self.app_state.nodes
            if (not keyword or keyword in node.name.lower())
            and (type_filter == "All" or node.node_type == type_filter)
            and (
                self.node_group == "all"
                or (self.node_group == "chain" and node.node_type == NODE_TYPE_CHAIN)
                or (self.node_group == "base" and node.node_type != NODE_TYPE_CHAIN)
            )
        ]

        if self._sort_col != -1:
            if self._sort_col == 6:
                # Latency: push invalid values to the bottom
                valid = [n for n in filtered if getattr(n, "latency", None) is not None and getattr(n, "latency", None) >= 0]
                invalid = [n for n in filtered if getattr(n, "latency", None) is None or getattr(n, "latency", None) < 0]
                valid.sort(key=lambda n: getattr(n, "latency", 0), reverse=self._sort_reverse)
                filtered = valid + invalid
            else:
                key_map = {1: lambda n: n.name.lower(), 2: lambda n: n.node_type.lower()}
                sort_fn = key_map.get(self._sort_col, lambda n: n.name.lower())
                filtered.sort(key=sort_fn, reverse=self._sort_reverse)

        self.table.setRowCount(len(filtered))
        self._filtered_nodes = filtered
        self._table_row_to_node.clear()

        for row_idx, node in enumerate(filtered):
            self.table.setItem(row_idx, 0, QTableWidgetItem(node.node_id))
            self.table.setItem(row_idx, 1, QTableWidgetItem(node.name))
            self.table.setItem(row_idx, 2, QTableWidgetItem(node.node_type))
            self.table.setItem(row_idx, 3, QTableWidgetItem(node.server or "—"))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(node.port) if node.port else "—"))
            self.table.setItem(row_idx, 5, QTableWidgetItem(node.source_sub or "Manual"))

            lat = getattr(node, "latency", None)
            if lat is not None and lat >= 0:
                delay_str = f"{lat} ms"
            elif lat == -1:
                delay_str = "Timeout"
            elif lat == -2:
                delay_str = "Testing..."
            else:
                delay_str = "-"
            self.table.setItem(row_idx, 6, QTableWidgetItem(delay_str))

            self._table_row_to_node[row_idx] = node

        self._lbl_count.setText(
            f"Showing {len(filtered)} / Total {len(self.app_state.nodes)} nodes"
        )
        group_count = len(filtered)
        if self.node_group == "base":
            summary = f"{group_count} base node(s). Import v2rayN or Clash subscriptions, paste share links, or add nodes manually."
        elif self.node_group == "chain":
            summary = f"{group_count} reusable chain node(s). Select these as hops when composing another chain."
        else:
            summary = f"{len(self.app_state.nodes)} node(s) available. Review, test, copy, and compose nodes into chains."
        self.summary_label.setText(summary)
        self._sync_action_buttons()

    def _on_filter_changed(self) -> None:
        self.refresh()

    def _sync_action_buttons(self) -> None:
        has_selection = bool(self.table.selectedIndexes())
        self.btn_edit.setEnabled(has_selection)
        self.btn_copy.setEnabled(has_selection)
        self.btn_ping.setEnabled(has_selection)
        self.btn_batch_chain.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        if self.node_group == "chain":
            for button in (self.btn_edit, self.btn_copy, self.btn_ping, self.btn_batch_chain):
                button.setEnabled(False)

    # ── Add ───────────────────────────────────────────

    def _on_manual_add(self) -> None:
        """Import a single node from a URI string."""
        uri_text = self.manual_input.text().strip()
        if not uri_text:
            QMessageBox.warning(self, "Notice", "Please enter node URI")
            return

        from parsers.uri_parsers import parse_single_uri
        try:
            node = parse_single_uri(uri_text, source_sub="Manual Insert")
            self.app_state.nodes.append(node)
            self.manual_input.clear()
            self.refresh()
            self.data_changed.emit()
            QMessageBox.information(self, "Success", f"Node added: {node.name}")
        except ValueError as err:
            QMessageBox.warning(self, "Parse Failed", str(err))

    def _on_add_new_node(self) -> None:
        """Open a blank editor dialog to create new nodes."""
        blank_node = Node(
            name="New Node",
            node_type="socks5",
            server="",
            port=1080,
        )
        dialog = NodeEditDialog(blank_node, self)
        dialog.setWindowTitle("Add New Node")
        result = dialog.exec()

        total_added = 0
        for n in dialog.added_nodes:
            n.source_sub = "Manual Add"
            self.app_state.nodes.append(n)
            total_added += 1

        if result == QDialog.DialogCode.Accepted:
            dialog.save_changes()
            if blank_node.server:
                blank_node.source_sub = "Manual Add"
                self.app_state.nodes.append(blank_node)
                total_added += 1

        if total_added > 0:
            self.refresh()
            self.data_changed.emit()
            QMessageBox.information(self, "Done", f"Total {total_added} node(s) added!")

    # ── Delete ────────────────────────────────────────

    def _on_delete_selected(self) -> None:
        """Remove selected nodes from the workspace."""
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes()),
            reverse=True,
        )
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select a node to delete")
            return

        for row in selected_rows:
            node = self._table_row_to_node.get(row)
            if node:
                dependents = [
                    item.name
                    for item in self.app_state.nodes
                    if item.node_type == NODE_TYPE_CHAIN
                    and node.node_id in item.extra.get("chain_hop_node_ids", [])
                ]
                if dependents:
                    QMessageBox.warning(
                        self,
                        "Node In Use",
                        f"Cannot delete '{node.name}' because chain node(s) depend on it: "
                        + ", ".join(dependents[:5]),
                    )
                    continue
                self.app_state.nodes = [
                    n for n in self.app_state.nodes if n.node_id != node.node_id
                ]

        self.refresh()
        self.data_changed.emit()

    # ── Batch chain creation ──────────────────────────

    def _on_batch_create_chain(self) -> None:
        """Create a single-hop chain for each selected node."""
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes())
        )
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select node(s) to create chain for")
            return

        text, ok = QInputDialog.getText(
            self,
            "Batch Create Chain",
            "Pattern (e.g. US{1-8}, or leave blank for node names):",
        )

        if not ok:
            return

        pattern_text = text.strip()
        from models.chain import Chain

        created_count = 0
        for i, row in enumerate(selected_rows):
            node = self._table_row_to_node.get(row)
            if node:
                if pattern_text:
                    chain_name = expand_pattern(pattern_text, i, len(selected_rows))
                else:
                    chain_name = node.name

                new_chain = Chain(name=chain_name)
                new_chain.hop_node_ids.append(node.node_id)
                self.app_state.chains.append(new_chain)
                created_count += 1

        self.data_changed.emit()
        QMessageBox.information(
            self,
            "Success",
            f"Successfully created {created_count} chains!\n\nYou can now go to Ports to bind them.",
        )

    # ── Context menu ──────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        """Right-click context menu."""
        menu = QMenu(self)
        action_edit = menu.addAction("Edit Node")
        action_copy = menu.addAction("Copy Node URI")
        action_paste = menu.addAction("Paste Node(s) from Clipboard")
        menu.addSeparator()
        action_select_all = menu.addAction("Select All")
        action_ping = menu.addAction("Test TCP Latency")
        menu.addSeparator()
        action_batch_chain = menu.addAction("Batch Create Chains from Selection")
        menu.addSeparator()
        action_del = menu.addAction("Remove Selected Nodes")

        action = menu.exec(self.table.mapToGlobal(pos))
        if action == action_edit:
            self._on_edit_node()
        elif action == action_copy:
            self._on_copy_nodes()
        elif action == action_paste:
            self._on_paste_nodes()
        elif action == action_select_all:
            self.table.selectAll()
        elif action == action_ping:
            self._on_test_tcping()
        elif action == action_batch_chain:
            self._on_batch_create_chain()
        elif action == action_del:
            self._on_delete_selected()

    # ── Edit ──────────────────────────────────────────

    def _on_edit_node(self) -> None:
        """Open the editor dialog for the first selected node."""
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes())
        )
        if not selected_rows:
            return

        row = selected_rows[0]
        node = self._table_row_to_node.get(row)
        if node:
            dialog = NodeEditDialog(node, self)
            result = dialog.exec()

            added_count = 0
            for n in dialog.added_nodes:
                n.source_sub = node.source_sub or "Manual Add"
                self.app_state.nodes.append(n)
                added_count += 1

            if result == QDialog.DialogCode.Accepted:
                dialog.save_changes()

            if added_count > 0 or result == QDialog.DialogCode.Accepted:
                self.refresh()
                self.data_changed.emit()
            if added_count > 0:
                QMessageBox.information(self, "Done", f"{added_count} new node(s) added via Add button!")

    # ── Copy / Paste ──────────────────────────────────

    def _on_copy_nodes(self) -> None:
        """Copy selected nodes as valid share URIs."""
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes())
        )
        if not selected_rows:
            return

        from parsers.uri_parsers import build_node_uri

        uris: list[str] = []
        copy_errors: list[str] = []
        for row in selected_rows:
            node = self._table_row_to_node.get(row)
            if node:
                try:
                    uris.append(build_node_uri(node))
                except ValueError as err:
                    copy_errors.append(f"{node.name}: {err}")

        if not uris:
            detail = "\n".join(copy_errors[:5])
            if len(copy_errors) > 5:
                detail += f"\n...and {len(copy_errors) - 5} more."
            message = "None of the selected nodes could be exported as share URIs."
            if detail:
                message += f"\n\n{detail}"
            QMessageBox.warning(self, "Copy Failed", message)
            return

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(uris))
        message = f"Copied {len(uris)} URI(s) to clipboard."
        if copy_errors:
            detail = "\n".join(copy_errors[:5])
            if len(copy_errors) > 5:
                detail += f"\n...and {len(copy_errors) - 5} more."
            message += f"\n\nSkipped {len(copy_errors)} node(s) that could not be exported:\n{detail}"
        QMessageBox.information(self, "Success", message)

    def _on_paste_nodes(self) -> None:
        """Parse clipboard content and import all valid nodes."""
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            QMessageBox.warning(self, "Notice", "Clipboard is empty!")
            return

        from parsers.subscription_fetcher import parse_text_only

        nodes, errors = parse_text_only(text, sub_name="Pasted")
        for node in nodes:
            self.app_state.nodes.append(node)

        if nodes:
            self.refresh()
            self.data_changed.emit()
            message = f"Successfully imported {len(nodes)} node(s) from clipboard."
            if errors:
                detail = "\n".join(errors[:5])
                if len(errors) > 5:
                    detail += f"\n...and {len(errors) - 5} more."
                message += f"\n\nSkipped {len(errors)} invalid item(s):\n{detail}"
            QMessageBox.information(self, "Success", message)
        else:
            detail = "\n".join(errors[:5]) if errors else ""
            if len(errors) > 5:
                detail += f"\n...and {len(errors) - 5} more."
            message = "No valid nodes were found in the clipboard."
            if detail:
                message += f"\n\n{detail}"
            QMessageBox.warning(self, "Import Failed", message)

    # ── Latency testing ───────────────────────────────

    def _on_test_tcping(self) -> None:
        """TCP latency test for selected nodes (multi-threaded)."""
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes())
        )
        if not selected_rows:
            return

        nodes_to_ping = []
        for row in selected_rows:
            node = self._table_row_to_node.get(row)
            if node:
                node.latency = -2
                nodes_to_ping.append((node.node_id, node.server, node.port))
                self.table.setItem(row, 6, QTableWidgetItem("Testing..."))

        self.ping_worker = TcpPingWorker(nodes_to_ping)
        self.ping_worker.progress.connect(self._on_ping_progress)
        self.ping_worker.finished_ping.connect(self._on_ping_finished)
        self.ping_worker.start()

    def _on_ping_progress(self, node_id: str, latency: int) -> None:
        target_node = None
        for n in self.app_state.nodes:
            if n.node_id == node_id:
                target_node = n
                break

        if target_node:
            target_node.latency = latency

        for row, node in self._table_row_to_node.items():
            if node.node_id == node_id:
                text = f"{latency} ms" if latency >= 0 else "Timeout"
                self.table.setItem(row, 6, QTableWidgetItem(text))
                break

    def _on_ping_finished(self) -> None:
        self.ping_worker.deleteLater()
        self.ping_worker = None
