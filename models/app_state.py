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
import ntpath
import sys

from models.node import Node
from models.subscription import Subscription
from models.chain import Chain
from models.port_mapping import PortMapping


# Get app running directory regardless of Python script or frozen EXE
if getattr(sys, 'frozen', False):
    # PyInstaller executable - save matching next to the .exe itself
    _base_dir = os.path.dirname(sys.executable)
else:
    # Running from python main.py
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default path for state.json 
DEFAULT_STATE_FILE = os.path.join(_base_dir, "state.json")
LEGACY_CHAIN_NODE_TYPE = "chain"


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
        self.enable_final_fragment: bool = False
        self.block_quic: bool = True
        self.remote_dns_url: str = "https://cloudflare-dns.com/dns-query"
        self.bootstrap_dns: str = "119.29.29.29"
        self.singbox_mux_protocol: str = "h2mux"  # h2mux, smux, yamux
        
        # TUN 設定 (TUN Settings)
        self.enable_tun: bool = False
        self.tun_chain_id: str = ""
        
        # 啟動設定 (Startup Settings)
        self.run_on_startup: bool = False
        self.minimize_on_start: bool = False
        self.auto_start_core: bool = False
        self.close_to_tray: bool = True

    def _get_default_exe_path(self, core_type: str) -> str:
        """Resolve the bundled core executable for the current OS."""
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        if os.name == "nt":
            candidates = {
                "sing-box": os.path.join(base_dir, "bin", "sing_box", "sing-box.exe"),
                "xray": os.path.join(base_dir, "bin", "xray", "xray.exe"),
                "mihomo": os.path.join(base_dir, "bin", "mihomo", "mihomo.exe"),
            }
        else:
            candidates = {
                "sing-box": os.path.join(base_dir, "bin", "sing_box", "sing-box"),
                "xray": os.path.join(base_dir, "bin", "xray", "xray"),
                "mihomo": os.path.join(base_dir, "bin", "mihomo", "mihomo"),
            }

        possible_path = candidates.get(core_type, "")
        if possible_path and os.path.isfile(possible_path) and os.access(possible_path, os.X_OK if os.name != "nt" else os.F_OK):
            return possible_path
        return ""

    @staticmethod
    def _is_path_for_current_platform(path: str) -> bool:
        """Reject persisted paths from another OS (e.g. D:\\... on Linux)."""
        if not path:
            return False
        if os.name != "nt" and ntpath.isabs(path):
            return False
        if os.name == "nt" and os.path.isabs(path) is False:
            return False
        return os.path.isfile(path)

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
            "enable_final_fragment": self.enable_final_fragment,
            "block_quic": self.block_quic,
            "remote_dns_url": self.remote_dns_url,
            "bootstrap_dns": self.bootstrap_dns,
            "singbox_mux_protocol": self.singbox_mux_protocol,
            "enable_tun": self.enable_tun,
            "tun_chain_id": self.tun_chain_id,
            "run_on_startup": self.run_on_startup,
            "minimize_on_start": self.minimize_on_start,
            "auto_start_core": self.auto_start_core,
            "close_to_tray": self.close_to_tray,
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

        # Migrate paths saved on another OS and stale bundle layouts. This is
        # important when a profile/state.json is shared between Windows/Linux.
        for core_name in ("sing-box", "xray", "mihomo"):
            saved_path = self.core_exe_paths.get(core_name, "")
            if not self._is_path_for_current_platform(saved_path):
                self.core_exe_paths[core_name] = self._get_default_exe_path(core_name)

        saved_config_dir = state_dict.get("config_output_dir", "")
        if (
            not saved_config_dir
            or (os.name != "nt" and ntpath.isabs(saved_config_dir))
            or (os.name == "nt" and not os.path.isabs(saved_config_dir))
        ):
            self.config_output_dir = os.path.join(_base_dir, "logs")
        else:
            self.config_output_dir = saved_config_dir
        self.log_level = state_dict.get("log_level", "warning")
        self.enable_ipv6 = state_dict.get("enable_ipv6", False)
        self.enable_udp = state_dict.get("enable_udp", True)
        self.enable_sniffing = state_dict.get("enable_sniffing", True)
        self.allow_lan = state_dict.get("allow_lan", False)
        self.enable_mux = state_dict.get("enable_mux", False)
        self.allow_insecure = state_dict.get("allow_insecure", False)
        self.enable_fragment = state_dict.get("enable_fragment", False)
        self.enable_final_fragment = state_dict.get(
            "enable_final_fragment", self.enable_fragment
        )
        self.block_quic = state_dict.get("block_quic", True)
        self.remote_dns_url = state_dict.get(
            "remote_dns_url", "https://cloudflare-dns.com/dns-query"
        )
        self.bootstrap_dns = state_dict.get("bootstrap_dns", "119.29.29.29")
        self.singbox_mux_protocol = state_dict.get("singbox_mux_protocol", "h2mux")
        self.enable_tun = state_dict.get("enable_tun", False)
        self.tun_chain_id = state_dict.get("tun_chain_id") or ""
        self.run_on_startup = state_dict.get("run_on_startup", False)
        self.minimize_on_start = state_dict.get("minimize_on_start", False)
        self.auto_start_core = state_dict.get("auto_start_core", False)
        self.close_to_tray = state_dict.get("close_to_tray", True)

        # 還原資料
        self.subscriptions = [
            Subscription.from_dict(d) for d in state_dict.get("subscriptions", [])
        ]
        self.nodes = [
            Node.from_dict(d) for d in state_dict.get("nodes", [])
        ]
        self.chains = [Chain.from_dict(d) for d in state_dict.get("chains", [])]
        self.port_mappings = [
            PortMapping.from_dict(d) for d in state_dict.get("port_mappings", [])
        ]
        self._migrate_legacy_chain_nodes()
        self._ensure_default_port_mappings()

    def _migrate_legacy_chain_nodes(self) -> None:
        """Collapse the previous duplicate Node(type=chain) wrapper into Chain."""
        legacy = {node.node_id: node for node in self.nodes if node.node_type == LEGACY_CHAIN_NODE_TYPE}
        if not legacy:
            return

        chains_by_id = {chain.chain_id: chain for chain in self.chains}
        for node in legacy.values():
            source_chain_id = node.extra.get("source_chain_id")
            if source_chain_id and source_chain_id not in chains_by_id:
                chain = Chain(
                    name=node.name,
                    hop_node_ids=list(node.extra.get("chain_hop_node_ids", [])),
                    chain_id=source_chain_id,
                )
                self.chains.append(chain)
                chains_by_id[chain.chain_id] = chain

        def expand(node_id: str, ancestors: set[str]) -> list[str] | None:
            wrapper = legacy.get(node_id)
            if wrapper is None:
                return [node_id] if self.find_node_by_id(node_id) else None
            if node_id in ancestors:
                return None
            nested = wrapper.extra.get("chain_hop_node_ids", [])
            if not isinstance(nested, list) or not nested:
                return None
            result: list[str] = []
            for nested_id in nested:
                resolved = expand(nested_id, {*ancestors, node_id})
                if resolved is None:
                    return None
                result.extend(resolved)
            return result

        for chain in self.chains:
            flattened: list[str] = []
            valid = True
            for node_id in chain.hop_node_ids:
                resolved = expand(node_id, set())
                if resolved is None:
                    valid = False
                    break
                flattened.extend(resolved)
            if valid:
                chain.hop_node_ids = flattened

        self.nodes = [node for node in self.nodes if node.node_type != LEGACY_CHAIN_NODE_TYPE]

    def _ensure_default_port_mappings(self) -> None:
        """Collapse old custom bindings to one automatic local port per chain."""
        chain_ids = {chain.chain_id for chain in self.chains}
        unique_mappings: list[PortMapping] = []
        mapped_chain_ids: set[str] = set()
        used_ports: set[int] = set()
        for mapping in self.port_mappings:
            if mapping.chain_id not in chain_ids or mapping.chain_id in mapped_chain_ids:
                continue
            if mapping.listen_port in used_ports:
                continue
            unique_mappings.append(mapping)
            mapped_chain_ids.add(mapping.chain_id)
            used_ports.add(mapping.listen_port)
        self.port_mappings = unique_mappings

        next_port = 20001
        for chain in self.chains:
            if chain.chain_id in mapped_chain_ids:
                continue
            while next_port in used_ports:
                next_port += 1
            self.port_mappings.append(PortMapping(listen_port=next_port, chain_id=chain.chain_id))
            used_ports.add(next_port)
            mapped_chain_ids.add(chain.chain_id)
            next_port += 1

    # ================================================================
    # 方便的工具方法
    # ================================================================

    def get_nodes_for_chain(self, chain: Chain) -> list[Node]:
        """Resolve a chain to its concrete base nodes; fail closed on broken IDs."""
        result: list[Node] = []
        for node_id in chain.hop_node_ids:
            node = self.find_node_by_id(node_id)
            if node is None or node.node_type == LEGACY_CHAIN_NODE_TYPE:
                return []
            result.append(node)
        return result
