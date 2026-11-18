"""Small editor for composing a route from imported base nodes."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
)

from models.app_state import AppState
from models.chain import Chain


class ChainEditorDialog(QDialog):
    """Choose base nodes and arrange their entry-to-exit order."""

    def __init__(
        self,
        app_state: AppState,
        chain: Chain | None = None,
        listen_port: int = 20001,
        used_ports: set[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.app_state = app_state
        self.chain = chain
        self.setWindowTitle("Edit Chain" if chain else "Create Chain")
        self.resize(900, 620)

        layout = QVBoxLayout(self)
        self.name_input = QLineEdit(chain.name if chain else "")
        self.name_input.setPlaceholderText("Chain name")
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.name_input)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Local Port"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(listen_port)
        self.port_input.setToolTip("Local proxy port assigned to this Chain.")
        port_row.addWidget(self.port_input)
        port_row.addStretch()
        layout.addLayout(port_row)
        self.used_ports = set(used_ports or set())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        available_panel = QVBoxLayout()
        available_panel.addWidget(QLabel("Available Base Nodes"))
        self.available = QListWidget()
        self.available.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        available_panel.addWidget(self.available)
        add_button = QPushButton("Add →")
        add_button.clicked.connect(self._add_selected)
        available_panel.addWidget(add_button)
        available_widget = self._panel(available_panel)

        route_panel = QVBoxLayout()
        route_panel.addWidget(QLabel("Chain Hops · Entry → Exit"))
        self.hops = QListWidget()
        self.hops.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        route_panel.addWidget(self.hops)
        controls = QHBoxLayout()
        for label, callback in (
            ("Remove", self._remove_selected),
            ("Move Up", self._move_up),
            ("Move Down", self._move_down),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        route_panel.addLayout(controls)
        route_widget = self._panel(route_panel)

        splitter.addWidget(available_widget)
        splitter.addWidget(route_widget)
        splitter.setSizes([420, 420])
        layout.addWidget(splitter, 1)

        self._nodes_by_id = {}
        for node in app_state.nodes:
            self._nodes_by_id[node.node_id] = node
            item = QListWidgetItem(f"{node.name}  ·  {node.node_type}  ·  {node.server}:{node.port}")
            item.setData(Qt.ItemDataRole.UserRole, node.node_id)
            self.available.addItem(item)

        if chain:
            for node_id in chain.hop_node_ids:
                self._append_hop(node_id)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _panel(layout: QVBoxLayout):
        from PySide6.QtWidgets import QWidget

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _append_hop(self, node_id: str) -> None:
        node = self._nodes_by_id.get(node_id)
        if node is None:
            return
        item = QListWidgetItem(f"{node.name}  ·  {node.node_type}  ·  {node.server}:{node.port}")
        item.setData(Qt.ItemDataRole.UserRole, node_id)
        self.hops.addItem(item)

    def _add_selected(self) -> None:
        for item in self.available.selectedItems():
            node_id = item.data(Qt.ItemDataRole.UserRole)
            self._append_hop(node_id)

    def _remove_selected(self) -> None:
        row = self.hops.currentRow()
        if row >= 0:
            self.hops.takeItem(row)

    def _move_up(self) -> None:
        self._move(-1)

    def _move_down(self) -> None:
        self._move(1)

    def _move(self, offset: int) -> None:
        row = self.hops.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.hops.count():
            return
        item = self.hops.takeItem(row)
        self.hops.insertItem(target, item)
        self.hops.setCurrentRow(target)

    def _validate_and_accept(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Missing name", "Enter a name for this chain.")
            return
        if self.hops.count() == 0:
            QMessageBox.warning(self, "Empty chain", "Add at least one base node.")
            return
        if self.port_input.value() in self.used_ports:
            QMessageBox.warning(self, "Port already in use", "Choose a local port that is not used by the Base listener or another Chain.")
            return
        self.accept()

    def result_values(self) -> tuple[str, list[str], int]:
        return (
            self.name_input.text().strip(),
            [self.hops.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.hops.count())],
            self.port_input.value(),
        )
