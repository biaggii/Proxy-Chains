"""
ui_pages_chains.py — 鏈式代理管理頁面

功能：
  - 顯示所有 chain（清單）
  - 新增/刪除 chain
  - 編輯 chain 的 hops（從節點清單中選取，支援上移/下移）
  - Wrap Socks5：選一條 pre-chain + 一個 socks5 節點 = 新 chain
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QMessageBox,
    QLineEdit, QGroupBox, QFormLayout, QComboBox,
    QSplitter, QInputDialog
)
from PySide6.QtCore import Signal, Qt
from models.app_state import AppState


class ChainsPage(QWidget):
    """鏈式代理管理頁面"""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---------- 上半：Wrap Socks5 ----------
        top_row = QHBoxLayout()

        # Wrap Socks5
        wrap_group = QGroupBox("Wrap Socks5 (Pre-chain + Landing)")
        wrap_form = QFormLayout()
        self.combo_pre_chain = QComboBox()
        wrap_form.addRow("Pre-chain:", self.combo_pre_chain)
        self.combo_landing_socks5 = QComboBox()
        wrap_form.addRow("Landing Socks5:", self.combo_landing_socks5)
        self.input_wrap_name = QLineEdit()
        self.input_wrap_name.setPlaceholderText("New Chain Name")
        wrap_form.addRow("New Name:", self.input_wrap_name)
        btn_wrap = QPushButton("🔗 Generate Wrap Chain")
        btn_wrap.clicked.connect(self._on_wrap_socks5)
        wrap_form.addRow(btn_wrap)
        wrap_group.setLayout(wrap_form)
        top_row.addWidget(wrap_group)

        layout.addLayout(top_row)

        # ---------- 下半：chain 清單 + hop 編輯 ----------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左邊：chain 清單
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("All Chains:"))
        self.chain_list = QListWidget()
        self.chain_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.chain_list.currentRowChanged.connect(self._on_chain_selected)
        left_layout.addWidget(self.chain_list)

        btn_add_empty_chain = QPushButton("➕ Add Empty Chain")
        btn_add_empty_chain.clicked.connect(self._on_add_empty_chain)
        left_layout.addWidget(btn_add_empty_chain)

        # 批量改名
        rename_row = QHBoxLayout()
        self.input_rename_pattern = QLineEdit()
        self.input_rename_pattern.setPlaceholderText("e.g. US{1-8} or HK{1-5}")
        rename_row.addWidget(self.input_rename_pattern)
        btn_batch_rename = QPushButton("✏️ Batch Rename")
        btn_batch_rename.clicked.connect(self._on_batch_rename)
        rename_row.addWidget(btn_batch_rename)
        left_layout.addLayout(rename_row)

        btn_del_chain = QPushButton("🗑️ Delete Selected Chain")
        btn_del_chain.clicked.connect(self._on_delete_chain)
        left_layout.addWidget(btn_del_chain)
        splitter.addWidget(left_widget)

        # 右邊：hop 編輯
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("Hops (Top to Bottom = Entry to Landing):"))

        self.hop_list = QListWidget()
        right_layout.addWidget(self.hop_list)

        # hop 操作按鈕
        hop_btns = QHBoxLayout()
        self.combo_add_node = QComboBox()
        hop_btns.addWidget(self.combo_add_node)
        btn_add_hop = QPushButton("➕ Add Hop")
        btn_add_hop.clicked.connect(self._on_add_hop)
        hop_btns.addWidget(btn_add_hop)
        right_layout.addLayout(hop_btns)

        hop_btns2 = QHBoxLayout()
        btn_up = QPushButton("⬆️ Move Up")
        btn_up.clicked.connect(self._on_move_up)
        hop_btns2.addWidget(btn_up)
        btn_down = QPushButton("⬇️ Move Down")
        btn_down.clicked.connect(self._on_move_down)
        hop_btns2.addWidget(btn_down)
        btn_remove_hop = QPushButton("❌ Remove Hop")
        btn_remove_hop.clicked.connect(self._on_remove_hop)
        hop_btns2.addWidget(btn_remove_hop)
        right_layout.addLayout(hop_btns2)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 500])
        layout.addWidget(splitter)

    # ============================================================
    # 刷新
    # ============================================================

    def refresh_table(self) -> None:
        """刷新所有清單"""
        self._refresh_chain_list()
        self._refresh_combos()

    def _refresh_chain_list(self) -> None:
        """刷新 chain 清單"""
        current_row = self.chain_list.currentRow()
        self.chain_list.clear()
        for chain in self.app_state.chains:
            hop_count = chain.hop_count()
            self.chain_list.addItem(
                f"[{chain.chain_id}] {chain.name}  ({hop_count} hops)"
            )
        if current_row >= 0 and current_row < self.chain_list.count():
            self.chain_list.setCurrentRow(current_row)

    def _refresh_combos(self) -> None:
        """刷新下拉選單"""
        # 節點下拉（用於加入 hop）
        self.combo_add_node.clear()
        for node in self.app_state.nodes:
            self.combo_add_node.addItem(
                f"[{node.node_id}] {node.name} ({node.node_type})",
                userData=node.node_id,
            )

        # Pre-chain 下拉
        self.combo_pre_chain.clear()
        for chain in self.app_state.chains:
            self.combo_pre_chain.addItem(
                f"[{chain.chain_id}] {chain.name}",
                userData=chain.chain_id,
            )

        # 落地 socks5 下拉（只顯示 socks5 類型的節點）
        self.combo_landing_socks5.clear()
        for node in self.app_state.nodes:
            if node.node_type == "socks5":
                self.combo_landing_socks5.addItem(
                    f"[{node.node_id}] {node.name} ({node.server}:{node.port})",
                    userData=node.node_id,
                )

    # ============================================================
    # Chain 操作
    # ============================================================

    def _on_add_empty_chain(self) -> None:
        name, ok = QInputDialog.getText(self, "Add", "Enter new Chain Name:")
        if ok and name.strip():
            from models.chain import Chain
            new_chain = Chain(name=name.strip())
            self.app_state.chains.append(new_chain)
            self.refresh_table()
            self.data_changed.emit()

    def _on_delete_chain(self) -> None:
        selected_rows = sorted(
            set(idx.row() for idx in self.chain_list.selectedIndexes()),
            reverse=True,
        )
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select a Chain")
            return
        for row in selected_rows:
            if 0 <= row < len(self.app_state.chains):
                self.app_state.chains.pop(row)
        self.refresh_table()
        self.hop_list.clear()
        self.data_changed.emit()

    def _on_batch_rename(self) -> None:
        """批量改名，支援格式：us{1-8} 或 HK{3-10}"""
        import re
        pattern_text = self.input_rename_pattern.text().strip()
        if not pattern_text:
            QMessageBox.warning(self, "Notice", "Please enter rename pattern, e.g.: US{1-8}")
            return

        selected_rows = sorted(
            set(idx.row() for idx in self.chain_list.selectedIndexes())
        )
        if not selected_rows:
            QMessageBox.warning(self, "Notice", "Please select Chain(s) to rename")
            return

        # 解析模板：找 {start-end} 或 {start}
        match = re.search(r'\{(\d+)(?:-(\d+))?\}', pattern_text)
        if match:
            start_num = int(match.group(1))
            prefix = pattern_text[:match.start()]
            suffix = pattern_text[match.end():]
            # 為每個選中的 chain 依序編號
            for i, row in enumerate(selected_rows):
                if 0 <= row < len(self.app_state.chains):
                    num = start_num + i
                    self.app_state.chains[row].name = f"{prefix}{num}{suffix}"
        else:
            # 沒有 {n} 模板，就都改成一樣的名字
            for row in selected_rows:
                if 0 <= row < len(self.app_state.chains):
                    self.app_state.chains[row].name = pattern_text

        self.input_rename_pattern.clear()
        self.refresh_table()
        self.data_changed.emit()
        QMessageBox.information(self, "Success", f"Renamed {len(selected_rows)} Chains")

    def _on_wrap_socks5(self) -> None:
        """Wrap Socks5：pre-chain + socks5 落地 = 新 chain"""
        pre_chain_id = self.combo_pre_chain.currentData()
        landing_node_id = self.combo_landing_socks5.currentData()
        new_name = self.input_wrap_name.text().strip()

        if not pre_chain_id:
            QMessageBox.warning(self, "Notice", "Please select a Pre-chain")
            return
        if not landing_node_id:
            QMessageBox.warning(self, "Notice", "Please select a Landing Socks5 Node")
            return
        if not new_name:
            QMessageBox.warning(self, "Notice", "Please enter new Chain Name")
            return

        pre_chain = self.app_state.find_chain_by_id(pre_chain_id)
        if pre_chain is None:
            QMessageBox.warning(self, "Error", "Pre-chain not found")
            return

        # 建立新 chain = pre-chain 的 hops + 落地 socks5
        from models.chain import Chain
        new_hops = list(pre_chain.hop_node_ids) + [landing_node_id]
        new_chain = Chain(name=new_name, hop_node_ids=new_hops)
        self.app_state.chains.append(new_chain)

        self.input_wrap_name.clear()
        self.refresh_table()
        self.data_changed.emit()
        QMessageBox.information(
            self, "Success",
            f"Created Wrap Chain: {new_name} ({len(new_hops)} hops)"
        )

    # ============================================================
    # Hop 操作
    # ============================================================

    def _get_selected_chain(self):
        """取得目前選中的 chain"""
        row = self.chain_list.currentRow()
        if row < 0 or row >= len(self.app_state.chains):
            return None
        return self.app_state.chains[row]

    def _on_chain_selected(self, row: int) -> None:
        """當選中一條 chain，顯示它的 hops"""
        self.hop_list.clear()
        chain = self._get_selected_chain()
        if chain is None:
            return

        for node_id in chain.hop_node_ids:
            node = self.app_state.find_node_by_id(node_id)
            if node:
                self.hop_list.addItem(
                    f"[{node.node_id}] {node.name} ({node.node_type}, {node.server}:{node.port})"
                )
            else:
                self.hop_list.addItem(f"[{node_id}] ⚠️ Node Deleted")

    def _on_add_hop(self) -> None:
        chain = self._get_selected_chain()
        if chain is None:
            QMessageBox.information(self, "Notice", "Please select a Chain on the left first")
            return

        node_id = self.combo_add_node.currentData()
        if not node_id:
            QMessageBox.information(self, "Notice", "Please select a Node to add")
            return

        chain.add_hop(node_id)
        self._on_chain_selected(self.chain_list.currentRow())
        self._refresh_chain_list()
        self.data_changed.emit()

    def _on_remove_hop(self) -> None:
        chain = self._get_selected_chain()
        if chain is None:
            return
        hop_row = self.hop_list.currentRow()
        if hop_row < 0:
            return
        chain.remove_hop(hop_row)
        self._on_chain_selected(self.chain_list.currentRow())
        self._refresh_chain_list()
        self.data_changed.emit()

    def _on_move_up(self) -> None:
        chain = self._get_selected_chain()
        if chain is None:
            return
        hop_row = self.hop_list.currentRow()
        chain.move_hop_up(hop_row)
        self._on_chain_selected(self.chain_list.currentRow())
        self.hop_list.setCurrentRow(max(0, hop_row - 1))
        self.data_changed.emit()

    def _on_move_down(self) -> None:
        chain = self._get_selected_chain()
        if chain is None:
            return
        hop_row = self.hop_list.currentRow()
        chain.move_hop_down(hop_row)
        self._on_chain_selected(self.chain_list.currentRow())
        self.hop_list.setCurrentRow(min(self.hop_list.count() - 1, hop_row + 1))
        self.data_changed.emit()
