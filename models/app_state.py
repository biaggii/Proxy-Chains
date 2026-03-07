"""
app_state.py — 應用程式全域狀態

AppState 是整個程式的「大腦」，存放所有資料：
  - 訂閱清單
  - 節點清單
  - 鏈清單
  - 端口映射清單
  - 設定（核心類型、exe 路徑等）

所有資料存在一個 JSON 檔（state.json），方便人類閱讀和 debug。
"""

import json
import os

from models.node import Node
from models.subscription import Subscription
from models.chain import Chain
from models.port_mapping import PortMapping


import sys

# Get app running directory regardless of Python script or frozen EXE
if getattr(sys, 'frozen', False):
    # PyInstaller executable - save matching next to the .exe itself
    _base_dir = os.path.dirname(sys.executable)
else:
    # Running from python main.py
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default path for state.json 
DEFAULT_STATE_FILE = os.path.join(_base_dir, "state.json")


class AppState:
    """
    應用程式的全域狀態，管理所有資料的增刪改查和持久化。
    """

    def __init__(self, state_file_path: str = DEFAULT_STATE_FILE):
        # JSON 檔的儲存路徑
        self.state_file_path: str = state_file_path

        # ---------- 資料容器 ----------
        self.subscriptions: list[Subscription] = []
        self.nodes: list[Node] = []
        self.chains: list[Chain] = []
        self.port_mappings: list[PortMapping] = []

        # ---------- 設定 ----------
        self.core_type: str = "sing-box"         # sing-box / xray / mihomo
        self.core_exe_paths: dict[str, str] = {
            "sing-box": self._get_default_exe_path("sing-box"),
            "xray": self._get_default_exe_path("xray"),
            "mihomo": self._get_default_exe_path("mihomo"),
        }
        self.config_output_dir: str = os.path.dirname(state_file_path)
        self.log_level: str = "warning"  # debug, info, warning, error, fatal
        self.enable_ipv6: bool = False
        
        # 進階代理設定 (Advanced Proxy Settings)
        self.enable_udp: bool = True
        self.enable_sniffing: bool = True
        self.allow_lan: bool = False
        self.enable_mux: bool = False
        self.allow_insecure: bool = False
        self.enable_fragment: bool = False
        self.singbox_mux_protocol: str = "h2mux"  # h2mux, smux, yamux
        
        # TUN 設定 (TUN Settings)
        self.enable_tun: bool = False
        self.tun_chain_id: str = ""
        
        # 啟動設定 (Startup Settings)
        self.run_on_startup: bool = False
        self.minimize_on_start: bool = False

    def _get_default_exe_path(self, core_type: str) -> str:
        """根據核心類型，預設去 ./bin/ 目錄下找找看有沒有對應的 exe"""
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        bin_dir = os.path.join(base_dir, "bin")
        exe_name = f"{core_type}.exe"
        possible_path = os.path.join(bin_dir, exe_name)
        if os.path.exists(possible_path):
            return possible_path
        return ""

    # ================================================================
    # 節點查找（很多地方要用到）
    # ================================================================

    def find_node_by_id(self, node_id: str) -> Node | None:
        """用 node_id 找節點，找不到回傳 None"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def find_chain_by_id(self, chain_id: str) -> Chain | None:
        """用 chain_id 找鏈，找不到回傳 None"""
        for chain in self.chains:
            if chain.chain_id == chain_id:
                return chain
        return None

    def find_sub_by_id(self, sub_id: str) -> Subscription | None:
        """用 sub_id 找訂閱"""
        for sub in self.subscriptions:
            if sub.sub_id == sub_id:
                return sub
        return None

    def find_mapping_by_id(self, mapping_id: str) -> PortMapping | None:
        """用 mapping_id 找端口映射"""
        for m in self.port_mappings:
            if m.mapping_id == mapping_id:
                return m
        return None

    # ================================================================
    # 刪除某個訂閱時，連帶刪除它的節點
    # ================================================================

    def remove_subscription_and_nodes(self, sub_id: str) -> None:
        """刪除訂閱，並移除所有來自該訂閱的節點"""
        # 找到訂閱名稱
        sub = self.find_sub_by_id(sub_id)
        if sub is None:
            return
        sub_name = sub.name

        # 移除該訂閱
        self.subscriptions = [s for s in self.subscriptions if s.sub_id != sub_id]

        # 移除來自該訂閱的節點
        self.nodes = [n for n in self.nodes if n.source_sub != sub_name]

    # ================================================================
    # 儲存 / 載入 JSON
    # ================================================================

    def save_to_file(self) -> None:
        """把目前狀態存成 JSON 檔"""
        state_dict = {
            "core_type": self.core_type,
            "core_exe_paths": self.core_exe_paths,
            "config_output_dir": self.config_output_dir,
            "log_level": self.log_level,
            "enable_ipv6": self.enable_ipv6,
            "enable_udp": self.enable_udp,
            "enable_sniffing": self.enable_sniffing,
            "allow_lan": self.allow_lan,
            "enable_mux": self.enable_mux,
            "allow_insecure": self.allow_insecure,
            "enable_fragment": self.enable_fragment,
            "singbox_mux_protocol": self.singbox_mux_protocol,
            "enable_tun": self.enable_tun,
            "tun_chain_id": self.tun_chain_id,
            "run_on_startup": self.run_on_startup,
            "minimize_on_start": self.minimize_on_start,
            "subscriptions": [s.to_dict() for s in self.subscriptions],
            "nodes": [n.to_dict() for n in self.nodes],
            "chains": [c.to_dict() for c in self.chains],
            "port_mappings": [m.to_dict() for m in self.port_mappings],
        }

        # 確保目錄存在
        dir_path = os.path.dirname(self.state_file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        # 寫檔（用 UTF-8 + 排版，方便人類閱讀）
        with open(self.state_file_path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, ensure_ascii=False, indent=2)

    def load_from_file(self) -> None:
        """從 JSON 檔讀回狀態。如果檔案不存在就跳過。"""
        if not os.path.exists(self.state_file_path):
            return  # 第一次跑，還沒有 state.json

        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                state_dict = json.load(f)
        except (json.JSONDecodeError, IOError) as err:
            print(f"[警告] 讀取 state.json 失敗: {err}")
            return

        # 還原設定
        self.core_type = state_dict.get("core_type", "sing-box")
        
        # 兼容舊版單一路徑
        old_exe_path = state_dict.get("core_exe_path", "")
        if old_exe_path and "core_exe_paths" not in state_dict:
            self.core_exe_paths[self.core_type] = old_exe_path
        elif "core_exe_paths" in state_dict:
            loaded_paths = state_dict["core_exe_paths"]
            for ct in ["sing-box", "xray", "mihomo"]:
                if ct in loaded_paths and loaded_paths[ct]:
                    self.core_exe_paths[ct] = loaded_paths[ct]
                else:
                    self.core_exe_paths[ct] = self._get_default_exe_path(ct)
        else:
             for ct in ["sing-box", "xray", "mihomo"]:
                  self.core_exe_paths[ct] = self._get_default_exe_path(ct)

        self.config_output_dir = state_dict.get(
            "config_output_dir", os.path.dirname(self.state_file_path)
        )
        self.log_level = state_dict.get("log_level", "warning")
        self.enable_ipv6 = state_dict.get("enable_ipv6", False)
        self.enable_udp = state_dict.get("enable_udp", True)
        self.enable_sniffing = state_dict.get("enable_sniffing", True)
        self.allow_lan = state_dict.get("allow_lan", False)
        self.enable_mux = state_dict.get("enable_mux", False)
        self.allow_insecure = state_dict.get("allow_insecure", False)
        self.enable_fragment = state_dict.get("enable_fragment", False)
        self.singbox_mux_protocol = state_dict.get("singbox_mux_protocol", "h2mux")
        self.enable_tun = state_dict.get("enable_tun", False)
        self.tun_chain_id = state_dict.get("tun_chain_id", "")
        self.run_on_startup = state_dict.get("run_on_startup", False)
        self.minimize_on_start = state_dict.get("minimize_on_start", False)

        # 還原資料
        self.subscriptions = [
            Subscription.from_dict(d) for d in state_dict.get("subscriptions", [])
        ]
        self.nodes = [
            Node.from_dict(d) for d in state_dict.get("nodes", [])
        ]
        self.chains = [
            Chain.from_dict(d) for d in state_dict.get("chains", [])
        ]
        self.port_mappings = [
            PortMapping.from_dict(d) for d in state_dict.get("port_mappings", [])
        ]

    # ================================================================
    # 方便的工具方法
    # ================================================================

    def get_nodes_for_chain(self, chain: Chain) -> list[Node]:
        """
        根據 chain 的 hop_node_ids，回傳對應的 Node 物件清單。
        找不到的 node_id 會跳過（可能被刪了）。
        """
        result: list[Node] = []
        for node_id in chain.hop_node_ids:
            node = self.find_node_by_id(node_id)
            if node is not None:
                result.append(node)
        return result

    def is_port_in_use(self, port: int, exclude_mapping_id: str = "") -> bool:
        """檢查某個端口是否已被其他映射使用"""
        for m in self.port_mappings:
            if m.listen_port == port and m.mapping_id != exclude_mapping_id:
                return True
        return False
