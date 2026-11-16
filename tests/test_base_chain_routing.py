import json

import yaml

from core.mihomo_adapter import MihomoAdapter
from core.singbox_adapter import SingBoxAdapter
from core.xray_adapter import XrayAdapter
from models.app_state import AppState, BASE_NODE_CHAIN_ID, TUN_NODE_CHAIN_ID
from models.chain import Chain
from models.node import Node, NODE_TYPE_SOCKS5
from models.port_mapping import PortMapping


def _state(tmp_path, tun: bool = False) -> AppState:
    state = AppState(str(tmp_path / "state.json"))
    state.config_output_dir = str(tmp_path)
    base = Node("Base exit", NODE_TYPE_SOCKS5, "base.example.test", 1080)
    first = Node("Chain entry", NODE_TYPE_SOCKS5, "entry.example.test", 1081)
    second = Node("Chain exit", NODE_TYPE_SOCKS5, "exit.example.test", 1082)
    state.nodes = [base, first, second]
    state.active_base_node_id = base.node_id
    chain_a = Chain("Chain A", [first.node_id])
    chain_b = Chain("Chain B", [first.node_id, second.node_id])
    state.chains = [chain_a, chain_b]
    state.port_mappings = [
        PortMapping(20001, chain_a.chain_id),
        PortMapping(20002, chain_b.chain_id),
    ]
    state.enable_tun = tun
    state.tun_node_id = base.node_id if tun else ""
    return state


def test_singbox_has_one_base_port_plus_one_port_per_chain_and_single_node_tun(tmp_path):
    state = _state(tmp_path, tun=True)
    text, _ = SingBoxAdapter().generate_config(state)
    config = json.loads(text)

    inbound_tags = {item["tag"] for item in config["inbounds"]}
    assert {"IN_BASE", "IN_20001", "IN_20002", "IN_TUN"} <= inbound_tags
    assert sum(item.get("type") == "mixed" for item in config["inbounds"]) == 3

    base_tag = f"CHAIN_{BASE_NODE_CHAIN_ID}_H1"
    base_routes = [
        rule for rule in config["route"]["rules"]
        if rule.get("inbound") in (["IN_BASE"], ["IN_TUN"])
    ]
    assert {tuple(rule["inbound"]) for rule in base_routes} == {
        ("IN_BASE",), ("IN_TUN",)
    }
    tun_tag = f"CHAIN_{TUN_NODE_CHAIN_ID}_H1"
    assert next(rule for rule in base_routes if rule["inbound"] == ["IN_BASE"])["outbound"] == base_tag
    assert next(rule for rule in base_routes if rule["inbound"] == ["IN_TUN"])["outbound"] == tun_tag
    assert config["route"]["final"] == tun_tag


def test_tun_can_bind_one_chain_hop_different_from_active_base_node(tmp_path):
    state = _state(tmp_path, tun=True)
    state.tun_node_id = state.nodes[2].node_id
    text, _ = SingBoxAdapter().generate_config(state)
    config = json.loads(text)
    tun_rule = next(rule for rule in config["route"]["rules"] if rule.get("inbound") == ["IN_TUN"])
    assert tun_rule["outbound"] == f"CHAIN_{TUN_NODE_CHAIN_ID}_H1"
    assert tun_rule["outbound"] != f"CHAIN_{BASE_NODE_CHAIN_ID}_H1"
    assert state.get_tun_node().node_id == state.nodes[2].node_id


def test_xray_uses_modern_dialer_proxy_and_separate_base_tun(tmp_path):
    state = _state(tmp_path, tun=True)
    text, _ = XrayAdapter().generate_config(state)
    config = json.loads(text)

    inbounds = {item["tag"]: item for item in config["inbounds"]}
    assert inbounds["IN_BASE"]["port"] == 10808
    assert inbounds["IN_20001"]["port"] == 20001
    assert inbounds["IN_20002"]["port"] == 20002
    assert "IN_TUN" in inbounds

    second_hop = next(
        item for item in config["outbounds"]
        if item["tag"] == f"CHAIN_{state.chains[1].chain_id}_H2"
    )
    assert second_hop["streamSettings"]["sockopt"]["dialerProxy"] == (
        f"CHAIN_{state.chains[1].chain_id}_H1"
    )
    assert "proxySettings" not in second_hop

    tun_rule = next(
        rule for rule in config["routing"]["rules"]
        if rule.get("inboundTag") == ["IN_TUN"]
    )
    assert tun_rule["outboundTag"] == f"CHAIN_{TUN_NODE_CHAIN_ID}_H1"


def test_mihomo_uses_base_listener_and_chain_listeners_without_extra_mixed_port(tmp_path):
    state = _state(tmp_path, tun=True)
    text, _ = MihomoAdapter().generate_config(state)
    config = yaml.safe_load(text)

    listeners = {item["name"]: item for item in config["listeners"]}
    assert listeners["IN_BASE"]["port"] == 10808
    assert listeners["IN_20001"]["port"] == 20001
    assert listeners["IN_20002"]["port"] == 20002
    assert "mixed-port" not in config
    assert config["tun"]["enable"] is True
    assert config["rules"][-1] == f"MATCH,CHAIN_{TUN_NODE_CHAIN_ID}_H1"


def test_base_only_mode_has_one_shared_port_and_tun_adds_no_proxy_port(tmp_path):
    state = AppState(str(tmp_path / "base-only.json"))
    state.config_output_dir = str(tmp_path)
    node = Node("Single node", NODE_TYPE_SOCKS5, "single.example.test", 1080)
    state.nodes = [node]
    state.active_base_node_id = node.node_id
    state.tun_node_id = node.node_id

    for tun in (False, True):
        state.enable_tun = tun
        text, _ = SingBoxAdapter().generate_config(state)
        config = json.loads(text)
        mixed = [item for item in config["inbounds"] if item.get("type") == "mixed"]
        assert len(mixed) == 1
        assert mixed[0]["listen_port"] == 10808
        assert ("IN_TUN" in {item["tag"] for item in config["inbounds"]}) is tun
        assert not any(item["tag"].startswith("IN_200") for item in config["inbounds"])


def test_legacy_chain_tun_setting_migrates_to_one_base_node(tmp_path):
    state_path = tmp_path / "legacy.json"
    state = _state(tmp_path)
    state.state_file_path = str(state_path)
    state.enable_tun = True
    state.save_to_file()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["tun_chain_id"] = state.chains[1].chain_id
    data.pop("active_base_node_id", None)
    state_path.write_text(json.dumps(data), encoding="utf-8")

    loaded = AppState(str(state_path))
    loaded.load_from_file()

    assert loaded.enable_tun is True
    assert loaded.active_base_node_id == state.nodes[2].node_id
    assert loaded.get_active_base_node().name == "Chain exit"
    assert not hasattr(loaded, "tun_chain_id")
