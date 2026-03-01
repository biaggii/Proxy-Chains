"""
ui_main_window.py — 主窗口

這是整個 GUI 的骨架：
  - 頂部：QTabWidget（6 個頁籤）
  - 底部：Apply / Start / Stop 三顆按鈕 + 狀態列

所有頁面都共用同一個 AppState 物件。
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QLabel, QMessageBox,
    QStatusBar, QSystemTrayIcon, QStyle, QMenu, QApplication
)
from PySide6.QtGui import QIcon, QAction, QCloseEvent
from PySide6.QtCore import Qt, Signal, Slot, QObject, QEvent
import subprocess
import os

from models.app_state import AppState
from core.process_runner import ProcessRunner

from app.ui_pages_subscriptions import SubscriptionsPage
from app.ui_pages_nodes import NodesPage
from app.ui_pages_chains import ChainsPage
from app.ui_pages_ports import PortsPage
from app.ui_pages_logs import LogsPage
from app.ui_pages_settings import SettingsPage


class LogBridge(QObject):
    """
    用來把背景執行緒的 log 文字安全地送到 GUI 執行緒。
    因為 PySide6 不允許從非 GUI 執行緒直接修改 UI，
    所以用 Signal 跨執行緒傳遞資料。
    """
    log_signal = Signal(str)
    stopped_signal = Signal()


class MainWindow(QMainWindow):
    """應用程式主窗口"""

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.process_runner = ProcessRunner()

        # 用來跨執行緒傳 log 的橋樑
        self.log_bridge = LogBridge()

        self._init_ui()
        self._init_tray_icon()
        self._connect_signals()
        self._load_and_refresh()

    def _init_ui(self) -> None:
        """建立所有 UI 元件"""
        self.setWindowTitle("ChainPort Gateway - Proxy Multi-Chain Manager")
        self.setMinimumSize(950, 750)
        self.resize(950, 750)

        # 主要容器
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ---------- Tab Widget ----------
        self.tabs = QTabWidget()

        # 建立 6 個頁面
        self.page_subs = SubscriptionsPage(self.app_state)
        self.page_nodes = NodesPage(self.app_state)
        self.page_chains = ChainsPage(self.app_state)
        self.page_ports = PortsPage(self.app_state)
        self.page_logs = LogsPage()
        self.page_settings = SettingsPage(self.app_state)

        self.tabs.addTab(self.page_subs, "📡 Subscriptions")
        self.tabs.addTab(self.page_nodes, "🖧 Nodes")
        self.tabs.addTab(self.page_chains, "🔗 Chains")
        self.tabs.addTab(self.page_ports, "🔌 Ports")
        self.tabs.addTab(self.page_logs, "📋 Logs")
        self.tabs.addTab(self.page_settings, "⚙️ Settings")

        # 切頁時刷新
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

        # ---------- 底部按鈕列 ----------
        bottom_row = QHBoxLayout()

        # 狀態顯示
        self.lbl_status = QLabel("● Stopped")
        self.lbl_status.setStyleSheet("color: gray; font-weight: bold;")
        bottom_row.addWidget(self.lbl_status)

        bottom_row.addStretch()

        self.btn_apply = QPushButton("📝 Apply (Generate Config)")
        self.btn_apply.setMinimumHeight(36)
        self.btn_apply.clicked.connect(self._on_apply)
        
        self.btn_run_admin = QPushButton("🛡️ Run as Admin")
        self.btn_run_admin.setMinimumHeight(36)
        self.btn_run_admin.setStyleSheet("QPushButton { background-color: #f39c12; color: white; font-weight: bold; }")
        self.btn_run_admin.clicked.connect(self._relaunch_as_admin)
        
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            self.btn_run_admin.hide()
            
        bottom_row.addWidget(self.btn_run_admin)
        bottom_row.addWidget(self.btn_apply)

        self.btn_start = QPushButton("▶️ Start")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.setStyleSheet("QPushButton { background-color: #2d7d46; color: white; }")
        self.btn_start.clicked.connect(self._on_start)
        bottom_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹️ Stop")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.setStyleSheet("QPushButton { background-color: #c0392b; color: white; }")
        self.btn_stop.clicked.connect(self._on_stop)
        bottom_row.addWidget(self.btn_stop)

        main_layout.addLayout(bottom_row)

        # 狀態列
        self.statusBar().showMessage("Ready")

    def _connect_signals(self) -> None:
        """連接各頁面的 data_changed 信號"""
        # 任何頁面的資料改變時，自動儲存 state.json
        self.page_subs.data_changed.connect(self._on_data_changed)
        self.page_nodes.data_changed.connect(self._on_data_changed)
        self.page_chains.data_changed.connect(self._on_data_changed)
        self.page_ports.data_changed.connect(self._on_data_changed)
        self.page_settings.data_changed.connect(self._on_data_changed)

        # Log 橋：背景執行緒 -> GUI 執行緒
        self.log_bridge.log_signal.connect(self.page_logs.append_log)
        self.log_bridge.stopped_signal.connect(self._on_core_exited)

    def _load_and_refresh(self) -> None:
        """載入 state.json 並刷新所有頁面"""
        self.app_state.load_from_file()
        self._refresh_all_pages()

    def _refresh_all_pages(self) -> None:
        """刷新所有頁面的表格"""
        self.page_subs.refresh_table()
        self.page_nodes.refresh_table()
        self.page_chains.refresh_table()
        self.page_ports.refresh_table()
        self.page_settings.refresh_table()

    def _init_tray_icon(self) -> None:
        """初始化系統列圖示 (System Tray)"""
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
            # Stop core process and save state explicitly before restart
            self._on_stop()
            self.app_state.save_to_file()
            
            # Request UAC elevation for current script/exe
            if getattr(sys, 'frozen', False):
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "", None, 1)
            else:
                import os
                main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
                
                # Use pythonw.exe to prevent a blank terminal window from showing
                exe_path = sys.executable
                if exe_path.lower().endswith("python.exe"):
                    pythonw_path = exe_path[:-10] + "pythonw.exe"
                    if os.path.exists(pythonw_path):
                        exe_path = pythonw_path
                        
                ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, f'"{main_script}"', None, 1)
                
            # Safely exit this non-admin instance
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
        """完全退出程式，先停止核心"""
        if self.process_runner.is_running():
            self._on_stop()
        self.app_state.save_to_file()
        self._force_closing = True
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        """當使用者按下 [X] 時，縮小到系統列而不是完全退出"""
        if getattr(self, '_force_closing', False):
            event.accept()
            return
            
        event.ignore()
        self.hide()
        
        # 可選：顯示一個氣泡提示告訴使用者藏去哪裡了
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "ChainPort Gateway",
                "App minimized to tray. Right-click the tray icon to exit entirely.",
                QSystemTrayIcon.Information,
                2000
            )

    def changeEvent(self, event: QEvent) -> None:
        """當使用者按下最小化「-」時也隱藏到系統列"""
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
                self.hide()
        super().changeEvent(event)

    # ============================================================
    # 事件處理
    # ============================================================

    @Slot()
    def _on_data_changed(self) -> None:
        """資料改變時，儲存 state 並刷新"""
        self.app_state.save_to_file()
        self.statusBar().showMessage("Auto-saved", 3000)

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        """切頁時刷新該頁"""
        page = self.tabs.widget(index)
        if hasattr(page, "refresh_table"):
            page.refresh_table()

    @Slot()
    def _on_apply(self) -> None:
        """按下 Apply：產生配置檔 + 驗證"""
        adapter = self._get_current_adapter()
        if adapter is None:
            return

        # 檢查基本條件
        if not self.app_state.port_mappings:
            QMessageBox.warning(self, "Notice", "Please create at least one port mapping in Ports tab first")
            return

        # 產生配置
        try:
            config_text, config_path = adapter.generate_config(self.app_state)
        except Exception as err:
            QMessageBox.critical(self, "Config Generation Failed", str(err))
            return

        # 驗證配置
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
            else:
                self.page_logs.append_log(f"[Verify] ❌ Config verification failed:")
                self.page_logs.append_log(output)

                error_msg = f"Config verification failed!\n\n{output[:500]}"
                if "Access is denied" in output and self.app_state.enable_tun:
                    error_msg = "🚨 Administrator Privileges Required!\n\nYou have enabled TUN Mode which creates virtual network interfaces.\nYou MUST right-click the terminal/command prompt and 'Run as Administrator' for sing-box/mihomo to work."

                QMessageBox.warning(
                    self, "Verification Failed", error_msg
                )
        else:
            self.page_logs.append_log(f"[Apply] Config generated: {config_path}")
            self.page_logs.append_log("[Apply] ⚠️ Core path not set, skipping verification")
            QMessageBox.information(
                self, "Apply",
                f"Config generated (Not verified due to missing core path)\n\nFile: {config_path}"
            )

        self.app_state.save_to_file()

    @Slot()
    def _on_start(self) -> None:
        """按下 Start：啟動核心"""
        if self.process_runner.is_running():
            QMessageBox.information(self, "Notice", "Core is already running")
            return

        exe_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")
        if not exe_path:
            QMessageBox.warning(self, "Notice", "Please set executable path in Settings first")
            return

        adapter = self._get_current_adapter()
        if adapter is None:
            return

        # 先幫所有的核心產生配置檔 (Auto-generate for all cores)
        from core.singbox_adapter import SingBoxAdapter
        from core.xray_adapter import XrayAdapter
        from core.mihomo_adapter import MihomoAdapter
        
        all_adapters = [SingBoxAdapter(), XrayAdapter(), MihomoAdapter()]
        for adp in all_adapters:
            try:
                path = adp.generate_config(self.app_state)[1]
                self.page_logs.append_log(f"[Auto Gen] ✅ {adp.adapter_name()} config generated: {path}")
            except Exception as err:
                self.page_logs.append_log(f"[Auto Gen] ❌ {adp.adapter_name()} generation failed: {err}")

        # 取得當前選擇的核心配置路徑以供啟動 (Get the config path for the selected core to start)
        try:
            _, config_path = adapter.generate_config(self.app_state)
        except Exception as err:
            QMessageBox.critical(self, "Error", f"Config generation failed: {err}")
            return

        # 啟動
        start_cmd = adapter.get_start_command(config_path, exe_path)

        # on_log 回呼用 signal 把文字送到 GUI 執行緒
        def on_log_from_thread(text: str) -> None:
            self.log_bridge.log_signal.emit(text)

        def on_exit_from_thread() -> None:
            self.log_bridge.stopped_signal.emit()

        self.process_runner.start(start_cmd, on_log=on_log_from_thread, on_exit=on_exit_from_thread)
        self._update_status(True)
        self.statusBar().showMessage("Core Started", 3000)

        # 切到 Logs 頁方便看 log
        self.tabs.setCurrentWidget(self.page_logs)

    @Slot()
    def _on_core_exited(self) -> None:
        """核心退出時更新 UI 狀態"""
        self._update_status(False)
        self.statusBar().showMessage("Core Exited", 3000)

    @Slot()
    def _on_stop(self) -> None:
        """按下 Stop：停止核心，順便清所有可能殘留的殭屍進程"""
        # 放棄檢查 is_running，強制停止並發送信號
        if self.process_runner.is_running():
            self.process_runner.stop()
        
        self._update_status(False)
        self.statusBar().showMessage("Core Stopped", 3000)

        # 暴力清理可能卡住的背景進程 (ghost processes block port binding)
        core = self.app_state.core_type
        exe_name = ""
        if core == "sing-box":
            exe_name = "sing-box.exe"
        elif core == "xray":
            exe_name = "xray.exe"
        elif core == "mihomo":
            exe_name = "mihomo.exe"
            
        if exe_name:
            try:
                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                subprocess.run(["taskkill", "/F", "/IM", exe_name], creationflags=flags, capture_output=True)
                self.page_logs.append_log(f"[System] Sent terminate signal to cleanup {exe_name} ghost processes.")
            except Exception:
                pass

    # ============================================================
    # 工具方法
    # ============================================================

    def _get_current_adapter(self):
        """根據設定取得對應的 CoreAdapter"""
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
            QMessageBox.warning(self, "Error", f"Unknown core type: {core_type}")
            return None

    def _update_status(self, is_running: bool) -> None:
        """更新底部狀態標籤"""
        if is_running:
            self.lbl_status.setText("● Running")
            self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.lbl_status.setText("● Stopped")
            self.lbl_status.setStyleSheet("color: gray; font-weight: bold;")


