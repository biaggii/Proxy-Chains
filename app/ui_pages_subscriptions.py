"""
ui_pages_subscriptions.py — 訂閱管理頁面

功能：
  - 顯示所有訂閱（表格：名稱、URL、類型、上次更新、節點數）
  - 新增訂閱（名稱 + URL + 類型）
  - 刪除選中的訂閱
  - Update Now（下載 + 解析 + 存入 state）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QLabel, QMessageBox,
    QGroupBox, QFormLayout,
)
from PySide6.QtCore import Qt, Signal
from models.app_state import AppState


class SubscriptionsPage(QWidget):
    """訂閱管理頁面"""

    # 當訂閱更新後，通知主窗口刷新其他頁面
    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        """建立 UI 元件"""
        layout = QVBoxLayout(self)

        # ---------- 新增區域 ----------
        add_group = QGroupBox("Add Subscription")
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

        btn_add = QPushButton("➕ Add Subscription")
        btn_add.clicked.connect(self._on_add_subscription)
        add_form.addRow(btn_add)

        add_group.setLayout(add_form)
        layout.addWidget(add_group)

        # ---------- 訂閱列表 ----------
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
        layout.addWidget(self.table)

        # ---------- 按鈕列 ----------
        btn_row = QHBoxLayout()

        btn_update = QPushButton("🔄 Update Selected (Download & Parse)")
        btn_update.clicked.connect(self._on_update_selected)
        btn_row.addWidget(btn_update)

        btn_update_all = QPushButton("🔄 Update All")
        btn_update_all.clicked.connect(self._on_update_all)
        btn_row.addWidget(btn_update_all)

        btn_delete = QPushButton("🗑️ Delete Selected")
        btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

    def refresh_table(self) -> None:
        """重新載入表格資料"""
        self.table.setRowCount(len(self.app_state.subscriptions))
        for row, sub in enumerate(self.app_state.subscriptions):
            self.table.setItem(row, 0, QTableWidgetItem(sub.name))
            self.table.setItem(row, 1, QTableWidgetItem(sub.url))
            self.table.setItem(row, 2, QTableWidgetItem(sub.sub_type))
            self.table.setItem(row, 3, QTableWidgetItem(sub.last_update or "Not Updated"))
            self.table.setItem(row, 4, QTableWidgetItem(str(sub.node_count)))

    def _on_add_subscription(self) -> None:
        """新增訂閱按鈕的事件"""
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

        # 清空輸入欄
        self.input_name.clear()
        self.input_url.clear()

        self.refresh_table()
        self.data_changed.emit()

    def _on_delete_selected(self) -> None:
        """刪除選中的訂閱"""
        selected_rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select a subscription to delete")
            return

        # 從大到小刪，避免 index 錯位
        for row in sorted(selected_rows, reverse=True):
            if row < len(self.app_state.subscriptions):
                sub = self.app_state.subscriptions[row]
                self.app_state.remove_subscription_and_nodes(sub.sub_id)

        self.refresh_table()
        self.data_changed.emit()

    def _on_update_selected(self) -> None:
        """更新選中的訂閱"""
        selected_rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "Notice", "Please select a subscription to update")
            return

        self._do_update_subs(list(selected_rows))

    def _on_update_all(self) -> None:
        """更新全部訂閱"""
        all_rows = list(range(len(self.app_state.subscriptions)))
        if not all_rows:
            QMessageBox.information(self, "Notice", "No subscriptions to update")
            return
        self._do_update_subs(all_rows)

    def _do_update_subs(self, row_indices: list[int]) -> None:
        """實際執行下載並解析"""
        from parsers.subscription_fetcher import fetch_and_parse

        all_errors: list[str] = []
        total_new_nodes = 0

        for row in row_indices:
            if row >= len(self.app_state.subscriptions):
                continue
            sub = self.app_state.subscriptions[row]

            # 先移除舊節點
            self.app_state.nodes = [
                n for n in self.app_state.nodes if n.source_sub != sub.name
            ]

            # 下載並解析
            new_nodes, errors = fetch_and_parse(sub)
            self.app_state.nodes.extend(new_nodes)
            total_new_nodes += len(new_nodes)
            all_errors.extend(errors)

        # 顯示結果
        msg = f"Update completed! Fetched {total_new_nodes} nodes."
        if all_errors:
            msg += f"\n\n⚠️ {len(all_errors)} Errors encountered:\n"
            msg += "\n".join(all_errors[:10])
            if len(all_errors) > 10:
                msg += f"\n...and {len(all_errors) - 10} more errors"

        QMessageBox.information(self, "Update Result", msg)

        self.refresh_table()
        self.data_changed.emit()
