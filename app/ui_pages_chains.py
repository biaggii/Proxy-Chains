"""
Chain management page.

Responsibilities:
  - Display all chains in a list
  - Create and delete chains
  - Edit chain hops (add, remove, reorder nodes)
  - Add a SOCKS5 exit to an existing chain (advanced, collapsible)
  - Batch rename selected chains
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QLabel, QMessageBox,
    QLineEdit, QGroupBox, QFormLayout, QComboBox,
    QSplitter, QInputDialog,
)
from PySide6.QtCore import Signal, Qt
from models.app_state import AppState
from utils.pattern_rename import expand_pattern


class ChainsPage(QWidget):
    """Build and edit proxy chains."""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.summary_label = QLabel(
            "A chain is the ordered route your traffic follows. "
            "The top hop is the entry, and the last hop is the exit."
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # ── Chain list + hop editor ────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: chain list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Chains"))
        self.chain_list = QListWidget()
        self.chain_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.chain_list.currentRowChanged.connect(self._on_chain_selected)
        left_layout.addWidget(self.chain_list)

        btn_add_empty_chain = QPushButton("Create New Chain")
        btn_add_empty_chain.clicked.connect(self._on_add_empty_chain)
        left_layout.addWidget(btn_add_empty_chain)

        # Batch rename
        rename_row = QHBoxLayout()
        self.input_rename_pattern = QLineEdit()
        self.input_rename_pattern.setPlaceholderText("e.g. US{1-8} or HK{1-5}")
        rename_row.addWidget(self.input_rename_pattern)
        btn_batch_rename = QPushButton("Rename Selected")
        btn_batch_rename.clicked.connect(self._on_batch_rename)
        rename_row.addWidget(btn_batch_rename)
        left_layout.addLayout(rename_row)

        btn_del_chain = QPushButton("Delete Selected Chain")
        btn_del_chain.clicked.connect(self._on_delete_chain)
        left_layout.addWidget(btn_del_chain)
        splitter.addWidget(left_widget)

        # Right: hop editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("Hops (Top to Bottom = Entry to Exit)"))

        self.hop_list = QListWidget()
        right_layout.addWidget(self.hop_list)

        hop_btns = QHBoxLayout()
        self.combo_add_node = QComboBox()
        hop_btns.addWidget(self.combo_add_node)
        btn_add_hop = QPushButton("Add Hop")
        btn_add_hop.clicked.connect(self._on_add_hop)
        hop_btns.addWidget(btn_add_hop)
        right_layout.addLayout(hop_btns)

        hop_btns2 = QHBoxLayout()
        btn_up = QPushButton("Move Up")
        btn_up.clicked.connect(self._on_move_up)
        hop_btns2.addWidget(btn_up)
        btn_down = QPushButton("Move Down")
        btn_down.clicked.connect(self._on_move_down)
        hop_btns2.addWidget(btn_down)
        btn_remove_hop = QPushButton("Remove Hop")
        btn_remove_hop.clicked.connect(self._on_remove_hop)
        hop_btns2.addWidget(btn_remove_hop)
        right_layout.addLayout(hop_btns2)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 500])
        layout.addWidget(splitter)

        # ── Advanced: Add SOCKS5 exit (collapsed by default) ──
        wrap_group = QGroupBox("Advanced: Add SOCKS5 Exit")
        wrap_group.setCheckable(True)
        wrap_group.setChecked(False)
        wrap_form = QFormLayout()
        self.combo_pre_chain = QComboBox()
        wrap_form.addRow("Base Chain:", self.combo_pre_chain)
        self.combo_landing_socks5 = QComboBox()
        wrap_form.addRow("Exit SOCKS5 Node:", self.combo_landing_socks5)
        self.input_wrap_name = QLineEdit()
        self.input_wrap_name.setPlaceholderText("New Route Name")
        wrap_form.addRow("New Chain Name:", self.input_wrap_name)
        btn_wrap = QPushButton("Create Exit Chain")
        btn_wrap.clicked.connect(self._on_wrap_socks5)
        wrap_form.addRow(btn_wrap)
        wrap_group.setLayout(wrap_form)
        layout.addWidget(wrap_group)

    # ── Refresh ───────────────────────────────────────

    def refresh(self) -> None:
        """Reload all lists and combos."""
        self._refresh_chain_list()
        self._refresh_combos()
        self.summary_label.setText(
            f"{len(self.app_state.chains)} chain(s) available. "
            "Build hops in the right panel, or use the advanced section to add a SOCKS5 exit."
        )

    def _refresh_chain_list(self) -> None:
        current_row = self.chain_list.currentRow()
        self.chain_list.clear()
        for chain in self.app_state.chains:
            hop_count = chain.hop_count()
            self.chain_list.addItem(
                f"[{chain.chain_id}] {chain.name}  ({hop_count} hops)"
            )
        if 0 <= current_row < self.chain_list.count():
            self.chain_list.setCurrentRow(current_row)

    def _refresh_combos(self) -> None:
        # Node combo (for adding hops)
        self.combo_add_node.clear()
        for node in self.app_state.nodes:
            self.combo_add_node.addItem(
                f"[{node.node_id}] {node.name} ({node.node_type})",
                userData=node.node_id,
            )

        # Pre-chain combo
        self.combo_pre_chain.clear()
        for chain in self.app_state.chains:
            self.combo_pre_chain.addItem(
                f"[{chain.chain_id}] {chain.name}",
                userData=chain.chain_id,
            )

        # SOCKS5 node combo (only socks5 nodes)
        self.combo_landing_socks5.clear()
        for node in self.app_state.nodes:
            if node.node_type == "socks5":
                self.combo_landing_socks5.addItem(
                    f"[{node.node_id}] {node.name} ({node.server}:{node.port})",
                    userData=node.node_id,
                )

    # ── Chain operations ──────────────────────────────

    def _on_add_empty_chain(self) -> None:
        name, ok = QInputDialog.getText(self, "Add", "Enter new Chain Name:")
        if ok and name.strip():
            from models.chain import Chain
            new_chain = Chain(name=name.strip())
            self.app_state.chains.append(new_chain)
            self.refresh()
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
        self.refresh()
        self.hop_list.clear()
        self.data_changed.emit()

    def _on_batch_rename(self) -> None:
        """Batch rename using a pattern like US{1-8}."""
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

        for i, row in enumerate(selected_rows):
            if 0 <= row < len(self.app_state.chains):
                self.app_state.chains[row].name = expand_pattern(
                    pattern_text, i, len(selected_rows)
                )

        self.input_rename_pattern.clear()
        self.refresh()
        self.data_changed.emit()
        QMessageBox.information(self, "Success", f"Renamed {len(selected_rows)} Chains")

    def _on_wrap_socks5(self) -> None:
        """Create a new chain = base chain hops + SOCKS5 exit."""
        pre_chain_id = self.combo_pre_chain.currentData()
        landing_node_id = self.combo_landing_socks5.currentData()
        new_name = self.input_wrap_name.text().strip()

        if not pre_chain_id:
            QMessageBox.warning(self, "Notice", "Please select a Base Chain")
            return
        if not landing_node_id:
            QMessageBox.warning(self, "Notice", "Please select an Exit SOCKS5 Node")
            return
        if not new_name:
            QMessageBox.warning(self, "Notice", "Please enter new Chain Name")
            return

        pre_chain = self.app_state.find_chain_by_id(pre_chain_id)
        if pre_chain is None:
            QMessageBox.warning(self, "Error", "Base chain not found")
            return

        from models.chain import Chain
        new_hops = list(pre_chain.hop_node_ids) + [landing_node_id]
        new_chain = Chain(name=new_name, hop_node_ids=new_hops)
        self.app_state.chains.append(new_chain)

        self.input_wrap_name.clear()
        self.refresh()
        self.data_changed.emit()
        QMessageBox.information(
            self, "Success",
            f"Created Exit Chain: {new_name} ({len(new_hops)} hops)"
        )

    # ── Hop operations ────────────────────────────────

    def _get_selected_chain(self):
        """Return the currently selected chain, or None."""
        row = self.chain_list.currentRow()
        if row < 0 or row >= len(self.app_state.chains):
            return None
        return self.app_state.chains[row]

    def _on_chain_selected(self, row: int) -> None:
        """Display hops for the selected chain."""
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
