import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.dialogs.chain_editor_dialog import ChainEditorDialog
from app.ui_main_window import MainWindow
from app.ui_kit.theme import APP_STYLESHEET
from models.app_state import AppState
from models.chain import Chain
from models.node import Node, NODE_TYPE_SOCKS5


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_has_only_node_groups_and_settings(tmp_path) -> None:
    app = _app()
    window = MainWindow(AppState(str(tmp_path / "state.json")))

    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Node Groups", "Settings"
    ]
    assert not hasattr(window, "btn_apply")
    assert window.btn_start.text() == "Start"
    assert window.btn_stop.text() == "Stop"

    window._force_closing = True
    window.close()
    app.processEvents()


def test_chain_editor_orders_selected_base_nodes(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    first = Node("Entry", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    second = Node("Exit", NODE_TYPE_SOCKS5, "203.0.113.10", 1080)
    state.nodes = [first, second]

    dialog = ChainEditorDialog(state)
    dialog.name_input.setText("Two hop")
    dialog.available.item(0).setSelected(True)
    dialog.available.item(1).setSelected(True)
    dialog._add_selected()
    dialog.hops.setCurrentRow(1)
    dialog._move_up()

    name, hop_ids = dialog.result_values()
    assert name == "Two hop"
    assert hop_ids == [second.node_id, first.node_id]
    dialog.close()
    app.processEvents()


def test_tun_switch_uses_the_selected_chain(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    first = Node("Entry", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    second = Node("Exit", NODE_TYPE_SOCKS5, "203.0.113.10", 1080)
    state.nodes = [first, second]
    state.chains = [Chain("A", [first.node_id]), Chain("B", [second.node_id])]
    window = MainWindow(state)

    window.page_chains.table.selectRow(1)
    window.page_chains._on_tun_toggled(True)

    assert state.enable_tun is True
    assert state.tun_chain_id == state.chains[1].chain_id

    window._force_closing = True
    window.close()
    app.processEvents()


def test_saved_tun_chain_is_selected_when_workspace_opens(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    node = Node("Exit", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    chain = Chain("TUN route", [node.node_id])
    state.nodes = [node]
    state.chains = [chain]
    state.enable_tun = True
    state.tun_chain_id = chain.chain_id

    window = MainWindow(state)
    assert window.page_chains.table.currentRow() == 0
    assert window.page_chains.tun_switch.isChecked()

    window._force_closing = True
    window.close()
    app.processEvents()


def test_start_generates_validates_then_launches_core(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    node = Node("Exit", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    state.nodes = [node]
    state.chains = [Chain("Default", [node.node_id])]
    state.core_exe_paths["sing-box"] = str(tmp_path / "sing-box")
    (tmp_path / "sing-box").write_text("stub", encoding="utf-8")
    state.config_output_dir = str(tmp_path)
    window = MainWindow(state)

    events = []

    class FakeRunner:
        def is_running(self):
            return False

        def run_and_wait(self, command):
            events.append(("validate", command))
            return True, "valid"

        def start(self, command, on_log, on_exit):
            events.append(("start", command))
            return True

        def stop(self):
            return None

    class FakeAdapter:
        def generate_config(self, app_state):
            events.append(("generate", None))
            return "{}", str(tmp_path / "config.json")

        def get_check_command(self, config_path, exe_path):
            return [exe_path, "check", config_path]

        def get_start_command(self, config_path, exe_path):
            return [exe_path, "run", config_path]

    window.process_runner = FakeRunner()
    window._get_current_adapter = lambda **kwargs: FakeAdapter()

    assert window._start_core(interactive=True) is True
    assert [event[0] for event in events] == ["generate", "validate", "start"]

    window._force_closing = True
    window.close()
    app.processEvents()


def test_theme_forces_readable_settings_and_context_menu_colours() -> None:
    assert "QGroupBox" in APP_STYLESHEET
    assert "background-color: #ffffff" in APP_STYLESHEET
    assert "QMenu::item" in APP_STYLESHEET
    assert "QMenu::item:selected" in APP_STYLESHEET
    assert "color: #1f2b33" in APP_STYLESHEET
    assert "QCheckBox::indicator:checked" in APP_STYLESHEET
