"""
Subscriptions management page.

Responsibilities:
  - List all configured subscription sources
  - Add and remove sources
  - Refresh one or many sources and import nodes into the workspace
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QLabel, QMessageBox,
    QGroupBox, QFormLayout,
)
from PySide6.QtCore import Qt, Signal
from models.app_state import AppState
from app.ui_kit.feedback import set_feedback_banner


class SubscriptionsPage(QWidget):
    """Manage subscription sources and refresh imported nodes."""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        """Build the page widgets."""
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.feedback_label = QLabel("No source activity yet.")
        self.feedback_label.setWordWrap(True)
        set_feedback_banner(self.feedback_label, "No source activity yet.", "info")
        layout.addWidget(self.feedback_label)

        add_group = QGroupBox("Import Source")
        add_form = QFormLayout()

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g.: Main Provider")
        add_form.addRow("Name:", self.input_name)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://example.com/sub?token=xxx")
        add_form.addRow("URL:", self.input_url)

        self.input_type = QComboBox()
        self.input_type.addItems(["auto", "clash", "v2rayn"])
        add_form.addRow("Type:", self.input_type)

        btn_add = QPushButton("Save Source")
        btn_add.clicked.connect(self._on_add_subscription)
        add_form.addRow(btn_add)

        add_group.setLayout(add_form)
        layout.addWidget(add_group)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "URL", "Type", "Last Update", "Nodes"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()

        btn_update = QPushButton("Update Selected")
        btn_update.clicked.connect(self._on_update_selected)
        btn_row.addWidget(btn_update)

        btn_update_all = QPushButton("Update All")
        btn_update_all.clicked.connect(self._on_update_all)
        btn_row.addWidget(btn_update_all)

        btn_delete = QPushButton("Delete Selected")
        btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

    def refresh(self) -> None:
        """Reload table data from the current application state."""
        self.table.setRowCount(len(self.app_state.subscriptions))
        for row, sub in enumerate(self.app_state.subscriptions):
            self.table.setItem(row, 0, QTableWidgetItem(sub.name))
            self.table.setItem(row, 1, QTableWidgetItem(sub.url))
            self.table.setItem(row, 2, QTableWidgetItem(sub.sub_type))
            self.table.setItem(row, 3, QTableWidgetItem(sub.last_update or "Not Updated"))
            self.table.setItem(row, 4, QTableWidgetItem(str(sub.node_count)))
        if self.app_state.subscriptions:
            self.summary_label.setText(
                f"{len(self.app_state.subscriptions)} source(s) configured. "
                "Keep provider links here. Updating a source refreshes the nodes that appear in the workspace."
            )
        else:
            self.summary_label.setText(
                "No sources configured yet. Add a provider link here, or skip this page and paste nodes directly into the Nodes tab."
            )

    def _on_add_subscription(self) -> None:
        """Handle the add-source action."""
        name = self.input_name.text().strip()
        url = self.input_url.text().strip()
        sub_type = self.input_type.currentText()

        if not name:
            QMessageBox.warning(self, "Notice", "Please enter a subscription name")
            return
        if not url:
            QMessageBox.warning(self, "Notice", "Please enter a subscription URL")
            return

        from models.subscription import Subscription
        new_sub = Subscription(name=name, url=url, sub_type=sub_type)
        self.app_state.subscriptions.append(new_sub)

        self.input_name.clear()
        self.input_url.clear()

        self.refresh()
        set_feedback_banner(self.feedback_label, f"Saved source '{new_sub.name}'.", "success")
        self.data_changed.emit()

    def _on_delete_selected(self) -> None:
        """Delete the selected subscription rows."""
        selected_rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select a subscription to delete")
            return

        deleted_count = 0
        for row in sorted(selected_rows, reverse=True):
            if row < len(self.app_state.subscriptions):
                sub = self.app_state.subscriptions[row]
                self.app_state.remove_subscription_and_nodes(sub.sub_id)
                deleted_count += 1

        self.refresh()
        set_feedback_banner(
            self.feedback_label,
            f"Removed {deleted_count} source(s) and their imported nodes.",
            "info",
        )
        self.data_changed.emit()

    def _on_update_selected(self) -> None:
        """Refresh the currently selected subscription rows."""
        selected_rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select a subscription to update")
            return

        self._do_update_subs(list(selected_rows))

    def _on_update_all(self) -> None:
        """Refresh all configured subscription sources."""
        all_rows = list(range(len(self.app_state.subscriptions)))
        if not all_rows:
            QMessageBox.information(self, "Notice", "No subscriptions to update")
            return
        self._do_update_subs(all_rows)

    def _do_update_subs(self, row_indices: list[int]) -> None:
        """Download and parse the selected sources."""
        from parsers.subscription_fetcher import fetch_and_parse

        all_errors: list[str] = []
        total_new_nodes = 0

        for row in row_indices:
            if row >= len(self.app_state.subscriptions):
                continue
            sub = self.app_state.subscriptions[row]

            self.app_state.nodes = [
                n for n in self.app_state.nodes if n.source_sub != sub.name
            ]

            new_nodes, errors = fetch_and_parse(sub)
            self.app_state.nodes.extend(new_nodes)
            total_new_nodes += len(new_nodes)
            all_errors.extend(errors)

        message = (
            f"Update completed. Imported {total_new_nodes} node(s) from "
            f"{len(row_indices)} source(s)."
        )
        if all_errors:
            message += f"\n\n{len(all_errors)} issue(s) were reported:\n"
            message += "\n".join(all_errors[:5])
            if len(all_errors) > 5:
                message += f"\n...and {len(all_errors) - 5} more"

        self.refresh()
        set_feedback_banner(
            self.feedback_label,
            message,
            "warning" if all_errors else "success",
        )
        self.data_changed.emit()
