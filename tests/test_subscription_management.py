import json

from PySide6.QtWidgets import QApplication, QDialog

from app.dialogs.subscription_edit_dialog import SubscriptionEditDialog
from app.dialogs.subscription_manager_dialog import SubscriptionManagerDialog
from app.ui_pages_base_nodes import BaseNodesPage
from models.app_state import AppState
from models.chain import Chain
from models.node import Node, NODE_TYPE_SOCKS5
from models.subscription import Subscription
from parsers import subscription_fetcher


def _app():
    return QApplication.instance() or QApplication([])


def test_subscription_model_round_trips_v2rayn_group_settings():
    sub = Subscription(
        "Provider", "https://example.test/sub", sub_type="v2rayn",
        enable_update=False, update_interval=45, remarks_filter="HK|JP",
        convert_target_type="sing-box", user_agent="ChainPortTest/1.0",
        http_headers={"X-Test": "value"}, sort=7,
        previous_proxy_remarks="Entry", next_proxy_remarks="Exit",
        custom_config_core="xray", custom_config_socks_port=23456,
        remarks_memo="test memo",
    )
    restored = Subscription.from_dict(sub.to_dict())
    assert restored.to_dict() == sub.to_dict()


def test_fetcher_uses_subscription_user_agent_headers_and_remarks_filter(monkeypatch):
    captured = {}
    raw = "vless://id@example.test:443?security=tls#HK-01\nvless://id2@example.test:443?security=tls#US-01"

    class Response:
        text = raw
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_get(url, timeout, headers):
        captured.update(url=url, timeout=timeout, headers=headers)
        return Response()

    monkeypatch.setattr(subscription_fetcher.requests, "get", fake_get)
    sub = Subscription(
        "Provider", "https://example.test/sub", sub_type="v2rayn",
        user_agent="CustomAgent/1.0", http_headers={"X-Token": "abc"},
        remarks_filter="HK",
    )
    nodes, errors = subscription_fetcher.fetch_and_parse(sub)

    assert not errors
    assert [node.name for node in nodes] == ["HK-01"]
    assert captured["headers"] == {"User-Agent": "CustomAgent/1.0", "X-Token": "abc"}
    assert sub.node_count == 1
    assert sub.last_update


def test_invalid_remarks_filter_does_not_report_success(monkeypatch):
    class Response:
        text = "vless://id@example.test:443?security=tls#HK-01"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(subscription_fetcher.requests, "get", lambda *args, **kwargs: Response())
    sub = Subscription("Provider", "https://example.test/sub", sub_type="v2rayn", remarks_filter="[")
    nodes, errors = subscription_fetcher.fetch_and_parse(sub)
    assert nodes == []
    assert any("regular expression" in error for error in errors)


def test_subscription_edit_dialog_contains_v2rayn_group_options():
    _app()
    dialog = SubscriptionEditDialog()
    assert dialog.remarks is not None
    assert dialog.url is not None
    assert dialog.enable_update.isChecked()
    assert dialog.update_interval.value() == 0
    assert dialog.remarks_filter is not None
    assert dialog.convert_target_type.count() >= 3
    assert dialog.user_agent is not None
    assert dialog.http_headers is not None
    assert dialog.sort is not None
    assert dialog.previous_remarks is not None
    assert dialog.next_remarks is not None
    assert dialog.custom_core is not None
    assert dialog.custom_socks_port is not None
    assert dialog.remarks_memo is not None
    dialog.remarks.setText("Local group")
    dialog.url.setPlainText("")
    dialog.http_headers.setPlainText('{"X-Test": "yes"}')
    dialog.update_interval.setValue(30)
    dialog.remarks_filter.setText("HK|JP")
    assert dialog._validate_and_accept() is None
    assert dialog.result() == QDialog.DialogCode.Accepted
    saved = dialog.build_subscription()
    assert saved.url == ""
    assert saved.http_headers == {"X-Test": "yes"}
    assert saved.update_interval == 30
    assert saved.remarks_filter == "HK|JP"
    dialog.close()


def test_subscription_manager_has_v2rayn_actions_and_group_columns():
    _app()
    state = AppState("/tmp/chainport-sub-manager-test.json")
    state.subscriptions = [Subscription("Provider", "https://example.test/sub")]
    dialog = SubscriptionManagerDialog(state)
    assert [dialog.table.horizontalHeaderItem(i).text() for i in range(7)] == [
        "Remarks", "URL", "Enable update", "Automatic update (min)", "User Agent", "Sort", "Nodes",
    ]
    assert [dialog.btn_add.text(), dialog.btn_delete.text(), dialog.btn_edit.text(), dialog.btn_share.text(), dialog.btn_close.text()] == [
        "Add", "Delete", "Edit", "Share", "Close",
    ]
    dialog.close()


def test_subscription_refresh_preserves_chain_node_ids_and_marks_removed_nodes_stale(tmp_path):
    _app()
    state = AppState(str(tmp_path / "state.json"))
    sub = Subscription("Provider", "https://example.test/sub")
    keep = Node("Keep", NODE_TYPE_SOCKS5, "keep.example.test", 1080)
    stale = Node("Removed", NODE_TYPE_SOCKS5, "removed.example.test", 1080)
    keep.source_sub = stale.source_sub = sub.name
    chain = Chain("Uses removed node", [stale.node_id])
    state.subscriptions = [sub]
    state.nodes = [keep, stale]
    state.chains = [chain]
    state.active_base_node_id = keep.node_id
    page = BaseNodesPage(state)
    refreshed = Node("Keep", NODE_TYPE_SOCKS5, "new-keep.example.test", 1080)
    refreshed.source_sub = sub.name

    page._on_subscription_update_completed(
        sub.sub_id, [refreshed], [], {"last_update": "2026-11-16T17:00:00+00:00"}
    )

    assert refreshed.node_id == keep.node_id
    assert state.find_node_by_id(stale.node_id) is stale
    assert stale.extra["subscription_stale"] is True
    assert state.chains[0].hop_node_ids == [stale.node_id]
    assert sub.node_count == 1
    page.auto_update_timer.stop()


def test_subscription_group_tabs_include_empty_subscriptions(tmp_path):
    _app()
    state = AppState(str(tmp_path / "state.json"))
    state.subscriptions = [Subscription("Empty Provider", "https://example.test/sub")]
    page = BaseNodesPage(state)
    assert [page.group_tabs.tabText(i) for i in range(page.group_tabs.count())] == [
        "ALL", "Empty Provider",
    ]
    page.auto_update_timer.stop()


def test_subscription_group_context_menu_only_has_edit_and_remove(tmp_path):
    _app()
    state = AppState(str(tmp_path / "state.json"))
    state.subscriptions = [Subscription("Provider", "https://example.test/sub")]
    page = BaseNodesPage(state)
    menu = page._build_group_context_menu(1)
    assert [action.text() for action in menu.actions()] == ["Edit group…", "Remove group"]
    all_menu = page._build_group_context_menu(0)
    assert all_menu.actions() == []
    page.auto_update_timer.stop()


def test_auto_update_respects_enable_flag_interval_and_empty_url(tmp_path, monkeypatch):
    _app()
    state = AppState(str(tmp_path / "state.json"))
    ready = Subscription("Ready", "https://example.test/ready", update_interval=10)
    disabled = Subscription("Disabled", "https://example.test/disabled", enable_update=False, update_interval=10)
    no_url = Subscription("No URL", "", update_interval=10)
    state.subscriptions = [ready, disabled, no_url]
    page = BaseNodesPage(state)
    requested = []
    monkeypatch.setattr(page, "_request_subscription_update", requested.append)

    page._check_auto_updates()
    assert requested == [ready.sub_id]
    page.auto_update_timer.stop()
