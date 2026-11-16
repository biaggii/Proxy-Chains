"""
Main application window.

This module hosts the tab shell, the global action bar, runtime status,
and the shared ``AppState`` wiring across the full desktop UI.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QLabel, QMessageBox,
    QSystemTrayIcon, QStyle, QMenu, QApplication, QDialog,
    QSpinBox,
)
from PySide6.QtGui import QIcon, QAction, QCloseEvent
from PySide6.QtCore import Qt, Signal, Slot, QObject, QEvent, QTimer
import os

from models.app_state import AppState
from core.process_runner import ProcessRunner
from app.ui_kit.feedback import set_feedback_banner

from app.ui_pages_node_groups import NodeGroupsPage
from app.ui_pages_logs import LogsPage
from app.ui_pages_settings import SettingsPage


class LogBridge(QObject):
    """
    Forward process logs from worker threads back to the GUI thread safely.
    """
    log_signal = Signal(str)
    stopped_signal = Signal()


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.process_runner = ProcessRunner()

        self.log_bridge = LogBridge()

        self._init_ui()
        self._init_tray_icon()
        self._connect_signals()
        self._load_and_refresh()
        self._launch_actions_scheduled = False

    def _init_ui(self) -> None:
        """Create the main window widgets.

        All QSS is handled by the centralised theme — no inline
        ``setStyleSheet()`` here.
        """
        self.setWindowTitle("ChainPort Gateway - Proxy Multi-Chain Manager")
        self.setMinimumSize(1040, 720)
        self.resize(1320, 900)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.banner = QLabel()
        self.banner.setObjectName("bannerLabel")
        self.banner.setWordWrap(True)
        self.banner.hide()
        main_layout.addWidget(self.banner)

        self.tabs = QTabWidget()

        self.page_node_groups = NodeGroupsPage(self.app_state)
        self.page_base_nodes = self.page_node_groups.base_page
        self.page_chains = self.page_node_groups.chain_page
        self.page_settings = SettingsPage(self.app_state)

        self.logs_dialog = QDialog(self)
        self.logs_dialog.setWindowTitle("ChainPort Runtime Logs")
        self.logs_dialog.resize(1000, 620)
        logs_layout = QVBoxLayout(self.logs_dialog)
        self.page_logs = LogsPage(self.logs_dialog)
        logs_layout.addWidget(self.page_logs)

        self.tabs.addTab(self.page_node_groups, "Node Groups")
        self.tabs.addTab(self.page_settings, "Settings")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Keep global runtime controls on the same top row as Node Groups / Settings.
        top_controls = QWidget(self.tabs)
        controls_layout = QHBoxLayout(top_controls)
        controls_layout.setContentsMargins(8, 2, 8, 2)
        controls_layout.setSpacing(8)

        self.btn_logs = QPushButton("Logs")
        self.btn_logs.clicked.connect(self.logs_dialog.show)
        controls_layout.addWidget(self.btn_logs)

        self.lbl_status = QLabel("● Stopped")
        self.lbl_status.setStyleSheet("color: gray; font-weight: bold; font-size: 14px;")
        self.lbl_preflight = QLabel("Waiting for configuration data")
        self.lbl_preflight.setToolTip("Core readiness / preflight status")
        self.lbl_context = QLabel("")
        self.lbl_context.setStyleSheet("color: #64748b;")
        controls_layout.addWidget(self.lbl_status)
        controls_layout.addWidget(self.lbl_preflight)

        self.lbl_tun_binding = QLabel("TUN: Not bound")
        self.lbl_tun_binding.setMinimumWidth(105)
        self.lbl_tun_binding.setToolTip("The single node bound to the TUN outbound")
        controls_layout.addWidget(self.lbl_tun_binding)

        self.tun_switch = QPushButton("TUN OFF")
        self.tun_switch.setObjectName("tunSwitch")
        self.tun_switch.setCheckable(True)
        self.tun_switch.setMinimumWidth(82)
        self.tun_switch.toggled.connect(self._on_tun_toggled)
        controls_layout.addWidget(self.tun_switch)

        self.shared_port_label = QLabel("Shared Port")
        self.shared_port = QSpinBox()
        self.shared_port.setRange(1, 65535)
        self.shared_port.setFixedWidth(88)
        self.shared_port.setValue(self.app_state.base_node_listen_port)
        self.shared_port.setToolTip("One shared local proxy port for the selected Base Node")
        self.shared_port.editingFinished.connect(self._save_shared_port)
        controls_layout.addWidget(self.shared_port_label)
        controls_layout.addWidget(self.shared_port)

        self.btn_run_admin = QPushButton("Run as Admin")
        self.btn_run_admin.setMinimumHeight(38)
        self.btn_run_admin.setStyleSheet("QPushButton { background-color: #f59e0b; color: #1f2937; font-weight: bold; }")
        self.btn_run_admin.clicked.connect(self._relaunch_as_admin)
        # The UAC relaunch action is Windows-only. Linux has no ctypes.windll.
        if os.name != "nt" or self._is_admin():
            self.btn_run_admin.hide()
        controls_layout.addWidget(self.btn_run_admin)

        self.btn_run = QPushButton("Start")
        self.btn_run.setObjectName("runToggleButton")
        self.btn_run.setMinimumSize(116, 40)
        self.btn_run.setStyleSheet("QPushButton { background-color: #2d7d46; color: white; font-weight: 700; }")
        self.btn_run.clicked.connect(self._on_run_clicked)
        controls_layout.addWidget(self.btn_run)

        self.tabs.setCornerWidget(top_controls, Qt.Corner.TopRightCorner)
        main_layout.addWidget(self.tabs)

        self.statusBar().showMessage("Workspace ready")

    def _connect_signals(self) -> None:
        """Connect cross-page signals and runtime callbacks."""
        self.page_node_groups.data_changed.connect(self._on_data_changed)
        self.page_node_groups.active_node_changed.connect(self._on_active_base_node_changed)
        self.page_node_groups.runtime_config_changed.connect(self._restart_running_core)
        self.page_settings.data_changed.connect(self._on_data_changed)
        self.log_bridge.log_signal.connect(self.page_logs.append_log)
        self.log_bridge.stopped_signal.connect(self._on_core_exited)

    def _load_and_refresh(self) -> None:
        """Load persisted state and refresh all pages."""
        self.app_state.load_from_file()
        # Persist cross-version migrations (legacy chain wrappers and port rows).
        self.app_state.save_to_file()
        self._refresh_all_pages()

    def _refresh_all_pages(self) -> None:
        """Refresh every page from the latest state."""
        self.page_node_groups.refresh()
        self.page_logs.refresh()
        self.page_settings.refresh()
        self._refresh_action_state()

    def _init_tray_icon(self) -> None:
        """Initialize the system tray icon and menu."""
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icon.ico"))
        app_icon = QIcon(icon_path) if os.path.exists(icon_path) else self.style().standardIcon(QStyle.SP_DriveNetIcon)
        
        self.setWindowIcon(app_icon)
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(app_icon)
        
        tray_menu = QMenu(self)
        
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)
        
        quit_action = QAction("Exit Completely", self)
        quit_action.triggered.connect(self._force_quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        
        self.tray_icon.show()

    def _relaunch_as_admin(self) -> None:
        if os.name != "nt":
            QMessageBox.information(
                self,
                "Not available on this platform",
                "Run ChainPort from a terminal with the required privileges. "
                "The Windows UAC elevation action is not available on Linux.",
            )
            return

        import ctypes
        import sys
        
        try:
            self._on_stop()
            self.app_state.save_to_file()
            
            if getattr(sys, 'frozen', False):
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "", None, 1)
            else:
                import os
                main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
                
                exe_path = sys.executable
                if exe_path.lower().endswith("python.exe"):
                    pythonw_path = exe_path[:-10] + "pythonw.exe"
                    if os.path.exists(pythonw_path):
                        exe_path = pythonw_path
                        
                ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, f'"{main_script}"', None, 1)
                
            self._force_quit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restart as administrator:\n{e}")

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._show_window()

    def _force_quit(self):
        """Exit the application after stopping the tracked core process."""
        if self.process_runner.is_running():
            self._on_stop()
        self.page_base_nodes.shutdown_updates()
        self.app_state.save_to_file()
        self._force_closing = True
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle the window close action based on the tray preference."""
        if getattr(self, '_force_closing', False):
            event.accept()
            return

        if not self.app_state.close_to_tray:
            if self.process_runner.is_running():
                self._on_stop()
            self.page_base_nodes.shutdown_updates()
            self.app_state.save_to_file()
            self._force_closing = True
            event.accept()
            return
            
        event.ignore()
        self.hide()
        
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "ChainPort Gateway",
                "App minimized to tray. Right-click the tray icon to exit entirely.",
                QSystemTrayIcon.Information,
                2000
            )

    def changeEvent(self, event: QEvent) -> None:
        """Hide to tray when minimizing if the tray preference is enabled."""
        if event.type() == QEvent.WindowStateChange and self.app_state.close_to_tray:
            if self.isMinimized():
                self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
                self.hide()
        super().changeEvent(event)

    @Slot()
    def _on_data_changed(self) -> None:
        """Persist state changes and refresh dependent pages."""
        self.app_state.save_to_file()
        self.statusBar().showMessage("Auto-saved", 3000)
        self._refresh_all_pages()

    @Slot(str)
    def _on_active_base_node_changed(self, node_id: str) -> None:
        """Reapply the shared base listener/TUN route when the selected node changes."""
        self.app_state.save_to_file()
        self.page_logs.append_log(
            f"[Base] Active node: {node_id or 'None'}; shared port remains "
            f"{self.app_state.base_node_listen_host}:{self.app_state.base_node_listen_port}."
        )
        if not self._restart_running_core():
            self._refresh_all_pages()

    @Slot()
    def _restart_running_core(self) -> bool:
        """Regenerate and restart a running core after its active routes change."""
        if not self.process_runner.is_running():
            return False
        self._on_stop()
        QTimer.singleShot(250, lambda: self._start_core(interactive=False))
        return True

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        """Refresh the active page when the current tab changes."""
        page = self.tabs.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()
        self._refresh_action_state()

    @Slot()
    def _on_start(self) -> None:
        """Generate config files and start the selected core."""
        self._start_core(interactive=True)

    @Slot()
    def _on_run_clicked(self) -> None:
        if self.process_runner.is_running():
            self._on_stop()
        else:
            self._on_start()

    @Slot(bool)
    def _on_tun_toggled(self, checked: bool) -> None:
        if checked and self.app_state.get_tun_node() is None:
            QMessageBox.warning(
                self, "Bind a node",
                "Right-click a Base Node or an individual Chain hop and choose 'Bind TUN' first.",
            )
            self.tun_switch.blockSignals(True)
            self.tun_switch.setChecked(False)
            self.tun_switch.blockSignals(False)
            return
        if self.app_state.enable_tun == checked:
            return
        self.app_state.enable_tun = checked
        self._on_data_changed()
        self._restart_running_core()

    def _save_shared_port(self) -> None:
        port = self.shared_port.value()
        if any(mapping.listen_port == port for mapping in self.app_state.port_mappings):
            QMessageBox.warning(
                self, "Port already in use",
                "This port is already assigned to a Chain. Choose another port.",
            )
            self.shared_port.blockSignals(True)
            self.shared_port.setValue(self.app_state.base_node_listen_port)
            self.shared_port.blockSignals(False)
            return
        if port == self.app_state.base_node_listen_port:
            return
        self.app_state.base_node_listen_port = port
        self.app_state.save_to_file()
        self.page_base_nodes.refresh()
        self.page_logs.append_log(
            f"[Base] Shared local proxy port changed to "
            f"{self.app_state.base_node_listen_host}:{port}."
        )
        self._refresh_action_state()
        self._restart_running_core()

    def _refresh_global_controls(self) -> None:
        self.tun_switch.blockSignals(True)
        self.tun_switch.setChecked(self.app_state.enable_tun)
        self.tun_switch.setText("TUN ON" if self.app_state.enable_tun else "TUN OFF")
        self.tun_switch.setStyleSheet(
            "QPushButton { background-color: #1f4b99; color: white; font-weight: 700; }"
            if self.app_state.enable_tun else ""
        )
        self.tun_switch.blockSignals(False)
        bound = self.app_state.get_tun_node()
        self.lbl_tun_binding.setText(f"TUN: {bound.name}" if bound else "TUN: Not bound")
        self.lbl_tun_binding.setToolTip(
            f"Bound node: {bound.name} ({bound.node_type})" if bound else "No node is bound to TUN"
        )
        self.shared_port.blockSignals(True)
        self.shared_port.setValue(self.app_state.base_node_listen_port)
        self.shared_port.blockSignals(False)

    @Slot()
    def _on_core_exited(self) -> None:
        """Update UI state after the core process exits."""
        self._update_status(False)
        self.statusBar().showMessage("Core Exited", 3000)
        self._show_banner("Core process exited.", "info")
        self._refresh_action_state()

    @Slot()
    def _on_stop(self) -> None:
        """Stop the tracked core process if it is running."""
        if self.process_runner.is_running():
            self.process_runner.stop()
        
        self._update_status(False)
        self.statusBar().showMessage("Core Stopped", 3000)
        self._show_banner("Core stopped.", "info")
        self._refresh_action_state()

    def _get_current_adapter(self, show_message: bool = True):
        """Return the adapter for the currently selected core type."""
        core_type = self.app_state.core_type

        if core_type == "sing-box":
            from core.singbox_adapter import SingBoxAdapter
            return SingBoxAdapter()
        elif core_type == "xray":
            from core.xray_adapter import XrayAdapter
            return XrayAdapter()
        elif core_type == "mihomo":
            from core.mihomo_adapter import MihomoAdapter
            return MihomoAdapter()
        else:
            if show_message:
                QMessageBox.warning(self, "Error", f"Unknown core type: {core_type}")
            return None

    def schedule_launch_actions(self) -> None:
        """Run any deferred startup actions after the window is created."""
        if self._launch_actions_scheduled:
            return
        self._launch_actions_scheduled = True
        QTimer.singleShot(0, self._run_launch_actions)

    def _run_launch_actions(self) -> None:
        if self.app_state.auto_start_core:
            self._start_core(interactive=False)

    def _start_core(self, interactive: bool) -> bool:
        if self.process_runner.is_running():
            if interactive:
                QMessageBox.information(self, "Notice", "Core is already running")
            else:
                self.page_logs.append_log("[Launch] Core is already running. Auto-start skipped.")
            return False

        preflight = self._get_preflight_state()
        if not preflight["can_start"]:
            message = str(preflight["detail"])
            self._show_banner(message, "warning")
            if interactive:
                QMessageBox.warning(self, "Action Needed", message)
            else:
                self._notify_launch_issue(f"Auto-start skipped: {message}", "warning")
            return False

        exe_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        adapter = self._get_current_adapter(show_message=interactive)
        if adapter is None:
            if not interactive:
                self._notify_launch_issue("Auto-start skipped: unknown core type.", "error")
            return False

        # Only generate config for the selected adapter (P2 fix: no more wasteful triple-gen).
        try:
            _, config_path = adapter.generate_config(self.app_state)
            self.page_logs.append_log(f"[Start] ✅ Config generated: {config_path}")
            check_cmd = adapter.get_check_command(config_path, exe_path)
            valid, validation_output = self.process_runner.run_and_wait(check_cmd)
            if not valid:
                self.page_logs.append_log(
                    f"[Start] Configuration validation failed:\n{validation_output}"
                )
                raise RuntimeError(f"Configuration validation failed:\n{validation_output}")
            self.page_logs.append_log("[Start] Configuration validation passed.")
        except Exception as err:
            if interactive:
                QMessageBox.critical(self, "Error", f"Config generation failed: {err}")
            else:
                self._notify_launch_issue(f"Auto-start failed while generating config: {err}", "error")
            return False

        start_cmd = adapter.get_start_command(config_path, exe_path)

        def on_log_from_thread(text: str) -> None:
            self.log_bridge.log_signal.emit(text)

        def on_exit_from_thread() -> None:
            self.log_bridge.stopped_signal.emit()

        started = self.process_runner.start(
            start_cmd,
            on_log=on_log_from_thread,
            on_exit=on_exit_from_thread,
        )
        if not started:
            self._update_status(False)
            self.statusBar().showMessage("Core Start Failed", 3000)
            self._open_tab("logs")
            if interactive:
                QMessageBox.warning(
                    self,
                    "Start Failed",
                    "Core process failed to start. Check the Logs tab for details.",
                )
                self._show_banner("Core process failed to start. Check the Logs tab for details.", "error")
            else:
                self._notify_launch_issue("Auto-start failed. Check the Logs tab for details.", "error")
            return False

        self._update_status(True)
        self.statusBar().showMessage("Core Started", 3000)
        self._show_banner("Core started successfully. Live output is available in Logs.", "success")
        if interactive:
            self._open_tab("logs")
        else:
            self.page_logs.append_log("[Launch] Core started automatically on app launch.")
            if self.tray_icon.isVisible() and not self.isVisible():
                self.tray_icon.showMessage(
                    "ChainPort Gateway",
                    "Core started automatically after launch.",
                    QSystemTrayIcon.Information,
                    3000,
                )
        self._refresh_action_state()
        return True

    def _notify_launch_issue(self, message: str, level: str) -> None:
        self._show_banner(message, level)
        self.statusBar().showMessage(message, 5000)
        self.page_logs.append_log(f"[Launch] {message}")
        if self.tray_icon.isVisible():
            icon = QSystemTrayIcon.Warning if level == "warning" else QSystemTrayIcon.Critical
            self.tray_icon.showMessage("ChainPort Gateway", message, icon, 4000)
        if not self.isVisible():
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def _update_status(self, is_running: bool) -> None:
        """Update the runtime status label in the global action bar."""
        if is_running:
            self.lbl_status.setText("● Running")
            self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.lbl_status.setText("● Stopped")
            self.lbl_status.setStyleSheet("color: gray; font-weight: bold;")
        self._refresh_action_state()

    def _show_banner(self, message: str, level: str = "info") -> None:
        """Show a feedback banner at the top of the window."""
        set_feedback_banner(self.banner, message, level)
        self.banner.show()

    def _open_tab(self, key: str) -> None:
        if key == "logs":
            self.logs_dialog.show()
            self.logs_dialog.raise_()
            self.logs_dialog.activateWindow()
            return
        if key in {"settings"}:
            self.tabs.setCurrentWidget(self.page_settings)
            return
        self.tabs.setCurrentWidget(self.page_node_groups)

    def _is_admin(self) -> bool:
        if os.name == "nt":
            import ctypes

            try:
                return bool(ctypes.windll.shell32.IsUserAnAdmin())
            except (AttributeError, OSError):
                return False

        # On POSIX, root is UID 0. This is used only for status/preflight;
        # never attempt to invoke Windows UAC APIs.
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def _get_preflight_state(self) -> dict[str, object]:
        exe_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        valid_chain_ids = {
            chain.chain_id
            for chain in self.app_state.chains
            if chain.hop_node_ids and self.app_state.get_nodes_for_chain(chain)
        }
        valid_mapping_count = sum(
            1 for mapping in self.app_state.port_mappings if mapping.chain_id in valid_chain_ids
        )
        blockers: list[str] = []
        active_base_node = self.app_state.get_active_base_node()
        if active_base_node is None and valid_mapping_count == 0:
            blockers.append("No active Base Node or valid Chain endpoint is available.")

        if not exe_path or not os.path.isfile(exe_path):
            blockers.append("The selected core executable was not found. Choose it in Settings.")

        if self.app_state.enable_tun:
            if self.app_state.get_tun_node() is None:
                blockers.append("TUN requires one node bound from the Base or Chain tab.")
            elif not self._is_admin():
                required = "Run as Administrator" if os.name == "nt" else "restart ChainPort with sudo"
                blockers.append(f"TUN requires elevated privileges; {required} before starting.")

        can_start = not blockers
        title = "Ready" if can_start else "Action required"
        detail = blockers[0] if blockers else "Configuration is ready."
        next_step = (
            "Start the core. Configuration is generated and validated automatically."
            if can_start
            else "Resolve the issue above, then choose Start again."
        )
        return {
            "title": title,
            "detail": detail,
            "next_step": next_step,
            "can_start": can_start,
        }

    def _refresh_action_state(self) -> None:
        preflight = self._get_preflight_state()
        is_running = self.process_runner.is_running()
        self.btn_run.setText("Stop" if is_running else "Start")
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: 700; }"
            if is_running else
            "QPushButton { background-color: #2d7d46; color: white; font-weight: 700; }"
        )
        self.btn_run.setEnabled(is_running or bool(preflight["can_start"]))
        self.btn_run_admin.setVisible(
            os.name == "nt" and self.app_state.enable_tun and not self._is_admin()
        )
        self.lbl_preflight.setText(str(preflight["title"]))
        self.lbl_preflight.setToolTip(str(preflight["detail"]))
        self.lbl_context.setText(f"{preflight['detail']} Next: {preflight['next_step']}")
        self._refresh_global_controls()
