"""
mihomo_adapter.py — Mihomo (Clash.Meta) 核心的配置生成器

最小可用版本，支援：
  - 多端口（每個 PortMapping 一個 mixed-port listener）
  - 兩跳鏈（用 dialer-proxy 串接）

Mihomo 鏈式原理（dialer-proxy）：
  chain hops: [A, B]
  proxies:
    - name: CHAIN_c1_H1   # A 的配置
    - name: CHAIN_c1_H2   # B 的配置 + dialer-proxy: CHAIN_c1_H1

  三跳以上：
    - name: CHAIN_c1_H1   # A
    - name: CHAIN_c1_H2   # B + dialer-proxy: CHAIN_c1_H1
    - name: CHAIN_c1_H3   # C + dialer-proxy: CHAIN_c1_H2

Mihomo listeners 格式：
  listeners:
    - name: IN_20001
      type: mixed
      port: 20001
      proxy: CHAIN_c1_H2

TODO: 完整多跳已實作，但某些 Mihomo 版本可能不支援 3 跳以上的 dialer-proxy。
      如遇到問題，請升級到最新版 mihomo。
"""

import os
from typing import Any

import yaml

from core.core_adapter_base import CoreAdapterBase
from models.app_state import AppState
from models.node import Node, NODE_TYPE_VMESS, NODE_TYPE_VLESS, NODE_TYPE_TROJAN
from models.node import NODE_TYPE_SS, NODE_TYPE_WG, NODE_TYPE_SOCKS5, NODE_TYPE_HTTP
from models.port_mapping import PortMapping


class MihomoAdapter(CoreAdapterBase):
    """Mihomo (Clash.Meta) 核心適配器"""

    def adapter_name(self) -> str:
        return "mihomo"

    def config_file_extension(self) -> str:
        return ".yaml"

    def get_check_command(self, config_path: str, exe_path: str) -> list[str]:
        # mihomo 沒有 check 指令，用 -t 測試
        return [exe_path, "-t", "-f", config_path]

    def get_start_command(self, config_path: str, exe_path: str) -> list[str]:
        return [exe_path, "-f", config_path]

    def generate_config(self, app_state: AppState) -> tuple[str, str]:
        """產生 Mihomo 的完整 YAML 配置"""

        # ---------- 1. proxies（所有 chain 的 hop outbound） ----------
        proxies_list: list[dict] = []
        chain_final_name_map: dict[str, str] = {}

        active_chain_ids = {pm.chain_id for pm in app_state.port_mappings}
        if app_state.enable_tun and app_state.tun_chain_id:
            active_chain_ids.add(app_state.tun_chain_id)

        for cid in active_chain_ids:
            chain = app_state.find_chain_by_id(cid)
            if chain is None:
                continue
            if chain.chain_id in chain_final_name_map:
                continue

            hop_nodes = app_state.get_nodes_for_chain(chain)
            if len(hop_nodes) == 0:
                continue

            hop_proxies, final_name = _build_mihomo_chain_proxies(
                chain.chain_id, hop_nodes, app_state
            )
            proxies_list.extend(hop_proxies)
            chain_final_name_map[chain.chain_id] = final_name

        # ---------- 2. listeners ----------
        listeners_list = _build_mihomo_listeners(
            app_state.port_mappings, chain_final_name_map
        )

        # ---------- 3. 組裝 ----------
        full_config: dict[str, Any] = {
            "ipv6": app_state.enable_ipv6,
            "mixed-port": 7890,       # 預設的全域 port（可能不會用到）
            "allow-lan": app_state.allow_lan,
            "mode": "rule",
            "log-level": app_state.log_level,
            "dns": {
                "enable": True,
                "ipv6": app_state.enable_ipv6,
                "nameserver": ["8.8.8.8", "1.1.1.1"]
            },
            "proxies": proxies_list,
            "listeners": listeners_list,
        }
        # Default catch-all rule
        match_rule = "MATCH,DIRECT"
        
        if app_state.enable_tun and app_state.tun_chain_id:
            full_config["tun"] = {
                "enable": True,
                "stack": "system",
                "device": "mihomo-tun",
                "auto-route": True,
                "auto-detect-interface": True,
                "dns-hijack": ["any:53", "tcp://any:53"]
            }
            # Prevent routing loops by excluding core processes
            full_config["tun"]["process-name-filter"] = [
                "sing-box.exe", "xray.exe", "mihomo.exe",
                "ChainPortGateway.exe", "ChainPortGateway",
                "python.exe", "pythonw.exe"
            ]
            
            final_name = chain_final_name_map.get(app_state.tun_chain_id)
            if final_name:
                # Add DNS hijacking and local routing safety
                full_config["rules"] = [
                    f"PROCESS-NAME,mihomo.exe,DIRECT",
                    f"PROCESS-NAME,sing-box.exe,DIRECT",
                    f"PROCESS-NAME,xray.exe,DIRECT",
                    "IP-CIDR,192.168.0.0/16,DIRECT",
                    "IP-CIDR,10.0.0.0/8,DIRECT",
                    "IP-CIDR,127.0.0.0/8,DIRECT",
                    f"MATCH,{final_name}"
                ]
        else:
            full_config["rules"] = ["MATCH,DIRECT"]

        # ---------- 4. 寫檔 ----------
        config_text = yaml.dump(
            full_config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        config_file = os.path.join(
            app_state.config_output_dir, "mihomo_config.yaml"
        )
        os.makedirs(os.path.dirname(config_file) or ".", exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_text)

        return config_text, config_file


# ================================================================
# Chain Proxies（用 dialer-proxy 串鏈）
# ================================================================

def _build_mihomo_chain_proxies(
    chain_id: str,
    hop_nodes: list[Node],
    app_state: AppState
) -> tuple[list[dict], str]:
    """
    Mihomo 的鏈式用 dialer-proxy 串接：
      H1 = A（直連）
      H2 = B + dialer-proxy: H1
      H3 = C + dialer-proxy: H2
    """
    hop_proxies: list[dict] = []

    for hop_index, node in enumerate(hop_nodes):
        hop_number = hop_index + 1
        name = f"CHAIN_{chain_id}_H{hop_number}"

        proxy = _node_to_mihomo_proxy(node, name, app_state)

        # 第 2 跳開始加 dialer-proxy
        if hop_index > 0:
            prev_name = f"CHAIN_{chain_id}_H{hop_number - 1}"
            proxy["dialer-proxy"] = prev_name

        hop_proxies.append(proxy)

    final_name = f"CHAIN_{chain_id}_H{len(hop_nodes)}"
    return hop_proxies, final_name


# ================================================================
# Node -> Mihomo proxy dict
# ================================================================

def _node_to_mihomo_proxy(node: Node, name: str, app_state: AppState) -> dict:
    """把 Node 轉成 Mihomo proxy dict"""
    ob: dict = {}
    if node.node_type == NODE_TYPE_VMESS:
        ob = _mihomo_vmess(node, name)
    elif node.node_type == NODE_TYPE_VLESS:
        ob = _mihomo_vless(node, name)
    elif node.node_type == NODE_TYPE_TROJAN:
        ob = _mihomo_trojan(node, name)
    elif node.node_type == NODE_TYPE_SS:
        ob = _mihomo_ss(node, name)
    elif node.node_type == NODE_TYPE_WG:
        ob = _mihomo_wg(node, name)
    elif node.node_type == NODE_TYPE_SOCKS5:
        ob = _mihomo_socks5(node, name)
    elif node.node_type == NODE_TYPE_HTTP:
        ob = _mihomo_http(node, name)
    else:
        ob = _mihomo_socks5(node, name)

    # 進階設定：允許不安全憑證
    if app_state.allow_insecure and ob.get("tls", False):
        ob["skip-cert-verify"] = True

    # 進階設定：Mux 多路復用
    if app_state.enable_mux and ob.get("type") in ["vmess", "vless", "trojan"]:
        ob["smux"] = {
            "enabled": True,
            "protocol": "smux",
        }

    return ob


def _mihomo_vmess(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "vmess",
        "server": node.server,
        "port": node.port,
        "uuid": node.uuid_str or "",
        "alterId": node.alter_id,
        "cipher": node.security or "auto",
        "tls": node.tls_enabled,
    }
    if node.sni:
        p["servername"] = node.sni
    if node.network and node.network != "tcp":
        p["network"] = node.network
        _mihomo_add_transport(p, node)
    return p


def _mihomo_vless(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "vless",
        "server": node.server,
        "port": node.port,
        "uuid": node.uuid_str or "",
        "tls": node.tls_enabled,
    }
    if node.flow:
        p["flow"] = node.flow
    if node.sni:
        p["servername"] = node.sni
    if node.network and node.network != "tcp":
        p["network"] = node.network
        _mihomo_add_transport(p, node)
    return p


def _mihomo_trojan(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "trojan",
        "server": node.server,
        "port": node.port,
        "password": node.password or "",
        "sni": node.sni or node.server,
    }
    if node.alpn:
        p["alpn"] = node.alpn
    if node.network and node.network != "tcp":
        p["network"] = node.network
        _mihomo_add_transport(p, node)
    return p


def _mihomo_ss(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "ss",
        "server": node.server,
        "port": node.port,
        "cipher": node.encryption or "aes-256-gcm",
        "password": node.password or "",
    }
    plugin = node.extra.get("plugin")
    if plugin:
        p["plugin"] = plugin
        plugin_opts = node.extra.get("plugin_opts")
        if isinstance(plugin_opts, dict):
            p["plugin-opts"] = plugin_opts
    return p


def _mihomo_wg(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "wireguard",
        "server": node.server,
        "port": node.port,
        "ip": node.wg_local_address or "",
        "public-key": node.wg_public_key or "",
        "private-key": node.wg_private_key or "",
        "udp": True,
    }
    return p


def _mihomo_socks5(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "socks5",
        "server": node.server,
        "port": node.port,
    }
    if node.username:
        p["username"] = node.username
    if node.password:
        p["password"] = node.password
    return p


def _mihomo_http(node: Node, name: str) -> dict:
    p: dict[str, Any] = {
        "name": name,
        "type": "http",
        "server": node.server,
        "port": node.port,
    }
    if node.username:
        p["username"] = node.username
    if node.password:
        p["password"] = node.password
    if node.tls_enabled:
        p["tls"] = True
    return p


def _mihomo_add_transport(p: dict, node: Node) -> None:
    """加入 ws / grpc / h2 傳輸層參數"""
    if node.network == "ws":
        ws_opts: dict[str, Any] = {}
        if node.path:
            ws_opts["path"] = node.path
        if node.host:
            ws_opts["headers"] = {"Host": node.host}
        p["ws-opts"] = ws_opts
    elif node.network in ("grpc", "gun"):
        grpc_opts: dict[str, Any] = {}
        if node.path:
            grpc_opts["grpc-service-name"] = node.path
        p["grpc-opts"] = grpc_opts
    elif node.network in ("h2", "http"):
        h2_opts: dict[str, Any] = {}
        if node.path:
            h2_opts["path"] = node.path
        if node.host:
            h2_opts["host"] = [node.host]
        p["h2-opts"] = h2_opts


# ================================================================
# Listeners
# ================================================================

def _build_mihomo_listeners(
    port_mappings: list[PortMapping],
    chain_final_name_map: dict[str, str],
) -> list[dict]:
    """每個 PortMapping 對應一個 mixed listener，綁定到 chain 的最後一跳"""
    listeners: list[dict] = []
    for pm in port_mappings:
        final_name = chain_final_name_map.get(pm.chain_id)
        if final_name is None:
            continue
        listener: dict[str, Any] = {
            "name": f"IN_{pm.listen_port}",
            "type": "mixed",
            "port": pm.listen_port,
            "listen": pm.listen_host,
            "proxy": final_name,
        }
        listeners.append(listener)
    return listeners
