"""
ui_pages_settings.py — 設定頁面

功能：
  - 選擇核心種類（sing-box / xray / mihomo）
  - 設定核心執行檔路徑
  - 顯示 config 生成路徑
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


class SettingsPage(QWidget):
    """設定頁面"""

    data_changed = Signal()

    def __init__(self, app_state: "AppState", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # ---------- 核心設定 ----------
        core_group = QGroupBox("Core Engine Settings")
        core_form = QFormLayout()

        # 核心類型
        self.combo_core_type = QComboBox()
        self.combo_core_type.addItems(["sing-box", "xray", "mihomo"])
        self.combo_core_type.currentTextChanged.connect(self._on_core_type_changed)
        core_form.addRow("Core Type:", self.combo_core_type)

        # exe 路徑
        exe_row = QHBoxLayout()
        self.input_exe_path = QLineEdit()
        self.input_exe_path.setPlaceholderText("Select Core Executable Path...")
        exe_row.addWidget(self.input_exe_path)
        btn_browse = QPushButton("📁 Browse...")
        btn_browse.clicked.connect(self._on_browse_exe)
        exe_row.addWidget(btn_browse)
        core_form.addRow("Executable Path:", exe_row)

        # config 輸出目錄
        cfg_row = QHBoxLayout()
        self.input_config_dir = QLineEdit()
        cfg_row.addWidget(self.input_config_dir)
        btn_browse_cfg = QPushButton("📁 Browse...")
        btn_browse_cfg.clicked.connect(self._on_browse_config)
        cfg_row.addWidget(btn_browse_cfg)
        core_form.addRow("Config Output Dir:", cfg_row)

        # log level
        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["debug", "info", "warning", "error", "fatal"])
        core_form.addRow("Log Level:", self.combo_log_level)

        # ipv6
        self.check_ipv6 = QCheckBox("Enable IPv6")
        core_form.addRow("", self.check_ipv6)
        
        # 進階設定
        self.check_udp = QCheckBox("Enable UDP Forwarding")
        core_form.addRow("", self.check_udp)
        
        self.check_sniffing = QCheckBox("Enable Sniffing (http/tls)")
        core_form.addRow("", self.check_sniffing)
        
        self.check_allow_lan = QCheckBox("Allow connections from LAN")
        core_form.addRow("", self.check_allow_lan)
        
        self.check_mux = QCheckBox("Enable Mux Multiplexing")
        core_form.addRow("", self.check_mux)
        
        self.check_allow_insecure = QCheckBox("Allow Insecure (Ignore TLS errors)")
        core_form.addRow("", self.check_allow_insecure)
        
        self.combo_singbox_mux = QComboBox()
        self.combo_singbox_mux.addItems(["h2mux", "smux", "yamux"])
        core_form.addRow("sing-box Mux Protocol:", self.combo_singbox_mux)
        
        self.check_fragment = QCheckBox("Enable Fragment")
        core_form.addRow("", self.check_fragment)

        btn_save = QPushButton("💾 Save Settings")
        btn_save.clicked.connect(self._on_save_settings)
        core_form.addRow(btn_save)

        core_group.setLayout(core_form)
        layout.addWidget(core_group)

        # ---------- Startup Settings ----------
        startup_group = QGroupBox("Startup Settings")
        startup_form = QFormLayout()
        
        self.check_run_on_startup = QCheckBox("Run on Windows Startup")
        self.check_run_on_startup.toggled.connect(self._on_run_startup_toggled)
        startup_form.addRow("", self.check_run_on_startup)
        
        self.check_minimize_on_start = QCheckBox("Minimize to Tray on Startup")
        startup_form.addRow("", self.check_minimize_on_start)
        
        startup_group.setLayout(startup_form)
        layout.addWidget(startup_group)

        # ---------- Data Management ----------
        data_group = QGroupBox("Data Management (Import/Export)")
        data_layout = QHBoxLayout()
        
        btn_export = QPushButton("📤 Export Profile")
        btn_export.clicked.connect(self._on_export_data)
        data_layout.addWidget(btn_export)
        
        btn_import = QPushButton("📥 Import Profile")
        btn_import.clicked.connect(self._on_import_data)
        data_layout.addWidget(btn_import)
        
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

        # ---------- 資訊 ----------
        info_group = QGroupBox("Usage Guide")
        info_layout = QVBoxLayout()
        info_text = QLabel(
            "1. Add Subscriptions in 'Subscriptions' page and Update\n"
            "2. Check nodes in 'Nodes' page\n"
            "3. Create chains in 'Chains' page\n"
            "4. Create bindings in 'Ports' page\n"
            "5. Click Apply at the bottom to generate config, then Start Core\n"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

    def refresh_table(self) -> None:
        """從 app_state 讀取設定並更新 UI"""
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
        
        current_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        self.input_exe_path.setText(current_path)
        self.input_config_dir.setText(self.app_state.config_output_dir)

    def _on_run_startup_toggled(self, checked: bool) -> None:
        success = set_autorun(checked)
        if not success:
            QMessageBox.warning(self, "Warning", "Failed to update Windows startup registry.")

    def _on_core_type_changed(self, text: str) -> None:
        """核心類型改變時，嘗試自動尋找 ./bin/ 對應的執行檔"""
        # 第一步：先看看這個核心之前有沒有存過路徑
        saved_path = self.app_state.core_exe_paths.get(text, "")
        if saved_path:
             self.input_exe_path.setText(saved_path)
             return

        # 如果沒有，試著去找它的預設位置
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
        """Browse folder for config output"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Profile Directory", self.app_state.config_output_dir)
        if dir_path:
            self.input_config_dir.setText(dir_path)

    def _on_browse_exe(self) -> None:
        """瀏覽檔案選擇 exe"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Core Executable",
            "",
            "Executable (*.exe);;All Files (*.*)",
        )
        if file_path:
            self.input_exe_path.setText(file_path)

    def _on_save_settings(self) -> None:
        """儲存設定到 app_state"""
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
        self.app_state.config_output_dir = self.input_config_dir.text().strip()
        self.app_state.core_exe_paths[core_type] = self.input_exe_path.text().strip()
        
        # Ensure registry matches
        set_autorun(self.app_state.run_on_startup)
        
        self.data_changed.emit()
        QMessageBox.information(self, "Success", "Settings Saved")

    def _on_export_data(self) -> None:
        """Export state.json"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile",
            os.path.join(self.app_state.config_output_dir, "my_profile.json"),
            "JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
        
        # We can temporarily change state_file_path and save
        original_path = self.app_state.state_file_path
        try:
            self.app_state.state_file_path = file_path
            self.app_state.save_to_file()
            QMessageBox.information(self, "Success", "Profile exported successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Failed", f"Failed to export: {e}")
        finally:
            self.app_state.state_file_path = original_path
            
    def _on_import_data(self) -> None:
        """Import state.json"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile",
            self.app_state.config_output_dir,
            "JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
            
        reply = QMessageBox.question(self, "Confirm Import", "This will overwrite all existing configurations. Continue?")
        if reply == QMessageBox.StandardButton.Yes:
            # Load the chosen file by overwriting app_state
            # We preserve the original state_file_path so auto-saves still go to the normal state file.
            original_path = self.app_state.state_file_path
            try:
                self.app_state.state_file_path = file_path
                self.app_state.load_from_file()
                self.app_state.state_file_path = original_path
                self.app_state.save_to_file()
                self.data_changed.emit() # This triggers UI refresh across all tabs
                self.refresh_table()
                QMessageBox.information(self, "Success", "Profile imported successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Failed", f"Failed to import: {e}")
                self.app_state.state_file_path = original_path
