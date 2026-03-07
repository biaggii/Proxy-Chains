"""
process_runner.py — 核心進程管理器

負責：
  1. 啟動核心進程（subprocess.Popen）
  2. 從 stdout/stderr 讀取 log
  3. 停止進程
  4. 檢查進程是否在跑

GUI 層只需要呼叫這個模組的方法，不直接碰 subprocess。
"""

import subprocess
import threading
from typing import Callable


class ProcessRunner:
    """
    管理一個外部進程（核心引擎）的生命週期。

    使用方式：
        runner = ProcessRunner()
        runner.start(["sing-box.exe", "run", "-c", "config.json"], on_log=my_callback)
        ...
        runner.stop()
    """

    def __init__(self):
        # 目前正在跑的進程物件
        self._process: subprocess.Popen | None = None

        # 讀取 log 的背景執行緒
        self._log_thread: threading.Thread | None = None

        # 告訴背景執行緒該停下來的旗標
        self._stop_flag = threading.Event()

        # log 回呼函式（每讀到一行就呼叫）
        self._on_log: Callable[[str], None] | None = None
        self._on_exit: Callable[[], None] | None = None

    def is_running(self) -> bool:
        """檢查進程是否還在跑"""
        if self._process is None:
            return False
        # poll() 回傳 None 表示還在跑
        return self._process.poll() is None

    def start(
        self,
        command: list[str],
        on_log: Callable[[str], None] | None = None,
        cwd: str | None = None,
        **kwargs,
    ) -> bool:
        """
        啟動核心進程。

        參數：
        - command : 要執行的命令，例如 ["sing-box.exe", "run", "-c", "config.json"]
        - on_log  : 每讀到一行 log 就呼叫這個函式，參數是一行文字
        - on_exit : 進程結束時呼叫的函式
        - cwd     : 工作目錄
        """
        # 如果已經在跑，先停掉
        if self.is_running():
            self.stop()

        self._on_log = on_log
        self._on_exit = kwargs.get('on_exit', None)
        self._stop_flag.clear()

        # 準備環境變數（為了禁用部分 sing-box 的棄用警告/錯誤）
        import os
        env = os.environ.copy()
        env["ENABLE_DEPRECATED_DNS_SERVERS"] = "true"
        env["ENABLE_DEPRECATED_LEGACY_DNS_SERVERS"] = "true"
        env["ENABLE_DEPRECATED_SPECIAL_OUTBOUNDS"] = "true"
        env["ENABLE_DEPRECATED_OUTBOUND_DNS_RULES"] = "true"

        # 啟動進程（把 stdout 和 stderr 合併到一起讀）
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=env,
                # 在 Windows 上不顯示黑色命令列窗口
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                # 用 UTF-8 讀取輸出
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            if on_log:
                on_log(f"[Error] Executable not found: {command[0]}")
            self._process = None
            return False
        except Exception as err:
            if on_log:
                on_log(f"[Error] Failed to start process: {err}")
            self._process = None
            return False

        if on_log:
            on_log(f"[Info] Process started (PID={self._process.pid})")
            on_log(f"[Info] Command: {' '.join(command)}")

        # 啟動背景執行緒讀 log
        self._log_thread = threading.Thread(
            target=self._read_log_loop,
            daemon=True,  # daemon thread：主程式關掉就自動結束
        )
        self._log_thread.start()
        return True

    def stop(self) -> None:
        """停止核心進程"""
        self._stop_flag.set()

        if self._process is not None and self.is_running():
            try:
                # 先嘗試溫和地終止
                self._process.terminate()
                # 等最多 3 秒
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # 等不到就強制殺掉
                    self._process.kill()
                    self._process.wait(timeout=2)
            except Exception:
                pass  # 進程可能已經自己結束了

            if self._on_log:
                self._on_log("[Info] Process stopped")

        self._process = None

        # 等背景執行緒結束
        if self._log_thread is not None:
            self._log_thread.join(timeout=2)
            self._log_thread = None

    def run_and_wait(
        self,
        command: list[str],
        timeout_seconds: int = 15,
        cwd: str | None = None,
    ) -> tuple[bool, str]:
        """
        執行一個短命令並等它結束（用於 check / validate）。

        回傳值：
        - (success, output_text)
          success = True 表示 exit code == 0
        """
        try:
            import os
            env = os.environ.copy()
            env["ENABLE_DEPRECATED_DNS_SERVERS"] = "true"
            env["ENABLE_DEPRECATED_LEGACY_DNS_SERVERS"] = "true"
            env["ENABLE_DEPRECATED_SPECIAL_OUTBOUNDS"] = "true"
            env["ENABLE_DEPRECATED_OUTBOUND_DNS_RULES"] = "true"

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=cwd,
                env=env,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0
            return success, output.strip()
        except FileNotFoundError:
            return False, f"Executable not found: {command[0]}"
        except subprocess.TimeoutExpired:
            return False, f"Command timed out ({timeout_seconds} seconds)"
        except Exception as err:
            return False, f"Error while running command: {err}"

    # ============================================================
    # 私有方法：背景讀取 log
    # ============================================================

    def _read_log_loop(self) -> None:
        """背景執行緒：持續從 stdout 讀取 log 行"""
        if self._process is None or self._process.stdout is None:
            return

        try:
            for line in iter(self._process.stdout.readline, ""):
                # 如果被要求停止，就退出
                if self._stop_flag.is_set():
                    break
                # 去掉尾巴的換行
                line = line.rstrip("\n").rstrip("\r")
                if line and self._on_log:
                    self._on_log(line)
        except Exception:
            pass  # 進程結束後 readline 可能會拋例外

        # 進程結束後的訊息
        if self._process is not None:
            exit_code = self._process.poll()
            if exit_code is not None and self._on_log:
                self._on_log(f"[Info] Process exited with code {exit_code}")
        
        # 呼叫 on_exit
        if self._on_exit:
            self._on_exit()
