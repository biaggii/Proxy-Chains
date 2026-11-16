import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui_main_window import MainWindow
from models.app_state import AppState
from models.node import Node


def test_launch_actions_preserve_selected_tun_route(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])

    state = AppState(str(tmp_path / "state.json"))
    state.auto_start_core = True
    state.enable_tun = True
    node = Node("Selected", "socks5", "127.0.0.1", 1080)
    state.nodes = [node]
    state.active_base_node_id = node.node_id

    window = MainWindow(state)
    calls: list[bool] = []

    def fake_start_core(*, interactive: bool) -> bool:
        calls.append(interactive)
        return True

    window._start_core = fake_start_core  # type: ignore[method-assign]
    window._run_launch_actions()

    assert state.enable_tun is True
    assert state.active_base_node_id == node.node_id
    assert calls == [False]

    window.close()
    app.quit()
