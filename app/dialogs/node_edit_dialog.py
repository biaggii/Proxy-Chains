"""
Node editing dialog.

Extracted from ``ui_pages_nodes.py`` so that the nodes page stays
focused on table management and the dialog can be reused elsewhere.
"""

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLineEdit, QComboBox, QCheckBox, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from models.node import Node


class NodeEditDialog(QDialog):
    """Full-field editor for a single proxy node."""

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

        # ── Basic ──────────────────────────────────────
        self.input_name = QLineEdit(node.name)
        self.combo_type = QComboBox()
        self.combo_type.addItems([
            "vmess", "vless", "trojan", "shadowsocks",
            "wireguard", "socks5", "http",
        ])
        self.combo_type.setCurrentText(node.node_type)
        self.combo_type.currentTextChanged.connect(self._on_type_changed)

        self.input_server = QLineEdit(node.server)
        self.input_port = QLineEdit(str(node.port))

        layout.addRow("Alias:", self.input_name)
        layout.addRow("Type:", self.combo_type)
        layout.addRow("Address:", self.input_server)
        layout.addRow("Port:", self.input_port)

        # ── Auth / UUID ────────────────────────────────
        self.input_uuid = QLineEdit(node.uuid_str or "")
        self.input_password = QLineEdit(node.password or "")
        self.input_username = QLineEdit(node.username or "")
        self.input_alter_id = QLineEdit(
            str(node.alter_id) if hasattr(node, "alter_id") else "0"
        )
        self.input_encryption = QLineEdit(node.encryption or "")

        layout.addRow("UUID / ID:", self.input_uuid)
        layout.addRow("Encryption:", self.input_encryption)
        layout.addRow("Username:", self.input_username)
        layout.addRow("Password:", self.input_password)
        layout.addRow("Alter ID:", self.input_alter_id)

        # ── Transport ─────────────────────────────────
        self.combo_network = QComboBox()
        self.combo_network.addItems(["tcp", "ws", "grpc", "h2"])
        self.combo_network.setCurrentText(node.network if node.network else "tcp")

        self.input_host = QLineEdit(node.host or "")
        self.input_path = QLineEdit(node.path or "")

        layout.addRow("Network:", self.combo_network)
        layout.addRow("Host:", self.input_host)
        layout.addRow("Path:", self.input_path)

        # ── TLS ───────────────────────────────────────
        self.chk_tls = QCheckBox("Enable TLS")
        self.chk_tls.setChecked(node.tls_enabled)
        self.input_sni = QLineEdit(node.sni or "")
        self.input_alpn = QLineEdit(
            ",".join(node.alpn) if node.alpn else ""
        )
        self.input_flow = QLineEdit(node.flow or "")

        layout.addRow("TLS / Reality:", self.chk_tls)
        layout.addRow("SNI:", self.input_sni)
        layout.addRow("ALPN (comma separated):", self.input_alpn)
        layout.addRow("Flow (VLESS):", self.input_flow)

        # ── WireGuard ─────────────────────────────────
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
        self.btn_add.setToolTip(
            "Add this node and keep the dialog open for the next one"
        )
        self.btn_add.clicked.connect(self._on_add_clicked)
        btn_row.addWidget(self.btn_add)
        btn_row.addStretch()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        btn_row.addWidget(self.buttons)
        main_layout.addLayout(btn_row)

        # Track nodes added via the Add button
        self.added_nodes: list[Node] = []

        # Initialise field visibility
        self._on_type_changed(self.combo_type.currentText())

    # ── Add button ────────────────────────────────────

    def _on_add_clicked(self) -> None:
        """Save current fields as a new node and keep the dialog open."""
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
        orig_node = self.node
        self.node = new_node
        self.save_changes()
        self.node = orig_node
        self.added_nodes.append(new_node)
        QMessageBox.information(
            self,
            "Added",
            f"Node '{new_node.name}' added! You can modify fields and click Add again.",
        )

    # ── Dynamic field visibility ──────────────────────

    def _set_row_visible(self, widget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self.form_layout.labelForField(widget)
        if label:
            label.setVisible(visible)

    def _show_fields(self, widgets) -> None:
        for w in widgets:
            self._set_row_visible(w, True)

    def _on_type_changed(self, node_type: str) -> None:
        # Hide all optional fields first
        all_optional = [
            self.input_uuid, self.input_password, self.input_username,
            self.input_alter_id, self.input_encryption,
            self.combo_network, self.input_host, self.input_path,
            self.chk_tls, self.input_sni, self.input_alpn, self.input_flow,
            self.input_wg_pub, self.input_wg_priv, self.input_wg_local,
        ]
        for w in all_optional:
            self._set_row_visible(w, False)

        # Show fields relevant to the selected node type
        if node_type == "vmess":
            self._show_fields([
                self.input_uuid, self.input_alter_id, self.input_encryption,
                self.combo_network, self.input_host, self.input_path,
                self.chk_tls, self.input_sni, self.input_alpn,
            ])
        elif node_type == "vless":
            self._show_fields([
                self.input_uuid,
                self.combo_network, self.input_host, self.input_path,
                self.chk_tls, self.input_sni, self.input_alpn, self.input_flow,
            ])
        elif node_type == "trojan":
            self._show_fields([
                self.input_password,
                self.combo_network, self.input_host, self.input_path,
                self.chk_tls, self.input_sni, self.input_alpn,
            ])
        elif node_type == "shadowsocks":
            self._show_fields([self.input_password, self.input_encryption])
        elif node_type == "socks5":
            self._show_fields([self.input_username, self.input_password])
        elif node_type == "http":
            self._show_fields([
                self.input_username, self.input_password,
                self.chk_tls, self.input_sni, self.input_alpn,
            ])
        elif node_type == "wireguard":
            self._show_fields([
                self.input_wg_pub, self.input_wg_priv, self.input_wg_local,
            ])

    # ── Persist changes back to the node ──────────────

    def save_changes(self) -> None:
        """Write form values back to ``self.node``."""
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
        self.node.alpn = (
            [x.strip() for x in alpn_text.split(",") if x.strip()]
            if alpn_text
            else None
        )
        self.node.flow = self.input_flow.text().strip() or None

        self.node.wg_public_key = self.input_wg_pub.text().strip() or None
        self.node.wg_private_key = self.input_wg_priv.text().strip() or None
        self.node.wg_local_address = self.input_wg_local.text().strip() or None
