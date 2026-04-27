"""
Main application window.

This module hosts the tab shell, the global action bar, runtime status,
and the shared ``AppState`` wiring across the full desktop UI.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QLabel, QMessageBox,
    QStatusBar, QSystemTrayIcon, QStyle, QMenu, QApplication
)
from PySide6.QtGui import QIcon, QAction, QCloseEvent
from PySide6.QtCore import Qt, Signal, Slot, QObject, QEvent, QTimer
import os

from models.app_state import AppState
from core.process_runner import ProcessRunner
from app.ui_kit.feedback import set_feedback_banner

from app.ui_pages_subscriptions import SubscriptionsPage
from app.ui_pages_nodes import NodesPage
from app.ui_pages_chains import ChainsPage
from app.ui_pages_ports import PortsPage
from app.ui_pages_logs import LogsPage
from app.ui_pages_settings import SettingsPage
from app.ui_pages_dashboard import DashboardPage
from app.ui_pages_routing import RoutingPage


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
        self.setMinimumSize(1120, 820)
        self.resize(1200, 860)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.banner = QLabel()
        self.banner.setObjectName("bannerLabel")
        self.banner.setWordWrap(True)
        self.banner.hide()
        main_layout.addWidget(self.banner)

        self.tabs = QTabWidget()

        self.page_dashboard = DashboardPage(self.app_state)
        self.page_subs = SubscriptionsPage(self.app_state)
        self.page_nodes = NodesPage(self.app_state)
        self.page_chains = ChainsPage(self.app_state)
        self.page_ports = PortsPage(self.app_state)
        self.page_routing = RoutingPage(self.app_state, self.page_chains, self.page_ports)
        self.page_logs = LogsPage()
        self.page_settings = SettingsPage(self.app_state)

        self.tabs.addTab(self.page_dashboard, "Home")
        self.tabs.addTab(self.page_subs, "Subscriptions")
        self.tabs.addTab(self.page_nodes, "Nodes")
        self.tabs.addTab(self.page_routing, "Routing")
        self.tabs.addTab(self.page_logs, "Logs")
        self.tabs.addTab(self.page_settings, "Settings")
        self._tab_widgets = {
            "dashboard": self.page_dashboard,
            "subscriptions": self.page_subs,
            "nodes": self.page_nodes,
            "routing": self.page_routing,
            "logs": self.page_logs,
            "settings": self.page_settings,
        }

        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

        bottom_row = QHBoxLayout()

        status_stack = QVBoxLayout()
        self.lbl_status = QLabel("● Stopped")
        self.lbl_status.setStyleSheet("color: gray; font-weight: bold; font-size: 14px;")
        self.lbl_preflight = QLabel("Waiting for configuration data")
        self.lbl_preflight.setWordWrap(True)
        self.lbl_context = QLabel("")
        self.lbl_context.setStyleSheet("color: #64748b;")
        status_stack.addWidget(self.lbl_status)
        status_stack.addWidget(self.lbl_preflight)
        status_stack.addWidget(self.lbl_context)
        bottom_row.addLayout(status_stack)

        bottom_row.addStretch()

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setMinimumHeight(36)
        self.btn_apply.clicked.connect(self._on_apply)
        
        self.btn_run_admin = QPushButton("Run as Admin")
        self.btn_run_admin.setMinimumHeight(36)
        self.btn_run_admin.setStyleSheet("QPushButton { background-color: #f59e0b; color: #1f2937; font-weight: bold; }")
        self.btn_run_admin.clicked.connect(self._relaunch_as_admin)
        
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            self.btn_run_admin.hide()
            
        bottom_row.addWidget(self.btn_run_admin)
        bottom_row.addWidget(self.btn_apply)

        self.btn_start = QPushButton("Start")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.setStyleSheet("QPushButton { background-color: #2d7d46; color: white; font-weight: 600; }")
        self.btn_start.clicked.connect(self._on_start)
        bottom_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.setStyleSheet("QPushButton { background-color: #c0392b; color: white; font-weight: 600; }")
        self.btn_stop.clicked.connect(self._on_stop)
        bottom_row.addWidget(self.btn_stop)

        main_layout.addLayout(bottom_row)

        self.statusBar().showMessage("Workspace ready")

    def _connect_signals(self) -> None:
        """Connect cross-page signals and runtime callbacks."""
        self.page_subs.data_changed.connect(self._on_data_changed)
        self.page_nodes.data_changed.connect(self._on_data_changed)
        self.page_chains.data_changed.connect(self._on_data_changed)
        self.page_ports.data_changed.connect(self._on_data_changed)
        self.page_settings.data_changed.connect(self._on_data_changed)
        self.page_dashboard.navigate_requested.connect(self._open_tab)

        self.log_bridge.log_signal.connect(self.page_logs.append_log)
        self.log_bridge.stopped_signal.connect(self._on_core_exited)

    def _load_and_refresh(self) -> None:
        """Load persisted state and refresh all pages."""
        self.app_state.load_from_file()
        self._refresh_all_pages()

    def _refresh_all_pages(self) -> None:
        """Refresh every page from the latest state."""
        self.page_dashboard.refresh()
        self.page_subs.refresh()
        self.page_nodes.refresh()
        self.page_chains.refresh()
        self.page_ports.refresh()
        self.page_routing.refresh()
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

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        """Refresh the active page when the current tab changes."""
        page = self.tabs.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()
        self._refresh_action_state()

    @Slot()
    def _on_apply(self) -> None:
        """Generate and verify the current core configuration."""
        adapter = self._get_current_adapter()
        if adapter is None:
            return

        preflight = self._get_preflight_state()
        if not preflight["can_apply"]:
            self._show_banner(preflight["detail"], "warning")
            QMessageBox.warning(self, "Action Needed", preflight["detail"])
            return

        try:
            config_text, config_path = adapter.generate_config(self.app_state)
        except Exception as err:
            QMessageBox.critical(self, "Config Generation Failed", str(err))
            return

        exe_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        if exe_path:
            check_cmd = adapter.get_check_command(config_path, exe_path)
            success, output = self.process_runner.run_and_wait(check_cmd)
            if success:
                self.page_logs.append_log(f"[Verify] ✅ Config verified")
                self.page_logs.append_log(f"[Verify] Config file: {config_path}")
                QMessageBox.information(
                    self, "Apply Success",
                    f"✅ Config generated and verified successfully!\n\n"
                    f"File: {config_path}\n"
                    f"Ports mapped: {len(self.app_state.port_mappings)}"
                )
                self._show_banner("Configuration generated and verified successfully.", "success")
            else:
                self.page_logs.append_log(f"[Verify] ❌ Config verification failed:")
                self.page_logs.append_log(output)

                error_msg = f"Config verification failed!\n\n{output[:500]}"
                if "Access is denied" in output and self.app_state.enable_tun:
                    error_msg = "🚨 Administrator Privileges Required!\n\nYou have enabled TUN Mode which creates virtual network interfaces.\nYou MUST right-click the terminal/command prompt and 'Run as Administrator' for sing-box/mihomo to work."

                QMessageBox.warning(
                    self, "Verification Failed", error_msg
                )
                self._show_banner("Configuration verification failed. Review the logs for details.", "error")
        else:
            self.page_logs.append_log(f"[Apply] Config generated: {config_path}")
            self.page_logs.append_log("[Apply] ⚠️ Core path not set, skipping verification")
            QMessageBox.information(
                self, "Apply",
                f"Config generated (Not verified due to missing core path)\n\nFile: {config_path}"
            )
            self._show_banner("Configuration generated. Add a core executable path to enable verification.", "info")

        self.app_state.save_to_file()
        self._refresh_action_state()

    @Slot()
    def _on_start(self) -> None:
        """Generate config files and start the selected core."""
        self._start_core(interactive=True)

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
            if self.app_state.enable_tun:
                self.app_state.enable_tun = False
                self.page_logs.append_log(
                    "[Launch] TUN mode was disabled for automatic startup. "
                    "Automatic launch starts chains only."
                )
                self._show_banner(
                    "Automatic launch starts chains only. TUN stays off until you enable it manually.",
                    "info",
                )
                self._refresh_all_pages()
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
        page = self._tab_widgets.get(key)
        if page is not None:
            self.tabs.setCurrentWidget(page)

    def _is_admin(self) -> bool:
        import ctypes

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _get_preflight_state(self) -> dict[str, object]:
        exe_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        valid_chain_ids = {
            chain.chain_id
            for chain in self.app_state.chains
            if chain.hop_node_ids and len(self.app_state.get_nodes_for_chain(chain)) == len(chain.hop_node_ids)
        }
        valid_mapping_count = sum(
            1 for mapping in self.app_state.port_mappings if mapping.chain_id in valid_chain_ids
        )

        blockers: list[str] = []
        warnings: list[str] = []
        next_target = "subscriptions"

        if not self.app_state.subscriptions and not self.app_state.nodes:
            blockers.append("No nodes are available yet. Add a subscription or paste node URIs.")
            next_target = "subscriptions"
        elif not self.app_state.nodes:
            blockers.append("Subscriptions exist, but no nodes were imported successfully.")
            next_target = "subscriptions"
        elif not valid_chain_ids:
            blockers.append("No usable chains exist yet. Create a chain with at least one valid hop.")
            next_target = "routing"
        elif valid_mapping_count == 0:
            blockers.append("No usable port mappings exist yet. Bind at least one local port to a valid chain.")
            next_target = "routing"

        if not exe_path:
            blockers.append("A core executable path is still missing.")
            if next_target == "subscriptions":
                next_target = "settings"

        if self.app_state.enable_tun:
            if not self.app_state.tun_chain_id:
                blockers.append("TUN mode is enabled, but no chain is selected for it.")
                next_target = "routing"
            elif not self._is_admin():
                blockers.append("TUN mode is enabled and requires administrator privileges before starting.")
                warnings.append("Use 'Run as Admin' before starting the core with TUN enabled.")
                next_target = "routing"

        if self.app_state.subscriptions == [] and self.app_state.nodes:
            warnings.append("You are running only manual nodes. That is fine, but subscriptions remain empty.")

        if self.app_state.enable_tun and self.app_state.tun_chain_id:
            tun_chain = self.app_state.find_chain_by_id(self.app_state.tun_chain_id)
            if tun_chain is None:
                warnings.append("The TUN chain no longer exists and should be reselected.")

        can_apply = bool(valid_mapping_count)
        can_start = can_apply and bool(exe_path) and not (
            self.app_state.enable_tun and not self._is_admin()
        ) and not (
            self.app_state.enable_tun and not self.app_state.tun_chain_id
        )
        title = "Ready" if can_start else "Action required"
        detail = blockers[0] if blockers else ("Configuration looks ready." if not warnings else warnings[0])
        next_step = (
            "Apply the config, then start the core."
            if can_start
            else "Open the highlighted page and resolve the remaining blockers."
        )
        return {
            "title": title,
            "detail": detail,
            "next_step": next_step,
            "blockers": blockers,
            "warnings": warnings,
            "next_target": next_target,
            "can_apply": can_apply,
            "can_start": can_start,
            "valid_mapping_count": valid_mapping_count,
        }

    def _refresh_action_state(self) -> None:
        preflight = self._get_preflight_state()
        is_running = self.process_runner.is_running()
        self.btn_apply.setEnabled(bool(preflight["can_apply"]) and not is_running)
        self.btn_start.setEnabled(bool(preflight["can_start"]) and not is_running)
        self.btn_stop.setEnabled(is_running)
        self.btn_run_admin.setVisible(self.app_state.enable_tun and not self._is_admin())
        self.lbl_preflight.setText(str(preflight["title"]))
        self.lbl_context.setText(f"{preflight['detail']} Next: {preflight['next_step']}")
        self.page_dashboard.set_runtime_state(is_running=is_running)
        self.page_dashboard.set_preflight_summary(
            blockers=list(preflight["blockers"]),
            warnings=list(preflight["warnings"]),
            next_target=str(preflight["next_target"]),
            can_apply=bool(preflight["can_apply"]),
            can_start=bool(preflight["can_start"]),
        )
