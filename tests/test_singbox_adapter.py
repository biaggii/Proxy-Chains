"""
test_singbox_adapter.py — 驗證 sing-box 配置生成的穩定性設定
"""

import json

from core.singbox_adapter import SingBoxAdapter
from models.app_state import AppState
from models.chain import Chain
from models.node import Node, NODE_TYPE_CHAIN, NODE_TYPE_SOCKS5, NODE_TYPE_VLESS, NODE_TYPE_WG
from models.port_mapping import PortMapping


def _build_app_state(tmp_path) -> AppState:
    """建立一份最小可生成配置的 AppState。"""
    app_state = AppState(state_file_path=str(tmp_path / "state.json"))
    app_state.config_output_dir = str(tmp_path)

    node = Node(
        name="測試 Socks5",
        node_type=NODE_TYPE_SOCKS5,
        server="127.0.0.1",
        port=1080,
        username="demo",
        password="secret",
    )
    chain = Chain(name="單跳測試", hop_node_ids=[node.node_id], chain_id="chain1")
    mapping = PortMapping(listen_port=20001, chain_id=chain.chain_id)

    app_state.nodes.append(node)
    app_state.chains.append(chain)
    app_state.port_mappings.append(mapping)
    return app_state


def _generate_config(app_state: AppState) -> dict:
    """產生並解析 sing-box 設定。"""
    config_text, _ = SingBoxAdapter().generate_config(app_state)
    return json.loads(config_text)


def test_tun_mode_uses_mixed_stack_and_matches_v2rayn_quic_policy(tmp_path) -> None:
    """TUN mode uses mixed stack and blocks UDP/443 like the reference config."""
    app_state = _build_app_state(tmp_path)
    app_state.enable_tun = True
    app_state.tun_chain_id = "chain1"

    config = _generate_config(app_state)

    tun_inbound = next(inbound for inbound in config["inbounds"] if inbound["tag"] == "IN_TUN")
    assert tun_inbound["stack"] == "mixed"

    reject_quic_rules = [
        rule for rule in config["route"]["rules"]
        if rule.get("action") == "reject"
        and rule.get("network") == ["udp"]
        and rule.get("port") == [443]
    ]
    assert len(reject_quic_rules) == 1


def test_route_respects_sniff_setting(tmp_path) -> None:
    """全域配置應跟隨 sniff 設定，在 route 中加入/移除 sniff action。"""
    app_state = _build_app_state(tmp_path)
    app_state.enable_sniffing = False

    config = _generate_config(app_state)
    assert not any(rule.get("action") == "sniff" for rule in config["route"]["rules"])

    app_state.enable_sniffing = True
    config = _generate_config(app_state)
    assert any(rule.get("action") == "sniff" for rule in config["route"]["rules"])


def test_tun_dns_uses_doh_through_tun_chain_and_direct_bootstrap(tmp_path) -> None:
    """TUN DNS uses DoH through its selected chain and direct bootstrap DNS."""
    app_state = _build_app_state(tmp_path)
    app_state.enable_tun = True
    app_state.tun_chain_id = "chain1"

    config = _generate_config(app_state)
    servers = {server["tag"]: server for server in config["dns"]["servers"]}

    assert servers["remote_dns_chain1"]["type"] == "https"
    assert servers["remote_dns_chain1"]["server"] == "cloudflare-dns.com"
    assert servers["remote_dns_chain1"]["path"] == "/dns-query"
    assert servers["remote_dns_chain1"]["detour"] == "CHAIN_chain1_H1"
    assert servers["direct_dns"]["type"] == "udp"
    assert servers["direct_dns"]["server"] == "119.29.29.29"
    assert any(
        rule.get("inbound") == ["IN_TUN"]
        and rule.get("server") == "remote_dns_chain1"
        for rule in config["dns"]["rules"]
    )
    assert config["route"]["default_domain_resolver"]["server"] == "direct_dns"


def test_tun_routes_loopback_directly(tmp_path) -> None:
    """TUN 模式下，127.0.0.0/8 應直接放行，避免本機上游代理被誤導流。"""
    app_state = _build_app_state(tmp_path)
    app_state.enable_tun = True
    app_state.tun_chain_id = "chain1"

    config = _generate_config(app_state)

    loopback_rules = [
        rule for rule in config["route"]["rules"]
        if rule.get("ip_cidr") == ["127.0.0.0/8"]
        and rule.get("outbound") == "DIRECT"
    ]
    assert loopback_rules, "Expected an explicit loopback direct route rule"


def test_non_tun_dns_uses_the_mapped_chain_detour(tmp_path) -> None:
    """Non-TUN DNS must still use the outbound chain selected by its inbound."""
    app_state = _build_app_state(tmp_path)

    config = _generate_config(app_state)
    servers = {server["tag"]: server for server in config["dns"]["servers"]}

    assert servers["remote_dns_chain1"]["detour"] == "CHAIN_chain1_H1"
    assert any(
        rule.get("inbound") == ["IN_20001"]
        and rule.get("server") == "remote_dns_chain1"
        for rule in config["dns"]["rules"]
    )


def test_chain_node_is_flattened_before_core_outbound_generation(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    first = app_state.nodes[0]
    second = Node(
        name="Exit SOCKS5",
        node_type=NODE_TYPE_SOCKS5,
        server="203.0.113.20",
        port=1080,
    )
    reusable = Node(
        name="Reusable two-hop chain",
        node_type=NODE_TYPE_CHAIN,
        server="",
        port=0,
        extra={"chain_hop_node_ids": [first.node_id, second.node_id]},
    )
    app_state.nodes.extend([second, reusable])
    app_state.chains[0].hop_node_ids = [reusable.node_id]

    config = _generate_config(app_state)
    chain_outbounds = [
        item for item in config["outbounds"]
        if item.get("tag", "").startswith("CHAIN_chain1_H")
    ]

    assert [item["server"] for item in chain_outbounds] == [
        "127.0.0.1", "203.0.113.20"
    ]
    assert chain_outbounds[1]["detour"] == "CHAIN_chain1_H1"



def test_outbounds_keep_connect_timeout_without_aggressive_tcp_flags(tmp_path) -> None:
    """outbound 應保留 connect_timeout，且不強制開啟高風險 TCP 特性。"""
    app_state = _build_app_state(tmp_path)

    config = _generate_config(app_state)
    outbound = next(item for item in config["outbounds"] if item["type"] == "socks")

    assert outbound["connect_timeout"] == "10s"
    assert "tcp_fast_open" not in outbound
    assert "tcp_multi_path" not in outbound


def test_fragment_feature_disabled_by_default(tmp_path) -> None:
    """新建立的 AppState 預設不應帶入 experimental 區段。"""
    app_state = _build_app_state(tmp_path)

    assert app_state.enable_fragment is False

    config = _generate_config(app_state)
    assert "experimental" not in config


def test_wireproxy_chain_limits_every_hop_to_tcp(tmp_path) -> None:
    """A loopback Wireproxy SOCKS upstream only supports TCP CONNECT."""
    app_state = _build_app_state(tmp_path)
    remote_node = Node(
        name="Remote SOCKS5",
        node_type=NODE_TYPE_SOCKS5,
        server="203.0.113.10",
        port=1080,
        username="demo",
        password="secret",
    )
    app_state.nodes.append(remote_node)
    app_state.chains[0].hop_node_ids = [app_state.nodes[0].node_id, remote_node.node_id]

    config = _generate_config(app_state)
    chain_outbounds = [item for item in config["outbounds"] if item["tag"].startswith("CHAIN_chain1_")]

    assert [item.get("network") for item in chain_outbounds] == ["tcp", "tcp"]


def test_wireproxy_chain_rejects_wireguard_as_second_hop(tmp_path) -> None:
    """WireGuard's UDP transport cannot pass through Wireproxy SOCKS CONNECT."""
    app_state = _build_app_state(tmp_path)
    wireguard_node = Node(
        name="Remote WireGuard",
        node_type=NODE_TYPE_WG,
        server="203.0.113.20",
        port=51820,
        wg_private_key="private",
        wg_public_key="public",
        wg_local_address="10.0.0.2/32",
    )
    app_state.nodes.append(wireguard_node)
    app_state.chains[0].hop_node_ids = [app_state.nodes[0].node_id, wireguard_node.node_id]

    try:
        _generate_config(app_state)
    except ValueError as err:
        assert "WireGuard cannot be used after a TCP-only local SOCKS5 upstream" in str(err)
    else:
        raise AssertionError("Expected an actionable WireGuard/Wireproxy compatibility error")


def test_disabling_udp_limits_proxy_outbounds_to_tcp(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    app_state.enable_udp = False

    config = _generate_config(app_state)
    outbound = next(item for item in config["outbounds"] if item["type"] == "socks")

    assert outbound["network"] == "tcp"


def test_remote_socks_chain_keeps_udp_when_enabled(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    app_state.nodes[0].server = "203.0.113.30"

    config = _generate_config(app_state)
    outbound = next(item for item in config["outbounds"] if item["type"] == "socks")

    assert "network" not in outbound


def test_vless_tls_fragment_matches_v2rayn_7256(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    node = Node(
        name="VLESS TLS",
        node_type=NODE_TYPE_VLESS,
        server="vless.example.test",
        port=443,
        uuid_str="00000000-0000-0000-0000-000000000001",
        tls_enabled=True,
        sni="vless.example.test",
        extra={"security": "tls", "query": {}},
    )
    app_state.nodes[0] = node
    app_state.chains[0].hop_node_ids = [node.node_id]
    app_state.enable_fragment = True

    config = _generate_config(app_state)
    outbound = next(item for item in config["outbounds"] if item.get("tag") == "CHAIN_chain1_H1")

    assert outbound["tls"]["fragment"] is True
    assert outbound["tls"]["record_fragment"] is True
    assert outbound["packet_encoding"] == "xudp"


def test_vless_reality_preserves_fingerprint_public_key_and_short_id(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    node = Node(
        name="VLESS REALITY",
        node_type=NODE_TYPE_VLESS,
        server="reality.example.test",
        port=443,
        uuid_str="00000000-0000-0000-0000-000000000001",
        tls_enabled=True,
        sni="reality.example.test",
        extra={
            "security": "reality",
            "query": {
                "fp": ["chrome"],
                "pbk": ["public-key"],
                "sid": ["0123456789abcdef"],
            },
        },
    )
    app_state.nodes[0] = node
    app_state.chains[0].hop_node_ids = [node.node_id]

    config = _generate_config(app_state)
    outbound = next(item for item in config["outbounds"] if item.get("tag") == "CHAIN_chain1_H1")

    assert outbound["tls"]["utls"] == {"enabled": True, "fingerprint": "chrome"}
    assert outbound["tls"]["reality"] == {
        "enabled": True,
        "public_key": "public-key",
        "short_id": "0123456789abcdef",
    }


def test_non_tun_dns_uses_doh_through_each_inbound_chain(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    remote_node = Node(
        name="Second SOCKS5",
        node_type=NODE_TYPE_SOCKS5,
        server="203.0.113.11",
        port=1081,
        username="demo",
        password="secret",
    )
    app_state.nodes.append(remote_node)
    app_state.chains[0].hop_node_ids.append(remote_node.node_id)

    second_chain = Chain(name="Other route", hop_node_ids=[remote_node.node_id], chain_id="chain2")
    second_mapping = PortMapping(listen_port=20002, chain_id=second_chain.chain_id)
    app_state.chains.append(second_chain)
    app_state.port_mappings.append(second_mapping)

    config = _generate_config(app_state)
    servers = {item["tag"]: item for item in config["dns"]["servers"]}
    rules = config["dns"]["rules"]

    assert servers["direct_dns"]["type"] == "udp"
    assert servers["direct_dns"]["server"] == "119.29.29.29"
    assert servers["remote_dns_chain1"]["type"] == "https"
    assert servers["remote_dns_chain1"]["server"] == "cloudflare-dns.com"
    assert servers["remote_dns_chain1"]["path"] == "/dns-query"
    assert servers["remote_dns_chain1"]["detour"] == "CHAIN_chain1_H2"
    assert servers["remote_dns_chain1"]["domain_resolver"] == "hosts_dns"
    assert servers["hosts_dns"]["type"] == "hosts"
    assert servers["hosts_dns"]["predefined"]["cloudflare-dns.com"] == [
        "104.16.249.249", "104.16.248.249",
        "2606:4700::6810:f8f9", "2606:4700::6810:f9f9",
    ]
    assert servers["direct_dns"]["domain_resolver"] == "local_dns"
    assert servers["remote_dns_chain2"]["detour"] == "CHAIN_chain2_H1"
    assert {tuple(rule["inbound"]): rule["server"] for rule in rules if "inbound" in rule} == {
        ("IN_20001",): "remote_dns_chain1",
        ("IN_20002",): "remote_dns_chain2",
    }
    assert config["dns"]["final"] == "remote_dns_chain1"
    assert config["dns"]["rules"][0] == {
        "server": "hosts_dns", "preferred_by": "hosts_dns"
    }


def test_non_tun_routes_hijack_dns_fragment_tls_and_reject_quic(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    app_state.enable_fragment = True
    app_state.enable_final_fragment = True

    config = _generate_config(app_state)
    rules = config["route"]["rules"]

    assert any(
        rule.get("action") == "hijack-dns"
        and rule.get("type") == "logical"
        and {tuple(child.get("port", [])) for child in rule.get("rules", [])} == {(53,), ()}
        for rule in rules
    )
    assert any(
        rule.get("action") == "route-options"
        and rule.get("protocol") == ["tls"]
        and rule.get("tls_record_fragment") is True
        for rule in rules
    )
    assert any(
        rule.get("action") == "reject"
        and rule.get("network") == ["udp"]
        and rule.get("port") == [443]
        for rule in rules
    )

def test_wireguard_single_hop_uses_singbox_endpoint(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    wireguard_node = Node(
        name="WireGuard",
        node_type=NODE_TYPE_WG,
        server="203.0.113.40",
        port=51820,
        wg_private_key="private",
        wg_public_key="public",
        wg_local_address="10.0.0.2/32",
    )
    app_state.nodes[0] = wireguard_node
    app_state.chains[0].hop_node_ids = [wireguard_node.node_id]

    config = _generate_config(app_state)

    assert config["endpoints"][0]["type"] == "wireguard"
    assert config["endpoints"][0]["tag"] == "CHAIN_chain1_H1"
    assert config["endpoints"][0]["peers"][0]["allowed_ips"] == ["0.0.0.0/0", "::/0"]
    assert not any(item.get("type") == "wireguard" for item in config["outbounds"])


def test_wireguard_requires_udp_forwarding(tmp_path) -> None:
    app_state = _build_app_state(tmp_path)
    wireguard_node = Node(
        name="WireGuard",
        node_type=NODE_TYPE_WG,
        server="203.0.113.40",
        port=51820,
        wg_private_key="private",
        wg_public_key="public",
        wg_local_address="10.0.0.2/32",
    )
    app_state.nodes[0] = wireguard_node
    app_state.chains[0].hop_node_ids = [wireguard_node.node_id]
    app_state.enable_udp = False

    try:
        _generate_config(app_state)
    except ValueError as err:
        assert "WireGuard requires UDP forwarding to be enabled" in str(err)
    else:
        raise AssertionError("Expected a WireGuard/UDP compatibility error")
