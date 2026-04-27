"""
Application settings page.

Responsibilities:
  - Choose the active core engine
  - Configure executable and config output paths
  - Adjust startup, advanced network, and profile import/export options

NOTE: The "Quick Start" guide lives exclusively on the Dashboard.
      It is NOT duplicated here.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QLineEdit, QFileDialog,
    QGroupBox, QFormLayout, QMessageBox, QCheckBox,
    QScrollArea
)
import json
import os
from PySide6.QtCore import Signal
from models.app_state import AppState
from utils.autorun import set_autorun
from app.ui_kit.feedback import set_feedback_banner


class SettingsPage(QWidget):
    """Configure runtime, startup, and profile settings."""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        self.feedback_label = QLabel("Review the Home tab for readiness hints after saving settings.")
        self.feedback_label.setWordWrap(True)
        set_feedback_banner(
            self.feedback_label,
            "Review the Home tab for readiness hints after saving settings.",
            "info",
        )
        main_layout.addWidget(self.feedback_label)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        core_group = QGroupBox("Basic Setup")
        core_form = QFormLayout()

        self.combo_core_type = QComboBox()
        self.combo_core_type.addItems(["sing-box", "xray", "mihomo"])
        self.combo_core_type.currentTextChanged.connect(self._on_core_type_changed)
        core_form.addRow("Core Type:", self.combo_core_type)

        exe_row = QHBoxLayout()
        self.input_exe_path = QLineEdit()
        self.input_exe_path.setPlaceholderText("Select a core executable path")
        exe_row.addWidget(self.input_exe_path)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._on_browse_exe)
        exe_row.addWidget(btn_browse)
        core_form.addRow("Executable Path:", exe_row)

        cfg_row = QHBoxLayout()
        self.input_config_dir = QLineEdit()
        cfg_row.addWidget(self.input_config_dir)
        btn_browse_cfg = QPushButton("Browse")
        btn_browse_cfg.clicked.connect(self._on_browse_config)
        cfg_row.addWidget(btn_browse_cfg)
        core_form.addRow("Config Output Dir:", cfg_row)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["debug", "info", "warning", "error", "fatal"])
        core_form.addRow("Log Level:", self.combo_log_level)

        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self._on_save_settings)
        core_form.addRow(btn_save)

        core_group.setLayout(core_form)
        layout.addWidget(core_group)

        advanced_group = QGroupBox("Advanced Network Options")
        advanced_form = QFormLayout()

        self.check_ipv6 = QCheckBox("Enable IPv6")
        advanced_form.addRow("", self.check_ipv6)

        self.check_udp = QCheckBox("Enable UDP Forwarding")
        advanced_form.addRow("", self.check_udp)

        self.check_sniffing = QCheckBox("Enable Sniffing (HTTP/TLS)")
        advanced_form.addRow("", self.check_sniffing)

        self.check_allow_lan = QCheckBox("Allow connections from LAN")
        advanced_form.addRow("", self.check_allow_lan)

        self.check_mux = QCheckBox("Enable Mux Multiplexing")
        advanced_form.addRow("", self.check_mux)

        self.check_allow_insecure = QCheckBox("Allow insecure TLS")
        advanced_form.addRow("", self.check_allow_insecure)

        self.combo_singbox_mux = QComboBox()
        self.combo_singbox_mux.addItems(["h2mux", "smux", "yamux"])
        advanced_form.addRow("sing-box Mux Protocol:", self.combo_singbox_mux)

        self.check_fragment = QCheckBox("Enable Fragment")
        advanced_form.addRow("", self.check_fragment)

        advanced_hint = QLabel(
            "Leave most advanced options at their defaults unless your provider or route requires a change."
        )
        advanced_hint.setWordWrap(True)
        advanced_form.addRow("", advanced_hint)

        advanced_group.setLayout(advanced_form)
        layout.addWidget(advanced_group)

        startup_group = QGroupBox("Startup and Window")
        startup_form = QFormLayout()
        
        self.check_run_on_startup = QCheckBox("Run on Windows Startup")
        self.check_run_on_startup.toggled.connect(self._on_run_startup_toggled)
        startup_form.addRow("", self.check_run_on_startup)
        
        self.check_minimize_on_start = QCheckBox("Minimize to Tray on Startup")
        startup_form.addRow("", self.check_minimize_on_start)

        self.check_auto_start_core = QCheckBox("Start Core Automatically on App Launch")
        self.check_auto_start_core.setToolTip(
            "The app will refresh config files and start the selected core when it launches. "
            "Automatic launch starts chains only and does not enable TUN."
        )
        startup_form.addRow("", self.check_auto_start_core)

        self.check_close_to_tray = QCheckBox("Close to Tray Instead of Exiting")
        startup_form.addRow("", self.check_close_to_tray)
        
        startup_group.setLayout(startup_form)
        layout.addWidget(startup_group)

        data_group = QGroupBox("Data Management")
        data_layout = QHBoxLayout()
        
        btn_export = QPushButton("Export Profile")
        btn_export.clicked.connect(self._on_export_data)
        data_layout.addWidget(btn_export)
        
        btn_import = QPushButton("Import Profile")
        btn_import.clicked.connect(self._on_import_data)
        data_layout.addWidget(btn_import)
        
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

        # Quick Start guide removed — it lives exclusively on Dashboard.

        layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

    def refresh(self) -> None:
        """Load settings from ``app_state`` into the form."""
        self.combo_core_type.setCurrentText(self.app_state.core_type)
        self.combo_log_level.setCurrentText(self.app_state.log_level)
        self.check_ipv6.setChecked(self.app_state.enable_ipv6)
        self.check_udp.setChecked(self.app_state.enable_udp)
        self.check_sniffing.setChecked(self.app_state.enable_sniffing)
        self.check_allow_lan.setChecked(self.app_state.allow_lan)
        self.check_mux.setChecked(self.app_state.enable_mux)
        self.check_allow_insecure.setChecked(self.app_state.allow_insecure)
        self.combo_singbox_mux.setCurrentText(self.app_state.singbox_mux_protocol)
        self.check_fragment.setChecked(self.app_state.enable_fragment)
        self.check_run_on_startup.setChecked(self.app_state.run_on_startup)
        self.check_minimize_on_start.setChecked(self.app_state.minimize_on_start)
        self.check_auto_start_core.setChecked(self.app_state.auto_start_core)
        self.check_close_to_tray.setChecked(self.app_state.close_to_tray)
        
        current_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        self.input_exe_path.setText(current_path)
        self.input_config_dir.setText(self.app_state.config_output_dir)

    def _on_run_startup_toggled(self, checked: bool) -> None:
        success = set_autorun(checked)
        if not success:
            QMessageBox.warning(self, "Warning", "Failed to update Windows startup registry.")

    def _on_core_type_changed(self, text: str) -> None:
        """Try to resolve a sensible executable path for the chosen core."""
        saved_path = self.app_state.core_exe_paths.get(text, "")
        if saved_path:
             self.input_exe_path.setText(saved_path)
             return

        default_path = self.app_state._get_default_exe_path(text)
        if default_path:
            self.input_exe_path.setText(default_path)
            self.app_state.core_exe_paths[text] = default_path
        else:
            self.input_exe_path.clear()
            hints = {
                "sing-box": "sing-box.exe",
                "xray": "xray.exe",
                "mihomo": "mihomo.exe",
            }
            self.input_exe_path.setPlaceholderText(
                f"Select {hints.get(text, '')} path"
            )

    def _on_browse_config(self) -> None:
        """Browse for the config output directory."""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Profile Directory", self.app_state.config_output_dir)
        if dir_path:
            self.input_config_dir.setText(dir_path)

    def _on_browse_exe(self) -> None:
        """Browse for a core executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Core Executable",
            "",
            "Executable (*.exe);;All Files (*.*)",
        )
        if file_path:
            self.input_exe_path.setText(file_path)

    def _on_save_settings(self) -> None:
        """Persist the form values back into ``app_state``."""
        core_type = self.combo_core_type.currentText()
        self.app_state.core_type = core_type
        self.app_state.log_level = self.combo_log_level.currentText()
        self.app_state.enable_ipv6 = self.check_ipv6.isChecked()
        self.app_state.enable_udp = self.check_udp.isChecked()
        self.app_state.enable_sniffing = self.check_sniffing.isChecked()
        self.app_state.allow_lan = self.check_allow_lan.isChecked()
        self.app_state.enable_mux = self.check_mux.isChecked()
        self.app_state.allow_insecure = self.check_allow_insecure.isChecked()
        self.app_state.singbox_mux_protocol = self.combo_singbox_mux.currentText()
        self.app_state.enable_fragment = self.check_fragment.isChecked()
        self.app_state.run_on_startup = self.check_run_on_startup.isChecked()
        self.app_state.minimize_on_start = self.check_minimize_on_start.isChecked()
        self.app_state.auto_start_core = self.check_auto_start_core.isChecked()
        self.app_state.close_to_tray = self.check_close_to_tray.isChecked()
        self.app_state.config_output_dir = self.input_config_dir.text().strip()
        self.app_state.core_exe_paths[core_type] = self.input_exe_path.text().strip()
        
        set_autorun(self.app_state.run_on_startup)
        
        self.data_changed.emit()
        set_feedback_banner(
            self.feedback_label,
            "Settings saved. Re-apply or restart the core if runtime behavior changed.",
            "success",
        )

    def _on_export_data(self) -> None:
        """Export the current profile to a JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile",
            os.path.join(self.app_state.config_output_dir, "chainport_profile.json"),
            "JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
        
        original_path = self.app_state.state_file_path
        try:
            self.app_state.state_file_path = file_path
            self.app_state.save_to_file()
            set_feedback_banner(self.feedback_label, f"Profile exported to {file_path}.", "success")
        except Exception as e:
            QMessageBox.warning(self, "Failed", f"Failed to export: {e}")
        finally:
            self.app_state.state_file_path = original_path
            
    def _on_import_data(self) -> None:
        """Import a previously exported profile file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile",
            self.app_state.config_output_dir,
            "JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
        
        reply = QMessageBox.question(self, "Confirm Import", "This will overwrite all existing configurations. Continue?")
        if reply == QMessageBox.StandardButton.Yes:
            original_path = self.app_state.state_file_path
            try:
                self.app_state.state_file_path = file_path
                self.app_state.load_from_file()
                self.app_state.state_file_path = original_path
                self.app_state.save_to_file()
                self.data_changed.emit()
                self.refresh()
                set_feedback_banner(self.feedback_label, f"Profile imported from {file_path}.", "success")
            except Exception as e:
                QMessageBox.warning(self, "Failed", f"Failed to import: {e}")
                self.app_state.state_file_path = original_path
