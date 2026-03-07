"""
ui_pages_nodes.py — 節點管理頁面

功能：
  - 顯示所有節點（表格：名稱、類型、伺服器、端口、來源）
  - 搜尋/篩選（按名稱或類型）
  - 手動新增 socks5 節點（socks5://user:pass@host:port）
  - 刪除選中節點
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QLabel, QMessageBox,
    QGroupBox, QFormLayout, QMenu, QInputDialog,
    QDialog, QDialogButtonBox, QApplication,
    QScrollArea, QCheckBox
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QClipboard
import socket
import time
import re
from typing import Callable
from models.node import Node
from models.app_state import AppState

class NodeEditDialog(QDialog):
    def __init__(self, node: Node, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Node: {node.name}")
        self.resize(500, 600)
        self.node = node
        
        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        layout = QFormLayout(form_widget)
        self.form_layout = layout

        # ---------------- Basic ----------------
        self.input_name = QLineEdit(node.name)
        self.combo_type = QComboBox()
        self.combo_type.addItems(["vmess", "vless", "trojan", "shadowsocks", "wireguard", "socks5", "http"])
        self.combo_type.setCurrentText(node.node_type)
        self.combo_type.currentTextChanged.connect(self._on_type_changed)
        
        self.input_server = QLineEdit(node.server)
        self.input_port = QLineEdit(str(node.port))
        
        layout.addRow("Alias:", self.input_name)
        layout.addRow("Type:", self.combo_type)
        layout.addRow("Address:", self.input_server)
        layout.addRow("Port:", self.input_port)
        
        # ---------------- Auth/UUID ----------------
        self.input_uuid = QLineEdit(node.uuid_str or "")
        self.input_password = QLineEdit(node.password or "")
        self.input_username = QLineEdit(node.username or "")
        self.input_alter_id = QLineEdit(str(node.alter_id) if hasattr(node, 'alter_id') else "0")
        self.input_encryption = QLineEdit(node.encryption or "")
        
        layout.addRow("UUID / ID:", self.input_uuid)
        layout.addRow("Encryption:", self.input_encryption)
        layout.addRow("Username:", self.input_username)
        layout.addRow("Password:", self.input_password)
        layout.addRow("Alter ID:", self.input_alter_id)
        
        # ---------------- Transport ----------------
        self.combo_network = QComboBox()
        self.combo_network.addItems(["tcp", "ws", "grpc", "h2"])
        self.combo_network.setCurrentText(node.network if node.network else "tcp")
        
        self.input_host = QLineEdit(node.host or "")
        self.input_path = QLineEdit(node.path or "")
        
        layout.addRow("Network:", self.combo_network)
        layout.addRow("Host:", self.input_host)
        layout.addRow("Path:", self.input_path)

        # ---------------- TLS ----------------
        self.chk_tls = QCheckBox("Enable TLS")
        self.chk_tls.setChecked(node.tls_enabled)
        self.input_sni = QLineEdit(node.sni or "")
        self.input_alpn = QLineEdit(",".join(node.alpn) if node.alpn else "")
        self.input_flow = QLineEdit(node.flow or "")
        
        layout.addRow("TLS / Reality:", self.chk_tls)
        layout.addRow("SNI:", self.input_sni)
        layout.addRow("ALPN (comma separated):", self.input_alpn)
        layout.addRow("Flow (VLESS):", self.input_flow)
        
        # ---------------- WireGuard ----------------
        self.input_wg_pub = QLineEdit(node.wg_public_key or "")
        self.input_wg_priv = QLineEdit(node.wg_private_key or "")
        self.input_wg_local = QLineEdit(node.wg_local_address or "")
        
        layout.addRow("WG Public Key:", self.input_wg_pub)
        layout.addRow("WG Private Key:", self.input_wg_priv)
        layout.addRow("WG Local Address:", self.input_wg_local)

        scroll.setWidget(form_widget)
        main_layout.addWidget(scroll)

        # Buttons: Add (keep open) + OK (close) + Cancel
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("➕ Add")
        self.btn_add.setToolTip("Add this node and keep the dialog open for the next one")
        self.btn_add.clicked.connect(self._on_add_clicked)
        btn_row.addWidget(self.btn_add)
        btn_row.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        btn_row.addWidget(self.buttons)
        main_layout.addLayout(btn_row)

        # Track nodes added via the Add button
        self.added_nodes: list[Node] = []

        # Init field visibility
        self._on_type_changed(self.combo_type.currentText())

    def _on_add_clicked(self):
        """Add button: save current fields as a new node, keep dialog open."""
        server = self.input_server.text().strip()
        if not server:
            QMessageBox.warning(self, "Error", "Server address cannot be empty!")
            return
        new_node = Node(
            name=self.input_name.text().strip() or "New Node",
            node_type=self.combo_type.currentText(),
            server=server,
            port=int(self.input_port.text().strip() or "0"),
        )
        # Temporarily point self.node to new_node so save_changes populates it
        orig_node = self.node
        self.node = new_node
        self.save_changes()
        self.node = orig_node
        self.added_nodes.append(new_node)
        QMessageBox.information(self, "Added", f"Node '{new_node.name}' added! You can modify fields and click Add again.")

    def _set_row_visible(self, widget, visible: bool):
        widget.setVisible(visible)
        label = self.form_layout.labelForField(widget)
        if label:
            label.setVisible(visible)

    def _show_fields(self, widgets):
        for w in widgets:
            self._set_row_visible(w, True)

    def _on_type_changed(self, node_type: str):
        # 先隱藏所有選填欄位
        all_optional = [
            self.input_uuid, self.input_password, self.input_username,
            self.input_alter_id, self.input_encryption,
            self.combo_network, self.input_host, self.input_path,
            self.chk_tls, self.input_sni, self.input_alpn, self.input_flow,
            self.input_wg_pub, self.input_wg_priv, self.input_wg_local
        ]
        for w in all_optional:
            self._set_row_visible(w, False)

        # 根據類型顯示對應欄位
        if node_type == "vmess":
            self._show_fields([
                self.input_uuid, self.input_alter_id, self.input_encryption,
                self.combo_network, self.input_host, self.input_path,
                self.chk_tls, self.input_sni, self.input_alpn
            ])
        elif node_type == "vless":
            self._show_fields([
                self.input_uuid,
                self.combo_network, self.input_host, self.input_path,
                self.chk_tls, self.input_sni, self.input_alpn, self.input_flow
            ])
        elif node_type == "trojan":
            self._show_fields([
                self.input_password,
                self.combo_network, self.input_host, self.input_path,
                self.chk_tls, self.input_sni, self.input_alpn
            ])
        elif node_type == "shadowsocks":
            self._show_fields([self.input_password, self.input_encryption])
        elif node_type == "socks5":
            self._show_fields([self.input_username, self.input_password])
        elif node_type == "http":
            self._show_fields([
                self.input_username, self.input_password,
                self.chk_tls, self.input_sni, self.input_alpn
            ])
        elif node_type == "wireguard":
            self._show_fields([
                self.input_wg_pub, self.input_wg_priv, self.input_wg_local
            ])

    def save_changes(self):
        self.node.name = self.input_name.text().strip()
        self.node.node_type = self.combo_type.currentText()
        self.node.server = self.input_server.text().strip()
        try:
            self.node.port = int(self.input_port.text().strip())
        except ValueError:
            pass
            
        self.node.uuid_str = self.input_uuid.text().strip() or None
        self.node.password = self.input_password.text().strip() or None
        self.node.username = self.input_username.text().strip() or None
        self.node.encryption = self.input_encryption.text().strip() or None
        try:
            self.node.alter_id = int(self.input_alter_id.text().strip() or "0")
        except ValueError:
            self.node.alter_id = 0
            
        self.node.network = self.combo_network.currentText()
        self.node.host = self.input_host.text().strip() or None
        self.node.path = self.input_path.text().strip() or None

        self.node.tls_enabled = self.chk_tls.isChecked()
        self.node.sni = self.input_sni.text().strip() or None
        alpn_text = self.input_alpn.text().strip()
        self.node.alpn = [x.strip() for x in alpn_text.split(",") if x.strip()] if alpn_text else None
        self.node.flow = self.input_flow.text().strip() or None
        
        self.node.wg_public_key = self.input_wg_pub.text().strip() or None
        self.node.wg_private_key = self.input_wg_priv.text().strip() or None
        self.node.wg_local_address = self.input_wg_local.text().strip() or None

class TcpPingWorker(QThread):
    progress = Signal(str, int) # node_id, latency_ms (-1 for timeout)
    finished_ping = Signal()

    def __init__(self, nodes_to_ping: list[tuple[str, str, int]]):
        super().__init__()
        self.nodes = nodes_to_ping

    def run(self):
        import concurrent.futures
        
        def _ping_task(node_id, host, port):
            latency = self.ping(host, int(port) if port else 80)
            return node_id, latency

        # Free-threaded Python 3.14 can fully utilize multiple cores here
        # max_workers=64 allows massively fast concurrent testing for large node lists
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
            futures = {
                executor.submit(_ping_task, node_id, host, port): node_id 
                for node_id, host, port in self.nodes
            }
            for future in concurrent.futures.as_completed(futures):
                node_id, latency = future.result()
                self.progress.emit(node_id, latency)
                
        self.finished_ping.emit()

    def ping(self, host: str, port: int) -> int:
        try:
            start = time.time()
            with socket.create_connection((host, port), timeout=3.0):
                pass
            return int((time.time() - start) * 1000)
        except Exception:
            return -1



class NodesPage(QWidget):
    """節點管理頁面"""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._sort_col = -1
        self._sort_reverse = False
        self._filtered_nodes = [] # Tracks real Node instances
        self._table_row_to_node = {} # Map table visual rows to underlying Node
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # ---------- 搜尋/篩選 ----------
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter name keywords...")
        self.search_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.search_input)

        filter_row.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "vmess", "vless", "trojan", "shadowsocks", "socks5", "http"])
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.type_filter)

        layout.addLayout(filter_row)

        # ---------- 手動新增 ----------
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

        add_group.setLayout(add_row)
        layout.addWidget(add_group)

        # ---------- 節點表格 ----------
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

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(self.btn_delete)

        lbl_count = QLabel("")
        self._lbl_count = lbl_count
        btn_row.addStretch()
        btn_row.addWidget(lbl_count)

        layout.addLayout(btn_row)
        self._sync_action_buttons()

    def _on_header_clicked(self, logical_index: int) -> None:
        """點擊標題可以排序"""
        if self._sort_col == logical_index:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = logical_index
            self._sort_reverse = False
        self.refresh_table()

    def refresh_table(self) -> None:
        """Reload the table with filtering and sorting applied."""
        keyword = self.search_input.text().strip().lower()
        type_filter = self.type_filter.currentText()

        # 1. 篩選節點
        filtered = []
        for node in self.app_state.nodes:
            if keyword and keyword not in node.name.lower():
                continue
            if type_filter != "All" and node.node_type != type_filter:
                continue
            filtered.append(node)
            
        # 2. 排序
        # ["ID", "名稱", "類型", "伺服器", "端口", "來源", "延遲"]
        if self._sort_col != -1:
            if self._sort_col == 6:
                # 延遲排序特別處理：將 -1 (Timeout) 等無效數值永遠放到最底下
                valid_nodes = [n for n in filtered if getattr(n, 'latency', None) is not None and getattr(n, 'latency', None) >= 0]
                invalid_nodes = [n for n in filtered if getattr(n, 'latency', None) is None or getattr(n, 'latency', None) < 0]
                
                valid_nodes.sort(key=lambda n: getattr(n, 'latency', 0), reverse=self._sort_reverse)
                filtered = valid_nodes + invalid_nodes
            else:
                def sort_key(n: Node):
                    val = ""
                    # name
                    if self._sort_col == 1:
                        val = n.name.lower()
                    # type
                    elif self._sort_col == 2:
                        val = n.node_type.lower()
                    else:
                        val = n.name.lower()
                    return val

                filtered.sort(key=sort_key, reverse=self._sort_reverse)

        self.table.setRowCount(len(filtered))
        self._filtered_nodes = filtered
        self._table_row_to_node.clear()

        def _fill_row(row_idx: int, node: Node):
            self.table.setItem(row_idx, 0, QTableWidgetItem(node.node_id))
            self.table.setItem(row_idx, 1, QTableWidgetItem(node.name))
            self.table.setItem(row_idx, 2, QTableWidgetItem(node.node_type))
            self.table.setItem(row_idx, 3, QTableWidgetItem(node.server))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(node.port)))
            self.table.setItem(row_idx, 5, QTableWidgetItem(node.source_sub or "Manual"))
            
            lat = getattr(node, 'latency', None)
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

        for row_idx, node in enumerate(filtered):
            _fill_row(row_idx, node)

        self._lbl_count.setText(
            f"Showing {len(filtered)} / Total {len(self.app_state.nodes)} nodes"
        )
        self.summary_label.setText(
            f"{len(self.app_state.nodes)} node(s) available. "
            "Review imported nodes here, then use the toolbar to test them, copy URIs, or turn selections into chains."
        )
        self._sync_action_buttons()

    def _on_filter_changed(self) -> None:
        self.refresh_table()

    def _sync_action_buttons(self) -> None:
        has_selection = bool(self.table.selectedIndexes())
        self.btn_edit.setEnabled(has_selection)
        self.btn_copy.setEnabled(has_selection)
        self.btn_ping.setEnabled(has_selection)
        self.btn_batch_chain.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)

    def _on_manual_add(self) -> None:
        """手動新增節點"""
        uri_text = self.manual_input.text().strip()
        if not uri_text:
            QMessageBox.warning(self, "Notice", "Please enter node URI")
            return

        from parsers.uri_parsers import parse_single_uri
        try:
            node = parse_single_uri(uri_text, source_sub="Manual Insert")
            self.app_state.nodes.append(node)
            self.manual_input.clear()
            self.refresh_table()
            self.data_changed.emit()
            QMessageBox.information(self, "Success", f"Node added: {node.name}")
        except ValueError as err:
            QMessageBox.warning(self, "Parse Failed", str(err))

    def _on_add_new_node(self) -> None:
        """Open a blank NodeEditDialog to create new nodes. 'Add' keeps it open, 'OK' closes."""
        blank_node = Node(
            name="New Node",
            node_type="socks5",
            server="",
            port=1080,
        )
        dialog = NodeEditDialog(blank_node, self)
        dialog.setWindowTitle("Add New Node")
        result = dialog.exec()

        # Collect nodes added via the "Add" button
        total_added = 0
        for n in dialog.added_nodes:
            n.source_sub = "Manual Add"
            self.app_state.nodes.append(n)
            total_added += 1

        # If user clicked OK (not Cancel), also add the final state
        if result == QDialog.DialogCode.Accepted:
            dialog.save_changes()
            if blank_node.server:
                blank_node.source_sub = "Manual Add"
                self.app_state.nodes.append(blank_node)
                total_added += 1

        if total_added > 0:
            self.refresh_table()
            self.data_changed.emit()
            QMessageBox.information(self, "Done", f"Total {total_added} node(s) added!")

    def _on_delete_selected(self) -> None:
        """刪除選中節點"""
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
                self.app_state.nodes = [
                    n for n in self.app_state.nodes if n.node_id != node.node_id
                ]

        self.refresh_table()
        self.data_changed.emit()

    def _on_batch_create_chain(self) -> None:
        """為選中的每個節點建立一條對應的單跳 Chain"""
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes())
        )
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select node(s) to create chain for")
            return

        text, ok = QInputDialog.getText(
            self, 
            "Batch Create Chain", 
            "Pattern (e.g. US{1-8}, or leave blank for node names):"
        )
        
        if not ok:
            return  # 取消

        pattern_text = text.strip()
        from models.chain import Chain

        created_count = 0
        match = re.search(r'\{(\d+)(?:-(\d+))?\}', pattern_text) if pattern_text else None

        for i, row in enumerate(selected_rows):
            node = self._table_row_to_node.get(row)
            if node:
                if not pattern_text:
                    chain_name = f"{node.name}"
                else:
                    if match:
                        start_num = int(match.group(1))
                        prefix = pattern_text[:match.start()]
                        suffix = pattern_text[match.end():]
                        num = start_num + i
                        chain_name = f"{prefix}{num}{suffix}"
                    else:
                        chain_name = f"{pattern_text}{i+1}" if len(selected_rows) > 1 else pattern_text

                new_chain = Chain(name=chain_name)
                new_chain.hop_node_ids.append(node.node_id)
                self.app_state.chains.append(new_chain)
                created_count += 1
        
        self.data_changed.emit()
        QMessageBox.information(
            self, 
            "Success", 
            f"Successfully created {created_count} chains!\n\nYou can now go to Ports to bind them."
        )

    def _show_context_menu(self, pos) -> None:
        """右鍵選單"""
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

    def _on_edit_node(self) -> None:
        """Edit the selected node. 'Add' button duplicates with tweaks."""
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

            # Collect any nodes added via the "Add" button
            added_count = 0
            for n in dialog.added_nodes:
                n.source_sub = node.source_sub or "Manual Add"
                self.app_state.nodes.append(n)
                added_count += 1

            # If OK, save edits to the original node
            if result == QDialog.DialogCode.Accepted:
                dialog.save_changes()

            if added_count > 0 or result == QDialog.DialogCode.Accepted:
                self.refresh_table()
                self.data_changed.emit()
            if added_count > 0:
                QMessageBox.information(self, "Done", f"{added_count} new node(s) added via Add button!")

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
        """Parse clipboard content with the subscription parser and import all valid nodes."""
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
            self.refresh_table()
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

    def _on_test_tcping(self) -> None:
        """多執行緒測試選定節點的 TCP 延遲"""
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
                if latency >= 0:
                    text = f"{latency} ms"
                else:
                    text = "Timeout"
                self.table.setItem(row, 6, QTableWidgetItem(text))
                break

    def _on_ping_finished(self) -> None:
        self.ping_worker.deleteLater()
        self.ping_worker = None
