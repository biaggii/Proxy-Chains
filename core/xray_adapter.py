"""
xray_adapter.py — Xray 核心的配置生成器

完整支援：
  - 單一共享 Base Node SOCKS inbound
  - 多端口（每個 Chain PortMapping 一個 socks inbound）
  - 多跳鏈（用 streamSettings.sockopt.dialerProxy 串接 hop outbound）
  - 路由規則（每個 inbound tag 導到對應的 chain 最後一跳）

Xray 鏈式原理：
  chain hops: [A, B, C]
  H1 = clone(A)                                          → 直連到 A
  H2 = clone(B) + sockopt.dialerProxy: "H1"             → B 透過 A 出去
  H3 = clone(C) + sockopt.dialerProxy: "H2"             → C 透過 B 出去

Xray 配置結構：
{
  "inbounds": [ { "protocol": "socks", "tag": "IN_20001", "port": 20001, ... } ],
  "outbounds": [
    { "protocol": "vmess", "tag": "CHAIN_c1_H1", "settings": {...} },
    { "protocol": "trojan", "tag": "CHAIN_c1_H2", "settings": {...},
      "streamSettings": {"sockopt": {"dialerProxy": "CHAIN_c1_H1"}} },
    ...
  ],
  "routing": {
    "rules": [
      { "type": "field", "inboundTag": ["IN_20001"], "outboundTag": "CHAIN_c1_H3" }
    ]
  }
}
"""

import json
import os
from typing import Any
from urllib.parse import urlsplit

from core.core_adapter_base import CoreAdapterBase
from models.app_state import AppState, BASE_NODE_CHAIN_ID, TUN_NODE_CHAIN_ID
from models.node import Node, NODE_TYPE_VMESS, NODE_TYPE_VLESS, NODE_TYPE_TROJAN
from models.node import NODE_TYPE_SS, NODE_TYPE_WG, NODE_TYPE_SOCKS5, NODE_TYPE_HTTP
from models.chain import Chain
from models.port_mapping import PortMapping


class XrayAdapter(CoreAdapterBase):
    """Xray 核心適配器"""

    def adapter_name(self) -> str:
        return "xray"

    def config_file_extension(self) -> str:
        return ".json"

    def get_check_command(self, config_path: str, exe_path: str) -> list[str]:
        return [exe_path, "run", "-test", "-c", config_path]

    def get_start_command(self, config_path: str, exe_path: str) -> list[str]:
        return [exe_path, "run", "-c", config_path]

    def generate_config(self, app_state: AppState) -> tuple[str, str]:
        """產生 Xray 的完整 JSON 配置"""

        # ---------- 1. 建立 inbounds ----------
        inbounds_list = _build_xray_inbounds(app_state.port_mappings, app_state)

        # ---------- 2. 建立 outbounds ----------
        outbounds_list: list[dict] = []
        chain_final_tag_map: dict[str, str] = {}

        active_chain_ids = list(dict.fromkeys(pm.chain_id for pm in app_state.port_mappings))
        if app_state.get_active_base_node():
            active_chain_ids.append(BASE_NODE_CHAIN_ID)
        if app_state.enable_tun and app_state.get_tun_chain():
            active_chain_ids.append(TUN_NODE_CHAIN_ID)

        for cid in active_chain_ids:
            chain = app_state.get_runtime_chain(cid)
            if chain is None:
                continue
            if chain.chain_id in chain_final_tag_map:
                continue

            hop_nodes = app_state.get_nodes_for_chain(chain)
            if len(hop_nodes) == 0:
                continue

            hop_outbounds, final_tag = _build_xray_chain_outbounds(
                chain.chain_id, hop_nodes, app_state
            )
            outbounds_list.extend(hop_outbounds)
            chain_final_tag_map[chain.chain_id] = final_tag

        # 加上 direct 和 block
        outbounds_list.append({
            "protocol": "freedom", "tag": "DIRECT", "settings": {}
        })
        outbounds_list.append({
            "protocol": "blackhole", "tag": "BLOCK", "settings": {}
        })

        # ---------- 3. 建立路由 ----------
        routing_rules = _build_xray_routing(
            app_state.port_mappings, chain_final_tag_map, app_state
        )
        
        # Match v2rayN's Xray route policy for private destinations. The
        # bundled Xray geodata is selected by XRAY_LOCATION_ASSET in the
        # process runner.
        routing_rules.insert(0, {
            "type": "field",
            "domain": ["geosite:private"],
            "outboundTag": "DIRECT"
        })
        routing_rules.insert(0, {
            "type": "field",
            "ip": ["geoip:private"],
            "outboundTag": "DIRECT"
        })

        if app_state.block_quic:
            routing_rules.insert(0, {
                "type": "field",
                "network": "udp",
                "port": "443",
                "outboundTag": "BLOCK",
            })

        if not app_state.enable_ipv6:
            # 阻擋所有 IPv6
            routing_rules.insert(0, {
                "type": "field",
                "ip": ["::/0"],
                "outboundTag": "BLOCK"
            })

        dns_outbound_tag = _select_xray_dns_outbound(
            app_state, app_state.port_mappings, chain_final_tag_map
        )
        routing_rules.insert(0, {
            "type": "field",
            "inboundTag": ["dns-module"],
            "outboundTag": dns_outbound_tag,
        })
        routing_rules.insert(0, {
            "type": "field",
            "inboundTag": ["direct-dns-1"],
            "outboundTag": "DIRECT",
        })

        # ---------- 4. 組裝 ----------
        full_config: dict[str, Any] = {
            "log": {"loglevel": app_state.log_level},
            "dns": _build_xray_dns_config(app_state),
            "inbounds": inbounds_list,
            "outbounds": outbounds_list,
            "routing": {
                "domainStrategy": "AsIs",
                "rules": routing_rules,
            },
        }

        # ---------- 5. 寫檔 ----------
        config_text = json.dumps(full_config, ensure_ascii=False, indent=2)
        config_file = os.path.join(
            app_state.config_output_dir, "xray_config.json"
        )
        os.makedirs(os.path.dirname(config_file) or ".", exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_text)

        return config_text, config_file


# ================================================================
# Inbounds
# ================================================================

def _build_xray_inbounds(port_mappings: list[PortMapping], app_state: AppState) -> list[dict]:
    """每個 PortMapping 對應一個 socks inbound"""
    inbounds: list[dict] = []
    
    if app_state.enable_tun and app_state.get_tun_chain():
        inbounds.append({
            "tag": "IN_TUN",
            "port": 0,
            "protocol": "tun",
            "settings": {
                "network": "127.0.0.1/30",
                "autoRoute": True,
                "strictRoute": True
            }
        })

    if app_state.get_active_base_node():
        inbounds.append({
            "protocol": "socks",
            "tag": "IN_BASE",
            "listen": app_state.base_node_listen_host,
            "port": app_state.base_node_listen_port,
            "settings": {"auth": "noauth", "udp": app_state.enable_udp},
            "sniffing": {
                "enabled": app_state.enable_sniffing,
                "destOverride": ["http", "tls"],
            },
        })
        
    for pm in port_mappings:
        ib: dict[str, Any] = {
            "protocol": "socks",
            "tag": f"IN_{pm.listen_port}",
            "listen": pm.listen_host,
            "port": pm.listen_port,
            "settings": {
                "auth": "noauth",
                "udp": app_state.enable_udp,
            },
            "sniffing": {
                "enabled": app_state.enable_sniffing,
                "destOverride": ["http", "tls"],
            },
        }
        inbounds.append(ib)
    return inbounds


# ================================================================
# Chain Outbounds（用 streamSettings.sockopt.dialerProxy 串鏈）
# ================================================================

def _build_xray_chain_outbounds(
    chain_id: str,
    hop_nodes: list[Node],
    app_state: AppState,
) -> tuple[list[dict], str]:
    """
    Xray 26.9.9+ uses streamSettings.sockopt.dialerProxy:
      H1 = A（直連）
      H2 = B + dialerProxy = H1
      H3 = C + dialerProxy = H2
    """
    hop_outbounds: list[dict] = []

    for hop_index, node in enumerate(hop_nodes):
        hop_number = hop_index + 1
        tag = f"CHAIN_{chain_id}_H{hop_number}"

        outbound = _node_to_xray_outbound(node, tag, app_state)

        # Xray 26.9.9+ removed outbound.proxySettings. Chain through the
        # underlying socket dialer instead so the hop's TLS/transport remains
        # active while its TCP connection is established through the previous hop.
        if hop_index > 0:
            prev_tag = f"CHAIN_{chain_id}_H{hop_number - 1}"
            stream_settings = outbound.setdefault("streamSettings", {"network": "raw"})
            stream_settings.setdefault("network", "raw")
            stream_settings.setdefault("sockopt", {})["dialerProxy"] = prev_tag

        hop_outbounds.append(outbound)

    # v2rayN applies outbound finalmask to TLS nodes that are not themselves
    # dialed through another hop. REALITY cannot use the tlshello packet mode.
    if app_state.enable_fragment:
        for outbound in hop_outbounds:
            stream_settings = outbound.get("streamSettings") or {}
            if not stream_settings.get("security"):
                continue
            if (stream_settings.get("sockopt") or {}).get("dialerProxy"):
                continue
            packet_mask = _build_xray_fragment_mask(app_state)
            if (
                stream_settings.get("security") == "reality"
                and packet_mask["settings"]["packets"] == "tlshello"
            ):
                packet_mask["settings"]["packets"] = "1-3"
            stream_settings["finalmask"] = {"tcp": [packet_mask]}
            outbound["streamSettings"] = stream_settings

    final_tag = f"CHAIN_{chain_id}_H{len(hop_nodes)}"
    if app_state.enable_final_fragment:
        fragment_tag = f"CHAIN_{chain_id}_FINAL_FRAGMENT"
        hop_outbounds.append({
            "protocol": "freedom",
            "tag": fragment_tag,
            "settings": {},
            "streamSettings": {
                "finalmask": {"tcp": [_build_xray_fragment_mask(app_state)]},
                "sockopt": {"dialerProxy": final_tag},
            },
        })
        final_tag = fragment_tag
    return hop_outbounds, final_tag


# ================================================================
# Node -> Xray outbound
# ================================================================

def _node_to_xray_outbound(node: Node, tag: str, app_state: AppState) -> dict:
    """把 Node 轉成 Xray outbound dict"""
    ob = {}
    if node.node_type == NODE_TYPE_VMESS:
        ob = _xray_vmess(node, tag)
    elif node.node_type == NODE_TYPE_VLESS:
        ob = _xray_vless(node, tag)
    elif node.node_type == NODE_TYPE_TROJAN:
        ob = _xray_trojan(node, tag)
    elif node.node_type == NODE_TYPE_SS:
        ob = _xray_ss(node, tag)
    elif node.node_type == NODE_TYPE_WG:
        ob = _xray_wg(node, tag)
    elif node.node_type == NODE_TYPE_SOCKS5:
        ob = _xray_socks(node, tag)
    elif node.node_type == NODE_TYPE_HTTP:
        ob = _xray_http(node, tag)
    else:
        ob = _xray_socks(node, tag)
        
    # 套用進階設定
    if app_state.enable_mux and ob.get("protocol") in ["vmess", "vless", "trojan", "shadowsocks"]:
        ob["mux"] = {
            "enabled": True,
            "concurrency": 8
        }
        
    return ob


def _xray_vmess(node: Node, tag: str) -> dict:
    """vmess outbound for Xray"""
    user_dict: dict[str, Any] = {
        "id": node.uuid_str or "",
        "alterId": node.alter_id,
        "security": node.security or "auto",
    }
    ob: dict[str, Any] = {
        "protocol": "vmess",
        "tag": tag,
        "settings": {
            "vnext": [{
                "address": node.server,
                "port": node.port,
                "users": [user_dict],
            }],
        },
    }
    _xray_add_stream(ob, node)
    return ob


def _xray_vless(node: Node, tag: str) -> dict:
    """vless outbound for Xray"""
    user_dict: dict[str, Any] = {
        "id": node.uuid_str or "",
        "encryption": "none",
    }
    if node.flow:
        user_dict["flow"] = node.flow
    ob: dict[str, Any] = {
        "protocol": "vless",
        "tag": tag,
        "settings": {
            "vnext": [{
                "address": node.server,
                "port": node.port,
                "users": [user_dict],
            }],
        },
    }
    _xray_add_stream(ob, node)
    return ob


def _xray_trojan(node: Node, tag: str) -> dict:
    """trojan outbound for Xray"""
    ob: dict[str, Any] = {
        "protocol": "trojan",
        "tag": tag,
        "settings": {
            "servers": [{
                "address": node.server,
                "port": node.port,
                "password": node.password or "",
            }],
        },
    }
    _xray_add_stream(ob, node)
    return ob


def _xray_ss(node: Node, tag: str) -> dict:
    """shadowsocks outbound for Xray"""
    ob: dict[str, Any] = {
        "protocol": "shadowsocks",
        "tag": tag,
        "settings": {
            "servers": [{
                "address": node.server,
                "port": node.port,
                "method": node.encryption or "aes-256-gcm",
                "password": node.password or "",
            }],
        },
    }
    return ob


def _xray_wg(node: Node, tag: str) -> dict:
    """wireguard outbound for Xray"""
    ob: dict[str, Any] = {
        "protocol": "wireguard",
        "tag": tag,
        "settings": {
            "secretKey": node.wg_private_key or "",
            "address": [node.wg_local_address] if node.wg_local_address else [],
            "peers": [{
                "publicKey": node.wg_public_key or "",
                "endpoint": f"{node.server}:{node.port}"
            }]
        },
    }
    return ob


def _xray_socks(node: Node, tag: str) -> dict:
    """socks outbound for Xray"""
    server_dict: dict[str, Any] = {
        "address": node.server,
        "port": node.port,
    }
    # 有帳密才加 users
    if node.username:
        server_dict["users"] = [{
            "user": node.username,
            "pass": node.password or "",
        }]
    ob: dict[str, Any] = {
        "protocol": "socks",
        "tag": tag,
        "settings": {"servers": [server_dict]},
        "streamSettings": {"network": "raw"},
    }
    return ob


def _xray_http(node: Node, tag: str) -> dict:
    """http outbound for Xray"""
    server_dict: dict[str, Any] = {
        "address": node.server,
        "port": node.port,
    }
    if node.username:
        server_dict["users"] = [{
            "user": node.username,
            "pass": node.password or "",
        }]
    ob: dict[str, Any] = {
        "protocol": "http",
        "tag": tag,
        "settings": {"servers": [server_dict]},
        "streamSettings": {"network": "raw"},
    }
    return ob


# ================================================================
# streamSettings（TLS + 傳輸層）
# ================================================================

def _xray_add_stream(ob: dict, node: Node) -> None:
    """加入 streamSettings（傳輸層 + TLS）"""
    stream: dict[str, Any] = {}
    network = node.network or "tcp"
    stream["network"] = network

    # TLS 設定
    if node.tls_enabled:
        security_type = node.extra.get("security", "tls")
        if security_type == "reality":
            stream["security"] = "reality"
            reality_settings: dict[str, Any] = {}
            if node.sni:
                reality_settings["serverName"] = node.sni
            query = node.extra.get("query", {})
            pbk_list = query.get("pbk", [])
            sid_list = query.get("sid", [])
            if pbk_list:
                reality_settings["publicKey"] = pbk_list[0]
            if sid_list:
                reality_settings["shortId"] = sid_list[0]
            stream["realitySettings"] = reality_settings
        else:
            stream["security"] = "tls"
            tls_settings: dict[str, Any] = {}
            if node.sni:
                tls_settings["serverName"] = node.sni
            if node.alpn:
                tls_settings["alpn"] = node.alpn
            if node.extra.get("skip_cert_verify"):
                tls_settings["allowInsecure"] = True
            stream["tlsSettings"] = tls_settings

    # 傳輸層設定
    if network == "ws":
        ws_settings: dict[str, Any] = {}
        if node.path:
            ws_settings["path"] = node.path
        if node.host:
            ws_settings["headers"] = {"Host": node.host}
        stream["wsSettings"] = ws_settings

    elif network == "grpc" or network == "gun":
        grpc_settings: dict[str, Any] = {}
        if node.path:
            grpc_settings["serviceName"] = node.path
        stream["grpcSettings"] = grpc_settings

    elif network in ("h2", "http"):
        http_settings: dict[str, Any] = {}
        if node.path:
            http_settings["path"] = node.path
        if node.host:
            http_settings["host"] = [node.host]
        stream["httpSettings"] = http_settings

    ob["streamSettings"] = stream


# ================================================================
# 路由規則
# ================================================================

def _build_xray_routing(
    port_mappings: list[PortMapping],
    chain_final_tag_map: dict[str, str],
    app_state: AppState,
) -> list[dict]:
    """每個 PortMapping → 一條路由規則"""
    rules: list[dict] = []
    
    if app_state.enable_tun and TUN_NODE_CHAIN_ID in chain_final_tag_map:
        final_tag = chain_final_tag_map.get(TUN_NODE_CHAIN_ID)
        if final_tag:
            rules.append({
                "type": "field",
                "inboundTag": ["IN_TUN"],
                "outboundTag": final_tag,
            })

    base_final_tag = chain_final_tag_map.get(BASE_NODE_CHAIN_ID)
    if base_final_tag:
        rules.append({
            "type": "field",
            "inboundTag": ["IN_BASE"],
            "outboundTag": base_final_tag,
        })
            
    for pm in port_mappings:
        final_tag = chain_final_tag_map.get(pm.chain_id)
        if final_tag is None:
            continue
        rules.append({
            "type": "field",
            "inboundTag": [f"IN_{pm.listen_port}"],
            "outboundTag": final_tag,
        })
    return rules


def _build_xray_fragment_mask(app_state: AppState) -> dict[str, Any]:
    """Build the same Xray finalmask fragment shape generated by v2rayN."""
    lengths = list(app_state.xray_fragment_lengths or ["50-100"])
    delays = list(app_state.xray_fragment_delays or ["10-20"])
    return {
        "type": "fragment",
        "settings": {
            "packets": app_state.xray_fragment_packets or "tlshello",
            "length": lengths[0],
            "delay": delays[0],
            "lengths": lengths,
            "delays": delays,
            "maxSplit": max(0, int(app_state.xray_fragment_max_split or 0)),
        },
    }


def _build_xray_dns_config(app_state: AppState) -> dict[str, Any]:
    """Mirror v2rayN's bootstrap + remote DoH DNS configuration."""
    remote_dns = (app_state.remote_dns_url or "").strip()
    parsed_dns = urlsplit(remote_dns)
    if parsed_dns.scheme.lower() != "https" or not parsed_dns.hostname:
        raise ValueError(
            "Remote DNS must be an HTTPS URL, for example "
            "https://cloudflare-dns.com/dns-query."
        )
    bootstrap_dns = (app_state.bootstrap_dns or "").strip()
    if not bootstrap_dns:
        raise ValueError("Bootstrap DNS address cannot be empty.")

    hosts = {
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
    }
    return {
        "hosts": hosts,
        "servers": [
            {
                "address": bootstrap_dns,
                "domains": [f"full:{parsed_dns.hostname}"],
                "skipFallback": True,
            },
            {
                "address": bootstrap_dns,
                "domains": ["geosite:private"],
                "skipFallback": True,
                "tag": "direct-dns-1",
            },
            remote_dns,
        ],
        "tag": "dns-module",
    }


def _select_xray_dns_outbound(
    app_state: AppState,
    port_mappings: list[PortMapping],
    chain_final_tag_map: dict[str, str],
) -> str:
    """Xray has one internal DNS module; prefer TUN, then Base, then a Chain."""
    if app_state.enable_tun and TUN_NODE_CHAIN_ID in chain_final_tag_map:
        return chain_final_tag_map[TUN_NODE_CHAIN_ID]
    base_outbound = chain_final_tag_map.get(BASE_NODE_CHAIN_ID)
    if base_outbound:
        return base_outbound
    for mapping in port_mappings:
        outbound_tag = chain_final_tag_map.get(mapping.chain_id)
        if outbound_tag:
            return outbound_tag
    return "DIRECT"
