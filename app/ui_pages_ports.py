"""
Port binding management page.

Responsibilities:
  - Create and delete local port bindings
  - Batch-create bindings with different assignment strategies
  - Control the dedicated TUN route target
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
    """Manage local bindings and the optional TUN route."""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.feedback_label = QLabel("No routing changes yet.")
        self.feedback_label.setWordWrap(True)
        self._set_feedback("No routing changes yet.", "info")
        layout.addWidget(self.feedback_label)

        tun_group = QGroupBox("System TUN Mode")
        tun_layout = QFormLayout()
        self.tun_switch = ToggleSwitch()
        self.tun_switch.toggled.connect(self._on_tun_toggled)
        self.lbl_tun = QLabel("Off")
        tun_switch_row = QHBoxLayout()
        tun_switch_row.addWidget(self.tun_switch)
        tun_switch_row.addWidget(self.lbl_tun)
        tun_layout.addRow("Status:", tun_switch_row)
        self.tun_chain_combo = QComboBox()
        self.tun_chain_combo.currentIndexChanged.connect(self._on_tun_chain_changed)
        tun_layout.addRow("Use Chain:", self.tun_chain_combo)
        self.tun_hint = QLabel(
            "TUN sends system traffic through the selected chain. It works best when the app is running as Administrator."
        )
        self.tun_hint.setWordWrap(True)
        tun_layout.addRow("", self.tun_hint)
        tun_group.setLayout(tun_layout)
        layout.addWidget(tun_group)

        forms_row = QHBoxLayout()

        add_group = QGroupBox("Add Port Mapping")
        add_form = QFormLayout()

        self.input_host = QLineEdit("127.0.0.1")
        add_form.addRow("Listen Address:", self.input_host)

        self.input_port = QSpinBox()
        self.input_port.setRange(1024, 65535)
        self.input_port.setValue(20001)
        add_form.addRow("Listen Port:", self.input_port)

        self.combo_chain = QComboBox()
        add_form.addRow("Use Chain:", self.combo_chain)

        self.input_remark = QLineEdit()
        self.input_remark.setPlaceholderText("Remarks (Optional)")
        add_form.addRow("Remarks:", self.input_remark)

        btn_add = QPushButton("Create Mapping")
        btn_add.clicked.connect(self._on_add_single)
        add_form.addRow(btn_add)

        add_group.setLayout(add_form)
        forms_row.addWidget(add_group)

        batch_group = QGroupBox("Batch Create Port Mappings")
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
        batch_form.addRow("Use Chain:", self.batch_chain_combo)

        self.batch_mode = QComboBox()
        self.batch_mode.addItems(["Use Each Existing Chain in Order", "Create One 1-Hop Chain per Node", "Use One Chain for All Ports"])
        batch_form.addRow("Assignment Strategy:", self.batch_mode)

        btn_batch = QPushButton("Create Batch")
        btn_batch.clicked.connect(self._on_batch_create)
        batch_form.addRow(btn_batch)

        batch_group.setLayout(batch_form)
        forms_row.addWidget(batch_group)
        layout.addLayout(forms_row)

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
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()

        btn_copy = QPushButton("Copy SOCKS5 Endpoints")
        btn_copy.clicked.connect(self._on_copy_proxy_list)
        btn_row.addWidget(btn_copy)

        btn_delete = QPushButton("Delete Selected")
        btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(btn_delete)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._on_clear_all)
        btn_row.addWidget(btn_clear)

        layout.addLayout(btn_row)

    def refresh_table(self) -> None:
        """Refresh the table and selector state."""
        self._refresh_chain_combos()
        self._refresh_mapping_table()
        self._refresh_tun_panel()
        self.summary_label.setText(
            f"{len(self.app_state.port_mappings)} local binding(s). "
            f"TUN is {'enabled' if self.app_state.enable_tun else 'disabled'}."
        )

    def _refresh_chain_combos(self) -> None:
        """Refresh chain selectors from the latest state."""
        current_tun_chain = self.app_state.tun_chain_id
        for combo in [self.combo_chain, self.batch_chain_combo, self.tun_chain_combo]:
            combo.blockSignals(True)
            combo.clear()
            for chain in self.app_state.chains:
                combo.addItem(
                    f"[{chain.chain_id}] {chain.name} ({chain.hop_count()} hop)",
                    userData=chain.chain_id,
                )
            combo.blockSignals(False)
        if current_tun_chain:
            index = self.tun_chain_combo.findData(current_tun_chain)
            if index >= 0:
                self.tun_chain_combo.blockSignals(True)
                self.tun_chain_combo.setCurrentIndex(index)
                self.tun_chain_combo.blockSignals(False)

    def _refresh_mapping_table(self) -> None:
        """Refresh the bindings table."""
        self.table.setRowCount(len(self.app_state.port_mappings))
        for row, pm in enumerate(self.app_state.port_mappings):
            chain = self.app_state.find_chain_by_id(pm.chain_id)
            chain_display = f"[{pm.chain_id}] {chain.name}" if chain else pm.chain_id
            if self.app_state.enable_tun and pm.chain_id == self.app_state.tun_chain_id:
                chain_display = f"{chain_display}  [TUN]"
            
            item_id = QTableWidgetItem(pm.mapping_id)
            item_host = QTableWidgetItem(pm.listen_host)
            item_port = QTableWidgetItem(str(pm.listen_port))
            item_chain = QTableWidgetItem(chain_display)
            item_remark = QTableWidgetItem(pm.remark)
            if self.app_state.enable_tun and pm.chain_id == self.app_state.tun_chain_id:
                item_chain.setBackground(QColor("#dbeafe"))

            self.table.setItem(row, 0, item_id)
            self.table.setItem(row, 1, item_host)
            self.table.setItem(row, 2, item_port)
            self.table.setItem(row, 3, item_chain)
            self.table.setItem(row, 4, item_remark)

    def _on_tun_toggled(self, checked: bool) -> None:
        chain_id = self.tun_chain_combo.currentData()
        if checked and not chain_id:
            QMessageBox.warning(self, "Notice", "Create a chain before enabling TUN")
            self.tun_switch.blockSignals(True)
            self.tun_switch.setChecked(False)
            self.tun_switch.position = 3.0
            self.tun_switch.blockSignals(False)
            return

        self.app_state.enable_tun = checked
        self.app_state.tun_chain_id = chain_id if checked else ""
        self._refresh_tun_panel()
        self._refresh_mapping_table()
        self._set_feedback(
            "TUN mode enabled. System traffic will use the selected chain."
            if checked
            else "TUN mode disabled. Local port bindings remain available.",
            "info",
        )
        self.data_changed.emit()

    def _on_tun_chain_changed(self, index: int) -> None:
        if index < 0:
            return
        chain_id = self.tun_chain_combo.currentData()
        if self.app_state.enable_tun and chain_id:
            self.app_state.tun_chain_id = chain_id
            self._refresh_mapping_table()
            self._set_feedback("Updated the chain used by TUN mode.", "info")
            self.data_changed.emit()

    def _refresh_tun_panel(self) -> None:
        has_chains = self.tun_chain_combo.count() > 0
        self.tun_switch.setEnabled(has_chains)
        self.tun_chain_combo.setEnabled(has_chains)
        self.tun_switch.blockSignals(True)
        self.tun_switch.setChecked(self.app_state.enable_tun)
        self.tun_switch.position = 24.0 if self.app_state.enable_tun else 3.0
        self.tun_switch.blockSignals(False)
        self.lbl_tun.setText("Enabled" if self.app_state.enable_tun else "Off")
        if not has_chains:
            self.tun_hint.setText("Create a chain first. TUN needs one route that will carry system traffic.")
        elif self.app_state.enable_tun:
            self.tun_hint.setText(
                "All system traffic will use the selected chain. Running as Administrator is still recommended."
            )
        else:
            self.tun_hint.setText(
                "TUN sends system traffic through the selected chain. It works best when the app is running as Administrator."
            )

    def _on_add_single(self) -> None:
        """Create one new port mapping."""
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
        self._set_feedback(f"Created mapping {host}:{port}.", "success")
        self.data_changed.emit()

    def _on_batch_create(self) -> None:
        """Create multiple port mappings in one action."""
        start_port = self.batch_start_port.value()
        count = self.batch_count.value()
        chain_id = self.batch_chain_combo.currentData()
        mode = self.batch_mode.currentText()

        if not chain_id and mode == "Use One Chain for All Ports":
            QMessageBox.warning(self, "Notice", "Please select a Chain first")
            return

        from models.port_mapping import PortMapping

        created = 0
        feedback_message = ""
        if mode == "Use One Chain for All Ports":
            for i in range(count):
                port = start_port + i
                if self.app_state.is_port_in_use(port):
                    continue
                pm = PortMapping(listen_port=port, chain_id=chain_id)
                self.app_state.port_mappings.append(pm)
                created += 1
            feedback_message = f"Created {created} mapping(s) using the same chain."
        elif mode == "Use Each Existing Chain in Order":
            chains = self.app_state.chains
            if not chains:
                QMessageBox.warning(self, "Notice", "No Chains exist, please create one first")
                return
            for i in range(min(count, len(chains))):
                port = start_port + i
                if self.app_state.is_port_in_use(port):
                    continue
                chain = chains[i]
                pm = PortMapping(listen_port=port, chain_id=chain.chain_id)
                self.app_state.port_mappings.append(pm)
                created += 1
            feedback_message = f"Created {created} distributed mapping(s) across existing chains."
        else:
            from models.chain import Chain
            nodes = self.app_state.nodes
            for i in range(min(count, len(nodes))):
                port = start_port + i
                if self.app_state.is_port_in_use(port):
                    continue
                node = nodes[i]
                auto_chain = Chain(
                    name=f"Auto_{node.name}",
                    hop_node_ids=[node.node_id],
                )
                self.app_state.chains.append(auto_chain)
                pm = PortMapping(listen_port=port, chain_id=auto_chain.chain_id)
                self.app_state.port_mappings.append(pm)
                created += 1
            feedback_message = f"Created {created} single-hop chain(s) and mapping(s)."

        self.refresh_table()
        if feedback_message:
            self._set_feedback(feedback_message, "success" if created else "warning")
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
        self._set_feedback(f"Removed {len(selected_rows)} mapping(s).", "info")
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
            self._set_feedback("Cleared all port mappings.", "info")
            self.data_changed.emit()

    def _on_copy_proxy_list(self) -> None:
        """Copy all local SOCKS5 endpoints to the clipboard."""
        lines: list[str] = []
        for pm in self.app_state.port_mappings:
            lines.append(f"socks5://{pm.listen_host}:{pm.listen_port}")
        if not lines:
            self._set_feedback("No port mappings are available to copy.", "warning")
            return
        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        self._set_feedback(f"Copied {len(lines)} SOCKS5 endpoint(s) to the clipboard.", "success")

    def _set_feedback(self, message: str, level: str) -> None:
        colors = {
            "success": ("#ecfdf3", "#166534"),
            "warning": ("#fff7ed", "#9a3412"),
            "error": ("#fef2f2", "#991b1b"),
            "info": ("#eff6ff", "#1d4ed8"),
        }
        background, foreground = colors.get(level, colors["info"])
        self.feedback_label.setText(message)
        self.feedback_label.setStyleSheet(
            f"padding: 8px 10px; border-radius: 8px; background: {background}; color: {foreground}; border: 1px solid {foreground};"
        )
