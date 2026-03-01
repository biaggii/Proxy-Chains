"""
core_adapter_base.py — 核心適配器的抽象基底類別

所有核心（sing-box / xray / mihomo）都要實作這個介面。
這樣 UI 層只需要呼叫統一的方法，不用管底下是哪個核心。

方法：
  - generate_config(app_state) -> (config_text, config_file_path)
  - get_check_command(config_path) -> list[str]
  - get_start_command(config_path) -> list[str]
"""

from abc import ABC, abstractmethod

from models.app_state import AppState


class CoreAdapterBase(ABC):
    """
    核心適配器的抽象基底。
    每個子類別（SingBoxAdapter、XrayAdapter、MihomoAdapter）都要實作所有 abstract 方法。
    """

    @abstractmethod
    def adapter_name(self) -> str:
        """回傳這個適配器的名稱，例如 "sing-box" """
        ...

    @abstractmethod
    def generate_config(self, app_state: AppState) -> tuple[str, str]:
        """
        根據 AppState 產生核心的配置檔內容。

        參數：
        - app_state: 包含所有節點、鏈、端口映射的全域狀態

        回傳值：
        - (config_text, config_file_path)
          config_text 是配置檔的文字內容
          config_file_path 是實際寫入的檔案路徑
        """
        ...

    @abstractmethod
    def get_check_command(self, config_path: str, exe_path: str) -> list[str]:
        """
        回傳用來「驗證配置檔」的命令。

        例如 sing-box: ["sing-box.exe", "check", "-c", "config.json"]
        例如 xray:     ["xray.exe", "run", "-test", "-c", "config.json"]
        """
        ...

    @abstractmethod
    def get_start_command(self, config_path: str, exe_path: str) -> list[str]:
        """
        回傳用來「啟動核心」的命令。

        例如 sing-box: ["sing-box.exe", "run", "-c", "config.json"]
        例如 xray:     ["xray.exe", "run", "-c", "config.json"]
        """
        ...

    @abstractmethod
    def config_file_extension(self) -> str:
        """回傳配置檔的副檔名，例如 ".json" 或 ".yaml" """
        ...
