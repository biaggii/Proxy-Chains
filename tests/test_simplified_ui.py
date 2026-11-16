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
    assert window.btn_run.text() == "Start"
    assert window.btn_run.minimumWidth() >= 112
    assert window.tabs.cornerWidget() is not None
    assert not window.tabs.cornerWidget().isHidden()
    window.show()
    app.processEvents()
    assert window.tabs.cornerWidget().isVisible()
    assert [window.page_node_groups.sections.tabText(i) for i in range(window.page_node_groups.sections.count())] == [
        "Base", "Chain"
    ]
    assert not hasattr(window.page_chains, "btn_add")
    assert window.page_chains.btn_create.text() == "Create"
    assert not hasattr(window.page_chains, "btn_edit")
    assert not hasattr(window.page_chains, "btn_remove")
    chain_summary_row = window.page_chains.layout().itemAt(1).layout()
    assert chain_summary_row.indexOf(window.page_chains.btn_create) >= 0
    assert chain_summary_row.indexOf(window.page_chains.summary) >= 0
    margins = window.page_node_groups.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (18, 14, 18, 18)

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


def test_tun_switch_uses_the_single_bound_node_not_current_base_selection(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    first = Node("Entry", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    second = Node("Exit", NODE_TYPE_SOCKS5, "203.0.113.10", 1080)
    state.nodes = [first, second]
    state.active_base_node_id = first.node_id
    state.tun_node_id = first.node_id
    window = MainWindow(state)

    window.page_base_nodes.table.selectRow(1)
    window._on_tun_toggled(True)

    assert state.enable_tun is True
    assert state.active_base_node_id == second.node_id
    assert state.tun_node_id == first.node_id

    window._force_closing = True
    window.close()
    app.processEvents()


def test_saved_tun_base_node_is_selected_when_workspace_opens(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    node = Node("Exit", NODE_TYPE_SOCKS5, "127.0.0.1", 25344)
    state.nodes = [node]
    state.active_base_node_id = node.node_id
    state.tun_node_id = node.node_id
    state.enable_tun = True

    window = MainWindow(state)
    assert window.page_base_nodes.table.currentRow() == 0
    assert window.tun_switch.isChecked()

    window._force_closing = True
    window.close()
    app.processEvents()


def test_base_tab_uses_one_shared_port_while_each_chain_has_its_own(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    base_a = Node("Base A", NODE_TYPE_SOCKS5, "base-a.example.test", 1080)
    base_b = Node("Base B", NODE_TYPE_SOCKS5, "base-b.example.test", 1080)
    chain_a = Chain("Chain A", [base_a.node_id])
    chain_b = Chain("Chain B", [base_b.node_id])
    state.nodes = [base_a, base_b]
    state.chains = [chain_a, chain_b]
    state.active_base_node_id = base_a.node_id
    window = MainWindow(state)

    assert window.page_base_nodes.table.rowCount() == 2
    assert window.shared_port.value() == 10808
    assert window.page_base_nodes.endpoint_label.text().startswith("Active Base Node:")
    assert [mapping.listen_port for mapping in state.port_mappings] == [20001, 20002]

    window.page_base_nodes.table.selectRow(1)
    assert state.active_base_node_id == base_b.node_id
    assert window.shared_port.value() == 10808

    window._force_closing = True
    window.close()
    app.processEvents()


def test_tun_switch_is_shared_above_base_and_chain_subtabs(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    node = Node("Base", NODE_TYPE_SOCKS5, "base.example.test", 1080)
    state.nodes = [node]
    state.active_base_node_id = node.node_id
    state.tun_node_id = node.node_id
    window = MainWindow(state)

    assert window.tun_switch.text() == "TUN OFF"
    assert window.page_base_nodes is window.page_node_groups.base_page
    assert window.page_chains is window.page_node_groups.chain_page
    window._on_tun_toggled(True)
    assert state.enable_tun is True
    window.page_node_groups.sections.setCurrentWidget(window.page_chains)
    window.page_node_groups.refresh()
    assert window.tun_switch.isChecked()
    assert state.active_base_node_id == node.node_id

    window._force_closing = True
    window.close()
    app.processEvents()


def test_base_subscription_tabs_and_editable_shared_port(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    manual = Node("Manual node", NODE_TYPE_SOCKS5, "manual.example.test", 1080)
    manual.source_sub = "Manual"
    provider_a = Node("Provider A node", NODE_TYPE_SOCKS5, "a.example.test", 1080)
    provider_a.source_sub = "Provider A"
    provider_b = Node("Provider B node", NODE_TYPE_SOCKS5, "b.example.test", 1080)
    provider_b.source_sub = "Provider B"
    state.nodes = [manual, provider_a, provider_b]
    state.active_base_node_id = manual.node_id
    window = MainWindow(state)
    base = window.page_base_nodes

    labels = [base.group_tabs.tabText(i) for i in range(base.group_tabs.count())]
    assert labels == ["ALL", "Customs", "Provider A", "Provider B"]
    base.group_tabs.setCurrentIndex(2)
    assert [node.node_id for node in base._visible_nodes] == [provider_a.node_id]

    window.shared_port.setValue(10999)
    window._save_shared_port()
    assert state.base_node_listen_port == 10999
    assert window.shared_port.value() == 10999

    window._force_closing = True
    window.close()
    app.processEvents()


def test_manual_and_import_sources_have_v2rayn_style_group_tabs(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    nodes = []
    for name, source in (
        ("Custom node", "Manual"),
        ("Manual add", "Manual Add"),
        ("Clipboard", "從剪貼簿貼上"),
        ("Manual create", "手動新增"),
        ("Subscription", "Provider X"),
    ):
        node = Node(name, NODE_TYPE_SOCKS5, f"{name}.example.test", 1080)
        node.source_sub = source
        nodes.append(node)
    state.nodes = nodes
    state.active_base_node_id = nodes[0].node_id
    window = MainWindow(state)
    base = window.page_base_nodes

    labels = [base.group_tabs.tabText(i) for i in range(base.group_tabs.count())]
    assert labels == [
        "ALL", "Customs", "Manual Add", "Provider X",
        "從剪貼簿貼上", "手動新增",
    ]
    base.group_tabs.setCurrentIndex(1)
    assert {node.source_sub for node in base._visible_nodes} == {"Manual"}
    assert base.btn_subscriptions.text() == "Subscriptions…"
    assert not hasattr(base, "btn_add")

    window._force_closing = True
    window.close()
    app.processEvents()


def test_binding_tun_replaces_previous_node_and_displays_target(tmp_path) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    first = Node("Base", NODE_TYPE_SOCKS5, "base.example.test", 1080)
    hop = Node("Chain Hop", NODE_TYPE_SOCKS5, "hop.example.test", 1080)
    state.nodes = [first, hop]
    state.active_base_node_id = first.node_id
    state.chains = [Chain("Route", [hop.node_id])]
    window = MainWindow(state)

    window.page_node_groups.bind_tun_node(first.node_id)
    assert state.enable_tun is True
    assert state.tun_node_id == first.node_id
    window.page_node_groups.bind_tun_node(hop.node_id)
    assert state.tun_node_id == hop.node_id
    assert window.lbl_tun_binding.text() == "TUN: Chain Hop"
    assert window.page_chains.table.item(0, 4).text() == "Chain Hop"
    assert window.page_base_nodes.table.item(0, 9).text() == ""
    window.page_chains.bind_tun_requested.emit(first.node_id)
    assert state.tun_node_id == first.node_id

    window._force_closing = True
    window.close()
    app.processEvents()


def test_node_table_context_menus_do_not_duplicate_edit_remove_buttons(tmp_path) -> None:
    from models.subscription import Subscription

    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    base = Node("Base", NODE_TYPE_SOCKS5, "base.example.test", 1080)
    hop = Node("Hop", NODE_TYPE_SOCKS5, "hop.example.test", 1080)
    state.nodes = [base, hop]
    state.active_base_node_id = base.node_id
    state.chains = [Chain("Route", [hop.node_id])]
    state.subscriptions = [Subscription("Provider", "https://example.test/sub")]
    window = MainWindow(state)

    base_menu = window.page_base_nodes._build_context_menu()
    base_actions = [action.text() for action in base_menu.actions()]
    assert "Edit" in base_actions
    assert "Remove" in base_actions
    assert "Bind TUN to this node" in base_actions

    window.page_chains.table.selectRow(0)
    chain_menu = window.page_chains._build_context_menu()
    chain_actions = [action.text() for action in chain_menu.actions()]
    assert "Create" not in chain_actions
    assert "Edit" in chain_actions
    assert "Remove" in chain_actions
    bind_menu = next(action.menu() for action in chain_menu.actions() if action.menu())
    assert [action.text() for action in bind_menu.actions()] == ["Hop"]

    window._force_closing = True
    window.close()
    app.processEvents()


def test_subscription_group_rename_and_remove_controls(tmp_path, monkeypatch) -> None:
    from models.subscription import Subscription
    from PySide6.QtWidgets import QMessageBox

    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    node = Node("Provider node", NODE_TYPE_SOCKS5, "provider.example.test", 1080)
    node.source_sub = "Provider A"
    state.nodes = [node]
    state.subscriptions = [Subscription("Provider A", "https://example.test/sub")]
    state.active_base_node_id = node.node_id
    window = MainWindow(state)
    base = window.page_base_nodes
    base.group_tabs.setCurrentIndex(1)

    monkeypatch.setattr(
        "app.ui_pages_base_nodes.QInputDialog.getText",
        lambda *args, **kwargs: ("Provider Renamed", True),
    )
    base._rename_group()
    assert node.source_sub == "Provider Renamed"
    assert state.subscriptions[0].name == "Provider Renamed"

    monkeypatch.setattr(
        "app.ui_pages_base_nodes.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    base.group_tabs.setCurrentIndex(1)
    base._remove_group()
    assert node not in state.nodes
    assert state.subscriptions == []

    window._force_closing = True
    window.close()
    app.processEvents()


def test_shared_port_editor_rejects_a_chain_port_collision(tmp_path, monkeypatch) -> None:
    app = _app()
    state = AppState(str(tmp_path / "state.json"))
    node = Node("Base", NODE_TYPE_SOCKS5, "base.example.test", 1080)
    state.nodes = [node]
    state.active_base_node_id = node.node_id
    state.chains = [Chain("Chain A", [node.node_id])]
    window = MainWindow(state)
    base = window.page_base_nodes
    chain_port = state.port_mappings[0].listen_port
    warnings = []
    monkeypatch.setattr(
        "app.ui_pages_base_nodes.QMessageBox.warning",
        lambda *args: warnings.append(args[2]),
    )

    window.shared_port.setValue(chain_port)
    window._save_shared_port()

    assert state.base_node_listen_port == 10808
    assert window.shared_port.value() == 10808
    assert warnings and "already assigned" in warnings[0]

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
        running = False

        def is_running(self):
            return self.running

        def run_and_wait(self, command):
            events.append(("validate", command))
            return True, "valid"

        def start(self, command, on_log, on_exit):
            events.append(("start", command))
            self.running = True
            return True

        def stop(self):
            self.running = False
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
    assert window.btn_run.text() == "Stop"
    window._on_run_clicked()
    assert window.btn_run.text() == "Start"

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
