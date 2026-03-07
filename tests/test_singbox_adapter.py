"""
test_singbox_adapter.py — 驗證 sing-box 配置生成的穩定性設定
"""

import json

from core.singbox_adapter import SingBoxAdapter
from models.app_state import AppState
from models.chain import Chain
from models.node import Node, NODE_TYPE_SOCKS5
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


def test_tun_mode_uses_mixed_stack_and_keeps_quic_available(tmp_path) -> None:
    """TUN 模式應使用 mixed stack，且不能再封鎖 QUIC。"""
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
    assert reject_quic_rules == []


def test_tun_inbound_respects_sniff_setting(tmp_path) -> None:
    """TUN inbound 應跟隨全域 sniff 設定。"""
    app_state = _build_app_state(tmp_path)
    app_state.enable_tun = True
    app_state.tun_chain_id = "chain1"
    app_state.enable_sniffing = False

    config = _generate_config(app_state)
    tun_inbound = next(inbound for inbound in config["inbounds"] if inbound["tag"] == "IN_TUN")

    assert tun_inbound["sniff"] is False
    assert "sniff_override_destination" not in tun_inbound


def test_tun_dns_uses_tcp_remote_server_and_direct_resolver(tmp_path) -> None:
    """TUN DNS 應改走可代理的 TCP 上游，並保留 direct resolver。"""
    app_state = _build_app_state(tmp_path)
    app_state.enable_tun = True
    app_state.tun_chain_id = "chain1"

    config = _generate_config(app_state)
    servers = {server["tag"]: server for server in config["dns"]["servers"]}

    assert servers["remote_dns"]["type"] == "tcp"
    assert servers["remote_dns"]["server"] == "8.8.8.8"
    assert servers["remote_dns"]["detour"] == "CHAIN_chain1_H1"
    assert servers["direct_dns"]["type"] == "local"
    assert config["route"]["default_domain_resolver"]["server"] == "direct_dns"


def test_non_tun_dns_does_not_set_invalid_direct_detour(tmp_path) -> None:
    """非 TUN 模式下，DNS server 不應帶入無效的 DIRECT detour。"""
    app_state = _build_app_state(tmp_path)

    config = _generate_config(app_state)
    servers = {server["tag"]: server for server in config["dns"]["servers"]}

    assert "detour" not in servers["remote_dns"]


def test_tun_route_adds_sniff_action_when_enabled(tmp_path) -> None:
    """TUN 模式在開啟 sniffing 時應加入 sing-box sniff action。"""
    app_state = _build_app_state(tmp_path)
    app_state.enable_tun = True
    app_state.tun_chain_id = "chain1"

    config = _generate_config(app_state)
    assert any(rule.get("action") == "sniff" for rule in config["route"]["rules"])


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
