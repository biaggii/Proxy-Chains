"""
singbox_adapter.py — sing-box 核心的配置生成器

這是最重要的 adapter，完整支援：
  - 多端口（每個 PortMapping 一個 mixed inbound）
  - 多跳鏈（用 detour 串接 hop outbound）
  - 路由規則（每個 inbound tag 導到對應的 chain 最後一跳）

sing-box 配置結構（簡化版）：
{
  "inbounds": [ { "type": "mixed", "tag": "IN_20001", "listen": "::", "listen_port": 20001 }, ... ],
  "outbounds": [
    // 每條 chain 的 hop outbound（用 detour 串起來）
    { "tag": "CHAIN_c1_H1", ... },
    { "tag": "CHAIN_c1_H2", ..., "detour": "CHAIN_c1_H1" },
    { "tag": "CHAIN_c1_H3", ..., "detour": "CHAIN_c1_H2" },
    // 必要的 direct 和 block outbound
    { "type": "direct", "tag": "DIRECT" },
    { "type": "block", "tag": "BLOCK" }
  ],
  "route": {
    "rules": [
      { "inbound": ["IN_20001"], "outbound": "CHAIN_c1_H3" },
      ...
    ],
    "final": "DIRECT"
  }
}
"""

import copy
import ipaddress
import json
import os
from typing import Any
from urllib.parse import urlsplit

from core.core_adapter_base import CoreAdapterBase
from models.app_state import AppState
from models.node import Node, NODE_TYPE_VMESS, NODE_TYPE_VLESS, NODE_TYPE_TROJAN
from models.node import NODE_TYPE_SS, NODE_TYPE_WG, NODE_TYPE_SOCKS5, NODE_TYPE_HTTP
from models.chain import Chain
from models.port_mapping import PortMapping


class SingBoxAdapter(CoreAdapterBase):
    """sing-box 核心適配器"""

    def adapter_name(self) -> str:
        return "sing-box"

    def config_file_extension(self) -> str:
        return ".json"

    def get_check_command(self, config_path: str, exe_path: str) -> list[str]:
        return [exe_path, "check", "-c", config_path]

    def get_start_command(self, config_path: str, exe_path: str) -> list[str]:
        return [exe_path, "run", "-c", config_path]

    def generate_config(self, app_state: AppState) -> tuple[str, str]:
        """
        產生 sing-box 的完整 JSON 配置。
        回傳 (config_text, config_file_path)。
        """
        # ---------- 1. 建立 inbounds ----------
        inbounds_list = _build_inbounds(app_state.port_mappings, app_state)

        # ---------- 2. 建立 outbounds ----------
        outbounds_list: list[dict] = []
        endpoints_list: list[dict] = []
        # 收集所有會用到的 chain，以及每條 chain 的「最後一跳 tag」
        chain_final_tag_map: dict[str, str] = {}

        active_chain_ids = list(dict.fromkeys(pm.chain_id for pm in app_state.port_mappings))
        if app_state.enable_tun and app_state.tun_chain_id:
            if app_state.tun_chain_id not in active_chain_ids:
                active_chain_ids.append(app_state.tun_chain_id)

        for cid in active_chain_ids:
            chain = app_state.find_chain_by_id(cid)
            if chain is None:
                continue
            # 如果這條 chain 已經處理過了，跳過
            if chain.chain_id in chain_final_tag_map:
                continue

            # 取得 chain 的所有 hop 節點
            hop_nodes = app_state.get_nodes_for_chain(chain)
            if len(hop_nodes) == 0:
                continue

            # 為這條 chain 產生 hop outbounds
            hop_outbounds, hop_endpoints, final_tag = _build_chain_outbounds(
                chain.chain_id, hop_nodes, app_state
            )
            outbounds_list.extend(hop_outbounds)
            endpoints_list.extend(hop_endpoints)
            chain_final_tag_map[chain.chain_id] = final_tag

        # 加上必要的 direct outbound
        outbounds_list.append({"type": "direct", "tag": "DIRECT"})

        # ---------- 3. 建立路由規則 ----------
        route_rules = _build_route_rules(
            app_state.port_mappings, chain_final_tag_map, app_state
        )
        
        # 阻擋所有 IPv6 流量 (使用 action: reject 取代 outbound: BLOCK)
        if not app_state.enable_ipv6:
            route_rules.insert(0, {"ip_version": 6, "action": "reject"})
            
        # 防止 TUN 路由迴圈、攔截 DNS，並讓區網維持直連
        if app_state.enable_tun:
            route_rules.insert(0, {
                "ip_cidr": ["127.0.0.0/8"],
                "outbound": "DIRECT"
            })
            route_rules.insert(0, {
                "process_name": [
                    "sing-box.exe", "xray.exe", "mihomo.exe",
                    "ChainPortGateway.exe", "ChainPortGateway",
                    "python.exe", "pythonw.exe"
                ],
                "outbound": "DIRECT"
            })
            route_rules.insert(0, {
                "ip_is_private": True,
                "outbound": "DIRECT"
            })
        # Match v2rayN's DNS interception and TLS record-fragment route options.
        # These rules must also apply when TUN is disabled and traffic enters
        # through a local mixed inbound.
        front_rules: list[dict] = []
        if app_state.enable_sniffing:
            front_rules.append({"action": "sniff"})
            front_rules.append({
                "type": "logical",
                "mode": "or",
                "rules": [{"port": [53]}, {"protocol": ["dns"]}],
                "action": "hijack-dns",
            })
        else:
            front_rules.append({"port": [53], "action": "hijack-dns"})

        if app_state.enable_final_fragment:
            fragment_rule: dict[str, Any] = {
                "action": "route-options",
                "tls_record_fragment": True,
            }
            if app_state.enable_sniffing:
                fragment_rule["protocol"] = ["tls"]
            front_rules.append(fragment_rule)

        if app_state.block_quic:
            front_rules.append({
                "network": ["udp"],
                "port": [443],
                "action": "reject",
            })

        route_rules = front_rules + route_rules

        dns_config = _build_dns_config(chain_final_tag_map, app_state)

        # ---------- 4. 組裝完整配置 ----------
        full_config: dict[str, Any] = {
            "log": {"level": app_state.log_level, "timestamp": True},
            "dns": dns_config,
            "inbounds": inbounds_list,
            "outbounds": outbounds_list,
            "route": {
                "rules": route_rules,
                "auto_detect_interface": True if app_state.enable_tun else False,
                "final": chain_final_tag_map.get(app_state.tun_chain_id, "DIRECT") if app_state.enable_tun else "DIRECT",
                "default_domain_resolver": {
                    "server": "direct_dns",
                    "strategy": "ipv4_only" if not app_state.enable_ipv6 else "prefer_ipv4",
                },
            },
        }
        if endpoints_list:
            full_config["endpoints"] = endpoints_list
        
        # ---------- 5. 寫入檔案 ----------
        config_text = json.dumps(full_config, ensure_ascii=False, indent=2)
        config_file = os.path.join(
            app_state.config_output_dir, "singbox_config.json"
        )
        os.makedirs(os.path.dirname(config_file) or ".", exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_text)

        return config_text, config_file


# ================================================================
# 內部函式：建立 Inbounds
# ================================================================

def _build_inbounds(port_mappings: list[PortMapping], app_state: AppState) -> list[dict]:
    """
    每個 PortMapping 對應一個 mixed inbound。
    tag 格式：IN_<port>
    """
    inbounds: list[dict] = []
    
    if app_state.enable_tun and app_state.tun_chain_id:
        tun_inbound: dict[str, Any] = {
            "type": "tun",
            "tag": "IN_TUN",
            "interface_name": "singbox_tun",
            "address": ["172.19.0.1/30"],
            "mtu": 9000,
            "auto_route": True,
            "strict_route": True,
            # mixed stack 會優先走系統 TCP stack，通常比 gvisor 更省 CPU。
            "stack": "mixed",
        }
        inbounds.append(tun_inbound)

    for pm in port_mappings:
        inbound_dict: dict = {
            "type": "mixed",
            "tag": f"IN_{pm.listen_port}",
            "listen": pm.listen_host,
            "listen_port": pm.listen_port,
        }
            
        inbounds.append(inbound_dict)
    return inbounds


def _build_dns_config(
    chain_final_tag_map: dict[str, str],
    app_state: AppState,
) -> dict[str, Any]:
    """Route each local inbound's DNS through the same outbound chain as its traffic."""
    parsed_dns = urlsplit((app_state.remote_dns_url or "").strip())
    if parsed_dns.scheme.lower() != "https" or not parsed_dns.hostname:
        raise ValueError(
            "Remote DNS must be an HTTPS URL, for example "
            "https://cloudflare-dns.com/dns-query."
        )

    bootstrap_dns = (app_state.bootstrap_dns or "").strip()
    if not bootstrap_dns:
        raise ValueError("Bootstrap DNS address cannot be empty.")

    # Keep the same three-stage DNS bootstrap used by the supplied working
    # v2rayN config: literal-IP bootstrap, static hosts for DNS provider names,
    # then DoH through the selected proxy chain. Resolving the DoH hostname
    # with the ISP-facing bootstrap resolver was the important mismatch.
    servers: list[dict[str, Any]] = [
        {
            "tag": "local_dns",
            "type": "udp",
            "server": bootstrap_dns,
        },
        {
            "tag": "direct_dns",
            "type": "udp",
            "server": bootstrap_dns,
            "domain_resolver": "local_dns",
        },
        {
            "tag": "hosts_dns",
            "type": "hosts",
            "predefined": {
                "dns.google": ["8.8.8.8", "8.8.4.4", "2001:4860:4860::8888", "2001:4860:4860::8844"],
                "dns.alidns.com": ["223.5.5.5", "223.6.6.6", "2400:3200::1", "2400:3200:baba::1"],
                "one.one.one.one": ["1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001"],
                "1dot1dot1dot1.cloudflare-dns.com": ["1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001"],
                "cloudflare-dns.com": ["104.16.249.249", "104.16.248.249", "2606:4700::6810:f8f9", "2606:4700::6810:f9f9"],
                "dns.cloudflare.com": ["162.159.61.8", "172.64.41.8", "2a06:98c1:52::8", "2803:f800:53::8"],
                "dot.pub": ["1.12.12.12", "120.53.53.53"],
                "doh.pub": ["1.12.12.12", "120.53.53.53"],
                "dns.quad9.net": ["9.9.9.9", "149.112.112.112", "2620:fe::fe", "2620:fe::9"],
                "dns.yandex.net": ["77.88.8.8", "77.88.8.1", "2a02:6b8::feed:0ff", "2a02:6b8:0:1::feed:0ff"],
                "dns.sb": ["45.11.45.11", "185.222.222.222", "2a09::", "2a11::"],
                "dns.umbrella.com": ["208.67.220.220", "208.67.222.222", "2620:119:35::35", "2620:119:53::53"],
                "dns.sse.cisco.com": ["208.67.220.220", "208.67.222.222", "2620:119:35::35", "2620:119:53::53"],
                "engage.cloudflareclient.com": ["162.159.192.1", "2606:4700:d0::a29f:c001"],
            },
        },
    ]
    rules: list[dict[str, Any]] = []
    remote_tag_by_chain: dict[str, str] = {}

    for chain_id, outbound_tag in chain_final_tag_map.items():
        remote_tag = f"remote_dns_{chain_id}"
        remote_server: dict[str, Any] = {
            "tag": remote_tag,
            "type": "https",
            "server": parsed_dns.hostname,
            "path": parsed_dns.path or "/dns-query",
            "domain_resolver": "hosts_dns",
            "detour": outbound_tag,
        }
        if parsed_dns.port:
            remote_server["server_port"] = parsed_dns.port
        servers.append(remote_server)
        remote_tag_by_chain[chain_id] = remote_tag

    for mapping in app_state.port_mappings:
        remote_tag = remote_tag_by_chain.get(mapping.chain_id)
        if remote_tag:
            rules.append({
                "inbound": [f"IN_{mapping.listen_port}"],
                "action": "route",
                "server": remote_tag,
            })

    default_chain_id = ""
    if app_state.enable_tun and app_state.tun_chain_id in remote_tag_by_chain:
        default_chain_id = app_state.tun_chain_id
    elif app_state.port_mappings:
        default_chain_id = app_state.port_mappings[0].chain_id

    default_remote_tag = remote_tag_by_chain.get(default_chain_id, "direct_dns")
    if app_state.enable_tun and app_state.tun_chain_id in remote_tag_by_chain:
        rules.append({
            "inbound": ["IN_TUN"],
            "action": "route",
            "server": remote_tag_by_chain[app_state.tun_chain_id],
        })

    return {
        "servers": servers,
        "rules": [{"server": "hosts_dns", "preferred_by": "hosts_dns"}, *rules],
        "final": default_remote_tag,
        "strategy": "ipv4_only" if not app_state.enable_ipv6 else "prefer_ipv4",
    }


# ================================================================
# 內部函式：建立 Chain 的 Hop Outbounds（用 detour 串起來）
# ================================================================

def _build_chain_outbounds(
    chain_id: str,
    hop_nodes: list[Node],
    app_state: AppState,
) -> tuple[list[dict], list[dict], str]:
    """
    為一條 chain 產生所有的 hop outbound。

    sing-box 的 detour 是「反向串」：
      chain hops: [A, B, C]
      H1 = clone(A)                     → 直連到 A
      H2 = clone(B) + detour = H1      → B 透過 A 出去
      H3 = clone(C) + detour = H2      → C 透過 B 出去（B 又透過 A）

    回傳值：
    - hop_outbounds: list of outbound dict
    - final_tag: 最後一跳的 tag（route 要指向這個）
    """
    hop_outbounds: list[dict] = []
    hop_endpoints: list[dict] = []
    tcp_only_chain = _chain_uses_tcp_only_upstream(hop_nodes)
    if tcp_only_chain and any(node.node_type == NODE_TYPE_WG for node in hop_nodes[1:]):
        raise ValueError(
            "WireGuard cannot be used after a TCP-only local SOCKS5 upstream "
            "such as Wireproxy. Use a UDP-capable upstream or a TCP-based "
            "second-hop protocol."
        )
    if not app_state.enable_udp and any(node.node_type == NODE_TYPE_WG for node in hop_nodes):
        raise ValueError(
            "WireGuard requires UDP forwarding to be enabled."
        )
    tcp_only_chain = tcp_only_chain or not app_state.enable_udp

    for hop_index, node in enumerate(hop_nodes):
        hop_number = hop_index + 1
        tag = f"CHAIN_{chain_id}_H{hop_number}"

        # 把 Node 轉成 sing-box outbound dict
        if node.node_type == NODE_TYPE_WG:
            outbound = _wireguard_endpoint(node, tag)
            target_list = hop_endpoints
        else:
            outbound = _node_to_singbox_outbound(
                node, tag, app_state, tcp_only=tcp_only_chain
            )
            target_list = hop_outbounds

        # 第 2 跳開始，加 detour 指向上一跳
        if hop_index > 0:
            prev_tag = f"CHAIN_{chain_id}_H{hop_number - 1}"
            outbound["detour"] = prev_tag

        target_list.append(outbound)

    # 最後一跳的 tag
    final_tag = f"CHAIN_{chain_id}_H{len(hop_nodes)}"

    return hop_outbounds, hop_endpoints, final_tag


# ================================================================
# 內部函式：Node -> sing-box outbound dict
# ================================================================

def _node_to_singbox_outbound(
    node: Node, tag: str, app_state: AppState, tcp_only: bool = False
) -> dict:
    """
    把一個 Node 轉成 sing-box 的 outbound JSON dict。
    每種協議的欄位不同，所以分開處理。
    """
    ob = {}
    if node.node_type == NODE_TYPE_VMESS:
        ob = _vmess_outbound(node, tag)
    elif node.node_type == NODE_TYPE_VLESS:
        ob = _vless_outbound(node, tag)
    elif node.node_type == NODE_TYPE_TROJAN:
        ob = _trojan_outbound(node, tag)
    elif node.node_type == NODE_TYPE_SS:
        ob = _ss_outbound(node, tag)
    elif node.node_type == NODE_TYPE_SOCKS5:
        ob = _socks5_outbound(node, tag)
    elif node.node_type == NODE_TYPE_HTTP:
        ob = _http_outbound(node, tag)
    else:
        # 不認識的類型，當作 socks 處理
        ob = _socks5_outbound(node, tag)
        
    _apply_advanced_outbound_settings(ob, app_state)
    if (
        app_state.enable_fragment
        and ob.get("type") in {"vmess", "vless", "trojan"}
        and isinstance(ob.get("tls"), dict)
    ):
        ob["tls"]["fragment"] = True
        ob["tls"]["record_fragment"] = True
    if tcp_only and ob.get("type") in {
        "socks", "vmess", "vless", "trojan", "shadowsocks"
    }:
        ob["network"] = "tcp"
    return ob


def _chain_uses_tcp_only_upstream(hop_nodes: list[Node]) -> bool:
    """Detect a local SOCKS5 first hop, such as Wireproxy's TCP-only listener."""
    if not hop_nodes or hop_nodes[0].node_type != NODE_TYPE_SOCKS5:
        return False

    server = (hop_nodes[0].server or "").strip().strip("[]").lower()
    if server == "localhost":
        return True
    try:
        return ipaddress.ip_address(server).is_loopback
    except ValueError:
        return False


def _apply_advanced_outbound_settings(ob: dict, app_state: AppState) -> None:
    """套用較保守的 outbound 穩定性設定。"""
    if ob.get("type") != "direct" and ob.get("type") != "block":
        # 只保留連線超時，避免強制開啟高風險的 TCP 特性造成斷流。
        ob["connect_timeout"] = "10s"

    # 處理 insecure
    if app_state.allow_insecure and "tls" in ob:
        ob["tls"]["insecure"] = True

    # 處理 mux
    if app_state.enable_mux and ob.get("type") in ["vmess", "vless", "trojan", "shadowsocks"]:
        ob["multiplex"] = {
            "enabled": True,
            "protocol": app_state.singbox_mux_protocol
        }


def _vmess_outbound(node: Node, tag: str) -> dict:
    """vmess outbound"""
    ob: dict[str, Any] = {
        "type": "vmess",
        "tag": tag,
        "server": node.server,
        "server_port": node.port,
        "uuid": node.uuid_str or "",
        "alter_id": node.alter_id,
        "security": node.security or "auto",
    }
    # 加 TLS
    _add_tls_if_needed(ob, node)
    # 加傳輸層
    _add_transport_if_needed(ob, node)
    return ob


def _vless_outbound(node: Node, tag: str) -> dict:
    """vless outbound"""
    ob: dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "server": node.server,
        "server_port": node.port,
        "uuid": node.uuid_str or "",
        "packet_encoding": "xudp",
    }
    if node.flow:
        ob["flow"] = node.flow
    _add_tls_if_needed(ob, node)
    _add_transport_if_needed(ob, node)
    return ob


def _trojan_outbound(node: Node, tag: str) -> dict:
    """trojan outbound"""
    ob: dict[str, Any] = {
        "type": "trojan",
        "tag": tag,
        "server": node.server,
        "server_port": node.port,
        "password": node.password or "",
    }
    _add_tls_if_needed(ob, node)
    _add_transport_if_needed(ob, node)
    return ob


def _ss_outbound(node: Node, tag: str) -> dict:
    """shadowsocks outbound"""
    ob: dict[str, Any] = {
        "type": "shadowsocks",
        "tag": tag,
        "server": node.server,
        "server_port": node.port,
        "method": node.encryption or "aes-256-gcm",
        "password": node.password or "",
    }
    plugin = node.extra.get("plugin")
    if plugin == "obfs":
        plugin_opts = node.extra.get("plugin_opts", {})
        obfs_mode = plugin_opts.get("mode", "http")
        obfs_host = plugin_opts.get("host", "")
        ob["plugin"] = "obfs"
        ob["plugin_opts"] = {
            "mode": obfs_mode,
            "host": obfs_host
        }
    return ob


def _wireguard_endpoint(node: Node, tag: str) -> dict:
    """Build the sing-box 1.11+ WireGuard endpoint (the legacy outbound was removed)."""
    extra = node.extra if isinstance(node.extra, dict) else {}
    reserved = extra.get("wg_reserved", extra.get("reserved"))
    if isinstance(reserved, str):
        reserved = [part.strip() for part in reserved.split(",") if part.strip()]
    if reserved is not None:
        reserved = [int(value) for value in reserved]

    allowed_ips = extra.get("wg_allowed_ips") or ["0.0.0.0/0", "::/0"]
    if isinstance(allowed_ips, str):
        allowed_ips = [value.strip() for value in allowed_ips.split(",") if value.strip()]

    peer: dict[str, Any] = {
        "address": node.server,
        "port": node.port,
        "public_key": node.wg_public_key or "",
        "allowed_ips": allowed_ips,
    }
    preshared_key = extra.get("wg_preshared_key") or extra.get("preshared_key")
    if preshared_key:
        peer["pre_shared_key"] = preshared_key
    if reserved is not None:
        peer["reserved"] = reserved

    endpoint: dict[str, Any] = {
        "type": "wireguard",
        "tag": tag,
        "address": [node.wg_local_address] if node.wg_local_address else ["172.16.0.2/32"],
        "private_key": node.wg_private_key or "",
        "peers": [peer],
    }
    mtu = extra.get("wg_mtu", extra.get("mtu"))
    if mtu:
        endpoint["mtu"] = int(mtu)
    return endpoint


def _socks5_outbound(node: Node, tag: str) -> dict:
    """socks outbound"""
    ob: dict[str, Any] = {
        "type": "socks",
        "tag": tag,
        "server": node.server,
        "server_port": node.port,
        "version": "5",
    }
    if node.username:
        ob["username"] = node.username
    if node.password:
        ob["password"] = node.password
    return ob


def _http_outbound(node: Node, tag: str) -> dict:
    """http outbound"""
    ob: dict[str, Any] = {
        "type": "http",
        "tag": tag,
        "server": node.server,
        "server_port": node.port,
    }
    if node.username:
        ob["username"] = node.username
    if node.password:
        ob["password"] = node.password
    if node.tls_enabled:
        ob["tls"] = {"enabled": True}
    return ob


# ================================================================
# 內部函式：TLS 和傳輸層的共用邏輯
# ================================================================

def _add_tls_if_needed(ob: dict, node: Node) -> None:
    """如果節點有啟用 TLS，加入 tls 區段"""
    if not node.tls_enabled:
        return
    tls_dict: dict[str, Any] = {"enabled": True}
    if node.sni:
        tls_dict["server_name"] = node.sni
    if node.alpn:
        tls_dict["alpn"] = node.alpn
    # 如果有 reality 相關設定
    security_type = node.extra.get("security", "")
    query = node.extra.get("query", {})
    if not isinstance(query, dict):
        query = {}

    def query_value(name: str) -> str:
        value = query.get(name, "")
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value) if value is not None else ""

    fingerprint = query_value("fp")
    if fingerprint:
        tls_dict["utls"] = {
            "enabled": True,
            "fingerprint": fingerprint,
        }

    if security_type == "reality":
        reality_dict: dict[str, Any] = {"enabled": True}
        pbk = query_value("pbk")
        sid = query_value("sid")
        if pbk:
            reality_dict["public_key"] = pbk
        if sid:
            reality_dict["short_id"] = sid
        tls_dict["reality"] = reality_dict
    # 跳過憑證驗證
    if node.extra.get("skip_cert_verify"):
        tls_dict["insecure"] = True
    ob["tls"] = tls_dict


def _add_transport_if_needed(ob: dict, node: Node) -> None:
    """如果節點有非 tcp 的傳輸層，加入 transport 區段"""
    network = node.network
    if not network or network == "tcp":
        return

    transport_dict: dict[str, Any] = {}

    if network == "ws":
        transport_dict["type"] = "ws"
        if node.path:
            transport_dict["path"] = node.path
        if node.host:
            transport_dict["headers"] = {"Host": node.host}

    elif network == "grpc" or network == "gun":
        transport_dict["type"] = "grpc"
        if node.path:
            transport_dict["service_name"] = node.path

    elif network in ("h2", "http"):
        transport_dict["type"] = "http"
        if node.path:
            transport_dict["path"] = node.path
        if node.host:
            transport_dict["host"] = [node.host]

    else:
        # 其他傳輸類型，先不處理
        return

    ob["transport"] = transport_dict


# ================================================================
# 內部函式：建立路由規則
# ================================================================

def _build_route_rules(
    port_mappings: list[PortMapping],
    chain_final_tag_map: dict[str, str],
    app_state: AppState,
) -> list[dict]:
    """
    每個 PortMapping 產生一條路由規則：
      inbound tag = IN_<port>  →  outbound tag = CHAIN_<chain_id>_H<last>
    """
    rules: list[dict] = []
    
    if app_state.enable_tun and app_state.tun_chain_id:
        final_tag = chain_final_tag_map.get(app_state.tun_chain_id)
        if final_tag:
            rules.append({
                "inbound": ["IN_TUN"],
                "outbound": final_tag,
            })
            
    for pm in port_mappings:
        final_tag = chain_final_tag_map.get(pm.chain_id)
        if final_tag is None:
            continue  # 這個 port mapping 的 chain 沒有有效節點
        rule_dict: dict = {
            "inbound": [f"IN_{pm.listen_port}"],
            "outbound": final_tag,
        }
        rules.append(rule_dict)
    return rules
