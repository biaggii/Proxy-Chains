"""v2rayN-style subscription group add/edit form."""

import json

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from models.subscription import Subscription, SUB_TYPE_AUTO, SUB_TYPE_CLASH, SUB_TYPE_V2RAYN


class SubscriptionEditDialog(QDialog):
    def __init__(self, subscription: Subscription | None = None, parent=None):
        super().__init__(parent)
        self.subscription = subscription
        self.setWindowTitle("Subscription Group" if subscription is None else "Edit Subscription Group")
        self.resize(760, 760)

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.remarks = QLineEdit(subscription.name if subscription else "")
        self.url = QPlainTextEdit(subscription.url if subscription else "")
        self.url.setMaximumHeight(72)
        self.url.setPlaceholderText("https://subscription.example/link?token=...")
        self.sub_type = QComboBox()
        self.sub_type.addItem("Auto", SUB_TYPE_AUTO)
        self.sub_type.addItem("v2rayN", SUB_TYPE_V2RAYN)
        self.sub_type.addItem("Clash", SUB_TYPE_CLASH)
        if subscription:
            self.sub_type.setCurrentIndex(max(0, self.sub_type.findData(subscription.sub_type)))
        self.enable_update = QCheckBox("On")
        self.enable_update.setChecked(subscription.enable_update if subscription else True)
        self.update_interval = QSpinBox()
        self.update_interval.setRange(0, 525600)
        self.update_interval.setSuffix(" min")
        self.update_interval.setValue(subscription.update_interval if subscription else 0)
        self.remarks_filter = QLineEdit(subscription.remarks_filter if subscription else "")
        self.remarks_filter.setPlaceholderText("Leave blank to include all nodes")
        self.convert_target_type = QComboBox()
        self.convert_target_type.addItem("Auto", "auto")
        self.convert_target_type.addItem("sing-box", "sing-box")
        self.convert_target_type.addItem("Xray", "Xray")
        self.convert_target_type.addItem("Mihomo / Clash Meta", "Mihomo / Clash Meta")
        self.convert_target_type.setToolTip(
            "Stored with the subscription for converter compatibility. ChainPort runtime uses the core selected in Settings."
        )
        if subscription and subscription.convert_target_type:
            index = self.convert_target_type.findData(subscription.convert_target_type)
            if index >= 0:
                self.convert_target_type.setCurrentIndex(index)
        self.user_agent = QLineEdit(subscription.user_agent if subscription else "")
        self.user_agent.setPlaceholderText("Leave blank for default User-Agent")
        self.http_headers = QPlainTextEdit(
            json.dumps(subscription.http_headers, ensure_ascii=False, indent=2)
            if subscription and subscription.http_headers else ""
        )
        self.http_headers.setPlaceholderText('{"X-Subscription-Token": "..."}')
        self.http_headers.setMinimumHeight(90)
        self.sort = QSpinBox()
        self.sort.setRange(0, 999999)
        self.sort.setValue(subscription.sort if subscription else 0)

        self.previous_remarks = QLineEdit(subscription.previous_proxy_remarks if subscription else "")
        self.next_remarks = QLineEdit(subscription.next_proxy_remarks if subscription else "")
        self.previous_select = QPushButton("Select Profile")
        self.next_select = QPushButton("Select Profile")
        self.previous_select.clicked.connect(lambda: self._select_profile(self.previous_remarks))
        self.next_select.clicked.connect(lambda: self._select_profile(self.next_remarks))
        self.custom_core = QComboBox()
        self.custom_core.addItems(["", "sing-box", "xray", "mihomo"])
        if subscription:
            self.custom_core.setCurrentText(subscription.custom_config_core)
        self.custom_core.setToolTip(
            "Stored as subscription conversion metadata; it does not override the single runtime core selected in Settings."
        )
        self.custom_socks_port = QSpinBox()
        self.custom_socks_port.setRange(0, 65535)
        self.custom_socks_port.setSpecialValueText("Default / disabled")
        self.custom_socks_port.setValue(subscription.custom_config_socks_port if subscription else 0)
        self.custom_socks_port.setToolTip(
            "Stored as subscription conversion metadata. ChainPort Base Nodes use the shared port configured on the Base tab."
        )
        self.remarks_memo = QLineEdit(subscription.remarks_memo if subscription else "")

        form.addRow("Remarks", self.remarks)
        form.addRow("URL (optional)", self.url)
        form.addRow("Format", self.sub_type)
        update_row = QHBoxLayout()
        update_row.addWidget(self.enable_update)
        update_row.addWidget(QLabel("Automatic update interval"))
        update_row.addWidget(self.update_interval)
        update_row.addStretch()
        form.addRow("Enable update", update_row)
        form.addRow("Remarks regular filter", self.remarks_filter)
        form.addRow("Convert target type", self.convert_target_type)
        form.addRow("User Agent", self.user_agent)
        form.addRow("HTTP headers (JSON)", self.http_headers)
        form.addRow("Sort", self.sort)
        form.addRow("Previous proxy remarks", self._with_button(self.previous_remarks, self.previous_select))
        form.addRow("Next proxy remarks", self._with_button(self.next_remarks, self.next_select))
        form.addRow("Custom config core", self.custom_core)
        form.addRow("Custom config socks port", self.custom_socks_port)
        form.addRow("Remarks Memo", self.remarks_memo)

        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    @staticmethod
    def _with_button(field: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return row

    def _select_profile(self, target: QLineEdit) -> None:
        from PySide6.QtWidgets import QInputDialog

        names = sorted({node.name for node in getattr(self.parent(), "app_state", object()).nodes}) if getattr(self.parent(), "app_state", None) else []
        if not names:
            return
        value, ok = QInputDialog.getItem(self, "Select Profile", "Proxy remarks:", names, 0, False)
        if ok:
            target.setText(value)

    def _validate_and_accept(self) -> None:
        if not self.remarks.text().strip():
            QMessageBox.warning(self, "Missing remarks", "Enter a subscription group name.")
            return
        try:
            headers = json.loads(self.http_headers.toPlainText() or "{}")
            if not isinstance(headers, dict):
                raise ValueError("HTTP headers must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as err:
            QMessageBox.warning(self, "Invalid HTTP headers", str(err))
            return
        if self.remarks_filter.text().strip():
            import re
            try:
                re.compile(self.remarks_filter.text())
            except re.error as err:
                QMessageBox.warning(self, "Invalid remarks filter", str(err))
                return
        self.accept()

    def build_subscription(self) -> Subscription:
        values = {
            "name": self.remarks.text().strip(),
            "url": self.url.toPlainText().strip(),
            "sub_type": self.sub_type.currentData(),
            "enable_update": self.enable_update.isChecked(),
            "update_interval": self.update_interval.value(),
            "remarks_filter": self.remarks_filter.text().strip(),
            "convert_target_type": self.convert_target_type.currentData(),
            "user_agent": self.user_agent.text().strip(),
            "http_headers": json.loads(self.http_headers.toPlainText() or "{}"),
            "sort": self.sort.value(),
            "previous_proxy_remarks": self.previous_remarks.text().strip(),
            "next_proxy_remarks": self.next_remarks.text().strip(),
            "custom_config_core": self.custom_core.currentText(),
            "custom_config_socks_port": self.custom_socks_port.value(),
            "remarks_memo": self.remarks_memo.text(),
        }
        if self.subscription:
            for key, value in values.items():
                setattr(self.subscription, key, value)
            return self.subscription
        return Subscription(**values)
