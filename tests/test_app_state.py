from pathlib import Path

from models.app_state import AppState
from models.chain import Chain
from models.node import Node, NODE_TYPE_SOCKS5
from models.port_mapping import PortMapping


def test_app_state_round_trips_auto_start_core(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    state.run_on_startup = True
    state.minimize_on_start = True
    state.auto_start_core = True
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()

    assert loaded.run_on_startup is True
    assert loaded.minimize_on_start is True
    assert loaded.auto_start_core is True


def test_app_state_round_trips_v2rayn_xray_fragment_parameters(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    state.xray_fragment_packets = "tlshello"
    state.xray_fragment_lengths = ["50-100", "120-160"]
    state.xray_fragment_delays = ["10-20"]
    state.xray_fragment_max_split = 2
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()

    assert loaded.xray_fragment_packets == "tlshello"
    assert loaded.xray_fragment_lengths == ["50-100", "120-160"]
    assert loaded.xray_fragment_delays == ["10-20"]
    assert loaded.xray_fragment_max_split == 2


def test_app_state_round_trips_complete_chain_tun_binding(tmp_path: Path) -> None:
    from models.chain import Chain
    from models.node import Node, NODE_TYPE_SOCKS5

    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    first = Node("Entry", NODE_TYPE_SOCKS5, "entry.example.test", 1080)
    second = Node("Exit", NODE_TYPE_SOCKS5, "exit.example.test", 1081)
    chain = Chain("Two hop", [first.node_id, second.node_id])
    state.nodes = [first, second]
    state.chains = [chain]
    state.enable_tun = True
    state.tun_node_id = ""
    state.tun_chain_id = chain.chain_id
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()

    assert loaded.tun_node_id == ""
    assert loaded.tun_chain_id == chain.chain_id
    assert loaded.get_runtime_chain("__tun_node__").hop_node_ids == [first.node_id, second.node_id]


def test_legacy_chain_node_wrappers_migrate_to_chain_model(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    first = Node("Wireproxy", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    second = Node("Exit", NODE_TYPE_SOCKS5, "203.0.113.10", 1080)
    legacy_chain_node = Node(
        "Wireproxy + Exit",
        "chain",
        "",
        0,
        extra={"source_chain_id": "old-chain", "chain_hop_node_ids": [first.node_id, second.node_id]},
    )
    state.nodes = [first, second, legacy_chain_node]
    state.chains = [Chain("Outer", [legacy_chain_node.node_id], chain_id="outer-chain")]
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()

    assert all(node.node_type != "chain" for node in loaded.nodes)
    outer = loaded.find_chain_by_id("outer-chain")
    assert outer is not None
    assert [node.node_id for node in loaded.get_nodes_for_chain(outer)] == [
        first.node_id, second.node_id
    ]
    assert loaded.find_chain_by_id("old-chain") is not None
    assert loaded.port_mappings


def test_each_chain_gets_one_default_local_port(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    first = Node("Entry", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    state.nodes = [first]
    state.chains = [Chain("A", [first.node_id]), Chain("B", [first.node_id])]
    state.port_mappings = [
        PortMapping(21000, state.chains[0].chain_id),
        PortMapping(21001, state.chains[0].chain_id),
        PortMapping(21000, state.chains[1].chain_id),
    ]
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()
    assert {item.chain_id for item in loaded.port_mappings} == {
        chain.chain_id for chain in loaded.chains
    }
    assert len(loaded.port_mappings) == 2
    assert len({item.listen_port for item in loaded.port_mappings}) == 2
    assert all(item.listen_port != loaded.base_node_listen_port for item in loaded.port_mappings)


def test_legacy_chain_port_collision_with_shared_base_port_is_migrated(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    node = Node("Exit", NODE_TYPE_SOCKS5, "127.0.0.1", 1080)
    chain = Chain("Legacy", [node.node_id])
    state.nodes = [node]
    state.chains = [chain]
    state.port_mappings = [PortMapping(10808, chain.chain_id)]
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()
    assert len(loaded.port_mappings) == 1
    assert loaded.port_mappings[0].listen_port != loaded.base_node_listen_port
