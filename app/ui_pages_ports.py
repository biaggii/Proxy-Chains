"""
ui_pages_ports.py — 端口映射管理頁面

功能：
  - 新增/刪除 port mapping（listen_host, listen_port, bind_chain）
  - 批量建立（起始 port + 數量 + 分配模式）
  - 顯示代理設定（一鍵複製）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QLabel, QMessageBox,
    QGroupBox, QFormLayout, QSpinBox, QApplication, QCheckBox
)
from PySide6.QtCore import Signal, Qt, QRect, QPoint, QPropertyAnimation, Property
from PySide6.QtGui import QPainter, QColor
from models.app_state import AppState

class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 3.0
        self.animation = QPropertyAnimation(self, b"position")
        self.animation.setDuration(200)
        self.stateChanged.connect(self.setup_animation)

    @Property(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def setup_animation(self, value):
        self.animation.stop()
        if value:
            self.animation.setEndValue(24.0)
        else:
            self.animation.setEndValue(3.0)
        self.animation.start()

    def hitButton(self, pos: QPoint) -> bool:
        return self.contentsRect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRect(0, 0, self.width(), self.height())
        if not self.isChecked():
            p.setBrush(QColor("#cccccc"))
        else:
            p.setBrush(QColor("#4cd964"))
        p.drawRoundedRect(0, 0, rect.width(), rect.height(), 13, 13)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(self._position), 3, 20, 20)
        p.end()



class PortsPage(QWidget):
    """端口映射管理頁面"""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---------- 新增單一端口 ----------
        add_group = QGroupBox("Add Port Mapping")
        add_form = QFormLayout()

        self.input_host = QLineEdit("127.0.0.1")
        add_form.addRow("Listen IP:", self.input_host)

        self.input_port = QSpinBox()
        self.input_port.setRange(1024, 65535)
        self.input_port.setValue(20001)
        add_form.addRow("Listen Port:", self.input_port)

        self.combo_chain = QComboBox()
        add_form.addRow("Bind Chain:", self.combo_chain)

        self.input_remark = QLineEdit()
        self.input_remark.setPlaceholderText("Remarks (Optional)")
        add_form.addRow("Remarks:", self.input_remark)

        btn_add = QPushButton("➕ Add")
        btn_add.clicked.connect(self._on_add_single)
        add_form.addRow(btn_add)

        add_group.setLayout(add_form)
        layout.addWidget(add_group)

        # ---------- 批量建立 ----------
        batch_group = QGroupBox("Batch Create")
        batch_form = QFormLayout()

        self.batch_start_port = QSpinBox()
        self.batch_start_port.setRange(1024, 65535)
        self.batch_start_port.setValue(20001)
        batch_form.addRow("Start Port:", self.batch_start_port)

        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 200)
        self.batch_count.setValue(5)
        batch_form.addRow("Count:", self.batch_count)

        self.batch_chain_combo = QComboBox()
        batch_form.addRow("Bind Chain:", self.batch_chain_combo)

        self.batch_mode = QComboBox()
        self.batch_mode.addItems(["Distribute across existing Chains", "Generate 1-Hop Chain per Node", "All to Same Chain"])
        batch_form.addRow("Alloc Mode:", self.batch_mode)

        btn_batch = QPushButton("📦 Batch Create")
        btn_batch.clicked.connect(self._on_batch_create)
        batch_form.addRow(btn_batch)

        batch_group.setLayout(batch_form)
        layout.addWidget(batch_group)

        # ---------- 映射表格 ----------
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Listen IP", "Port", "Bind Chain", "Remarks"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # ---------- 按鈕 ----------
        btn_row = QHBoxLayout()
        
        self.tun_switch = ToggleSwitch()
        self.tun_switch.setEnabled(False)
        self.tun_switch.toggled.connect(self._on_tun_toggled)
        self.lbl_tun = QLabel("🌍 Enable TUN (Select Row)")
        self.lbl_tun.setStyleSheet("font-weight: bold;")
        
        tun_container = QWidget()
        tun_cont_layout = QHBoxLayout(tun_container)
        tun_cont_layout.setContentsMargins(0, 0, 10, 0)
        tun_cont_layout.addWidget(self.tun_switch)
        tun_cont_layout.addWidget(self.lbl_tun)
        btn_row.addWidget(tun_container)

        btn_copy = QPushButton("📋 Copy Proxy Settings")
        btn_copy.clicked.connect(self._on_copy_proxy_list)
        btn_row.addWidget(btn_copy)

        btn_delete = QPushButton("🗑️ Delete Selected")
        btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(btn_delete)

        btn_clear = QPushButton("🗑️ Clear All")
        btn_clear.clicked.connect(self._on_clear_all)
        btn_row.addWidget(btn_clear)

        layout.addLayout(btn_row)

    # ============================================================
    # 刷新
    # ============================================================

    def refresh_table(self) -> None:
        """刷新表格和下拉選單"""
        self._refresh_chain_combos()
        self._refresh_mapping_table()

    def _refresh_chain_combos(self) -> None:
        """刷新 chain 下拉選單"""
        for combo in [self.combo_chain, self.batch_chain_combo]:
            combo.clear()
            for chain in self.app_state.chains:
                combo.addItem(
                    f"[{chain.chain_id}] {chain.name} ({chain.hop_count()} hop)",
                    userData=chain.chain_id,
                )

    def _refresh_mapping_table(self) -> None:
        """刷新端口映射表格"""
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.app_state.port_mappings))
        for row, pm in enumerate(self.app_state.port_mappings):
            chain = self.app_state.find_chain_by_id(pm.chain_id)
            chain_display = f"[{pm.chain_id}] {chain.name}" if chain else pm.chain_id
            
            item_id = QTableWidgetItem(pm.mapping_id)
            item_host = QTableWidgetItem(pm.listen_host)
            item_port = QTableWidgetItem(str(pm.listen_port))
            item_chain = QTableWidgetItem(chain_display)
            item_remark = QTableWidgetItem(pm.remark)
            
            # If TUN is enabled, lock everything except the TUN row
            if self.app_state.enable_tun and self.app_state.tun_chain_id != pm.chain_id:
                flags = item_id.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable
                item_id.setFlags(flags)
                item_host.setFlags(flags)
                item_port.setFlags(flags)
                item_chain.setFlags(flags)
                item_remark.setFlags(flags)

            self.table.setItem(row, 0, item_id)
            self.table.setItem(row, 1, item_host)
            self.table.setItem(row, 2, item_port)
            self.table.setItem(row, 3, item_chain)
            self.table.setItem(row, 4, item_remark)
        self.table.blockSignals(False)

    # ============================================================
    # 操作
    # ============================================================
    
    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectedIndexes()
        
        # If TUN is enabled, lock selection entirely to the active TUN row
        if self.app_state.enable_tun:
            tun_row = -1
            for r, pm in enumerate(self.app_state.port_mappings):
                if pm.chain_id == self.app_state.tun_chain_id:
                    tun_row = r
                    break
            
            if tun_row != -1:
                # Force selection to the TUN row
                self.table.blockSignals(True)
                self.table.selectRow(tun_row)
                self.table.blockSignals(False)
                
                self.tun_switch.setEnabled(True)
                self.tun_switch.blockSignals(True)
                self.tun_switch.setChecked(True)
                self.tun_switch.position = 24.0
                self.lbl_tun.setText("🌍 Disable TUN")
                self.tun_switch.blockSignals(False)
            return

        if not selected_rows:
            self.tun_switch.setEnabled(False)
            self.lbl_tun.setText("🌍 Enable TUN (Select Row)")
            return
            
        self.tun_switch.setEnabled(True)
        row = sorted(set(idx.row() for idx in selected_rows))[0]
        if row < len(self.app_state.port_mappings):
            pm = self.app_state.port_mappings[row]
            
            self.tun_switch.blockSignals(True)
            self.tun_switch.setChecked(False)
            self.tun_switch.position = 3.0
            self.lbl_tun.setText("🌍 Enable TUN")
            self.tun_switch.blockSignals(False)

    def _on_tun_toggled(self, checked: bool) -> None:
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not selected_rows:
            return
        row = selected_rows[0]
        if row < len(self.app_state.port_mappings):
            pm = self.app_state.port_mappings[row]
            if checked: # Enable TUN
                self.app_state.enable_tun = True
                self.app_state.tun_chain_id = pm.chain_id
                self.lbl_tun.setText("🌍 Disable TUN")
            else: # Disable TUN
                self.app_state.enable_tun = False
                self.app_state.tun_chain_id = None
                self.lbl_tun.setText("🌍 Enable TUN")
            self._refresh_mapping_table()
            self.data_changed.emit()

    def _on_add_single(self) -> None:
        """新增單一端口映射"""
        host = self.input_host.text().strip()
        port = self.input_port.value()
        chain_id = self.combo_chain.currentData()
        remark = self.input_remark.text().strip()

        if not chain_id:
            QMessageBox.warning(self, "Notice", "Please create at least one Chain first")
            return
        if self.app_state.is_port_in_use(port):
            QMessageBox.warning(self, "Notice", f"Port {port} is already in use")
            return

        from models.port_mapping import PortMapping
        pm = PortMapping(
            listen_port=port, chain_id=chain_id,
            listen_host=host, remark=remark,
        )
        self.app_state.port_mappings.append(pm)
        self.input_port.setValue(port + 1)
        self.refresh_table()
        self.data_changed.emit()

    def _on_batch_create(self) -> None:
        """批量建立端口映射"""
        start_port = self.batch_start_port.value()
        count = self.batch_count.value()
        chain_id = self.batch_chain_combo.currentData()
        mode = self.batch_mode.currentText()

        if not chain_id and mode == "All to Same Chain":
            QMessageBox.warning(self, "Notice", "Please select a Chain first")
            return

        from models.port_mapping import PortMapping

        if mode == "All to Same Chain":
            # 全部綁同一條 chain
            created = 0
            for i in range(count):
                port = start_port + i
                if self.app_state.is_port_in_use(port):
                    continue
                pm = PortMapping(listen_port=port, chain_id=chain_id)
                self.app_state.port_mappings.append(pm)
                created += 1
            QMessageBox.information(
                self, "Done", f"Created {created} port mappings (Same Chain)"
            )
        elif mode == "Distribute across existing Chains":
            # 依序把現有的 Chain 分配給新的 Port
            chains = self.app_state.chains
            if not chains:
                QMessageBox.warning(self, "Notice", "No Chains exist, please create one first")
                return
            created = 0
            for i in range(min(count, len(chains))):
                port = start_port + i
                if self.app_state.is_port_in_use(port):
                    continue
                chain = chains[i]
                pm = PortMapping(listen_port=port, chain_id=chain.chain_id)
                self.app_state.port_mappings.append(pm)
                created += 1
            QMessageBox.information(
                self, "Done",
                f"Created {created} mappings (Distributed)"
            )
        else:
            # 各節點單跳：每個節點建一條 1-hop chain + 一個 port mapping
            from models.chain import Chain
            nodes = self.app_state.nodes
            created = 0
            for i in range(min(count, len(nodes))):
                port = start_port + i
                if self.app_state.is_port_in_use(port):
                    continue
                node = nodes[i]
                # 建立 1-hop chain
                auto_chain = Chain(
                    name=f"Auto_{node.name}",
                    hop_node_ids=[node.node_id],
                )
                self.app_state.chains.append(auto_chain)
                pm = PortMapping(listen_port=port, chain_id=auto_chain.chain_id)
                self.app_state.port_mappings.append(pm)
                created += 1
            QMessageBox.information(
                self, "Done",
                f"Created {created} Auto-Chains + mappings"
            )

        self.refresh_table()
        self.data_changed.emit()

    def _on_delete_selected(self) -> None:
        selected_rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes()),
            reverse=True,
        )
        if not selected_rows:
            return
        for row in selected_rows:
            if row < len(self.app_state.port_mappings):
                self.app_state.port_mappings.pop(row)
        self.refresh_table()
        self.data_changed.emit()

    def _on_clear_all(self) -> None:
        if not self.app_state.port_mappings:
            return
        reply = QMessageBox.question(
            self, "Confirm", "Are you sure you want to clear all mappings?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.app_state.port_mappings.clear()
            self.refresh_table()
            self.data_changed.emit()

    def _on_copy_proxy_list(self) -> None:
        """複製代理設定到剪貼簿"""
        lines: list[str] = []
        for pm in self.app_state.port_mappings:
            lines.append(f"socks5://{pm.listen_host}:{pm.listen_port}")
        if not lines:
            QMessageBox.information(self, "Notice", "No port mappings to copy")
            return
        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        QMessageBox.information(
            self, "Copied",
            f"Copied {len(lines)} lines to clipboard:\n\n{text[:500]}"
        )
