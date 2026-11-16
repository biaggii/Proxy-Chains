from pathlib import Path

from models.app_state import AppState
from models.chain import Chain
from models.node import Node, NODE_TYPE_CHAIN, NODE_TYPE_SOCKS5


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


def test_chain_node_expands_to_original_hops(tmp_path: Path) -> None:
    state = AppState(str(tmp_path / "state.json"))
    first = Node("Wireproxy", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    second = Node("Exit", NODE_TYPE_SOCKS5, "203.0.113.10", 1080)
    reusable = Node(
        "Wireproxy + Exit",
        NODE_TYPE_CHAIN,
        "",
        0,
        extra={"chain_hop_node_ids": [first.node_id, second.node_id]},
    )
    state.nodes = [first, second, reusable]
    route = Chain("Published route", [reusable.node_id])

    assert state.get_nodes_for_chain(route) == [first, second]


def test_nested_chain_nodes_expand_recursively(tmp_path: Path) -> None:
    state = AppState(str(tmp_path / "state.json"))
    first = Node("Entry", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    second = Node("Exit", NODE_TYPE_SOCKS5, "203.0.113.10", 1080)
    inner = Node(
        "Inner",
        NODE_TYPE_CHAIN,
        "",
        0,
        extra={"chain_hop_node_ids": [first.node_id, second.node_id]},
    )
    outer = Node(
        "Outer",
        NODE_TYPE_CHAIN,
        "",
        0,
        extra={"chain_hop_node_ids": [inner.node_id]},
    )
    state.nodes = [first, second, inner, outer]

    assert state.get_nodes_for_chain(Chain("Nested route", [outer.node_id])) == [first, second]


def test_cyclic_chain_nodes_are_rejected(tmp_path: Path) -> None:
    state = AppState(str(tmp_path / "state.json"))
    first = Node("First", NODE_TYPE_CHAIN, "", 0, extra={"chain_hop_node_ids": []})
    second = Node("Second", NODE_TYPE_CHAIN, "", 0, extra={"chain_hop_node_ids": [first.node_id]})
    first.extra["chain_hop_node_ids"] = [second.node_id]
    state.nodes = [first, second]

    assert state.get_nodes_for_chain(Chain("Invalid", [first.node_id])) == []
