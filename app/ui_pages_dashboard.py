from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from models.app_state import AppState


class _MetricCard(QFrame):
    def __init__(self, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardStatCard")
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        self.value_label = QLabel("0")
        self.value_label.setObjectName("dashboardStatValue")
        self.value_label.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {accent};"
        )
        layout.addWidget(self.value_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("dashboardStatTitle")
        self.title_label.setStyleSheet("font-size: 12px; letter-spacing: 0.5px; color: #5f6b70;")
        layout.addWidget(self.title_label)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("font-size: 12px; color: #465158;")
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)


class DashboardPage(QWidget):
    navigate_requested = Signal(str)
    apply_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    open_logs_requested = Signal()

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._runtime_text = "Stopped"
        self._can_apply = False
        self._can_start = False
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        root_layout.addWidget(scroll_area)

        content = QWidget()
        scroll_area.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 24)
        layout.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("dashboardHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(10)

        eyebrow = QLabel("OVERVIEW")
        eyebrow.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: #c46a2e;")
        hero_layout.addWidget(eyebrow)

        title = QLabel("Control Deck")
        title.setObjectName("dashboardHeroTitle")
        title.setStyleSheet("font-size: 30px; font-weight: 700; color: #1f2b33;")
        hero_layout.addWidget(title)

        subtitle = QLabel(
            "Build routes, publish local proxy ports, and start the selected core from a single guided workspace."
        )
        subtitle.setObjectName("dashboardHeroSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 14px; color: #41505a;")
        hero_layout.addWidget(subtitle)

        quick_actions = QHBoxLayout()
        quick_actions.setSpacing(10)

        self.btn_open_sources = QPushButton("Open Sources")
        self.btn_open_sources.clicked.connect(lambda: self.navigate_requested.emit("subscriptions"))
        quick_actions.addWidget(self.btn_open_sources)

        self.btn_open_routing = QPushButton("Open Routing")
        self.btn_open_routing.clicked.connect(lambda: self.navigate_requested.emit("routing"))
        quick_actions.addWidget(self.btn_open_routing)

        self.btn_apply = QPushButton("Apply Configuration")
        self.btn_apply.clicked.connect(lambda _checked=False: self.apply_requested.emit())
        quick_actions.addWidget(self.btn_apply)

        self.btn_start = QPushButton("Start Service")
        self.btn_start.clicked.connect(lambda _checked=False: self.start_requested.emit())
        quick_actions.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Service")
        self.btn_stop.clicked.connect(lambda _checked=False: self.stop_requested.emit())
        quick_actions.addWidget(self.btn_stop)

        self.btn_logs = QPushButton("Open Activity")
        self.btn_logs.clicked.connect(lambda _checked=False: self.open_logs_requested.emit())
        quick_actions.addWidget(self.btn_logs)

        quick_actions.addStretch()
        hero_layout.addLayout(quick_actions)
        layout.addWidget(hero)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(14)
        metrics_grid.setVerticalSpacing(14)

        self.metric_subscriptions = _MetricCard("Subscriptions", "#c46a2e")
        self.metric_nodes = _MetricCard("Nodes", "#2f7a73")
        self.metric_chains = _MetricCard("Chains", "#284b63")
        self.metric_ports = _MetricCard("Bindings", "#7b5b9a")
        self.metric_tun = _MetricCard("TUN Mode", "#cb4f3f")

        metrics_grid.addWidget(self.metric_subscriptions, 0, 0)
        metrics_grid.addWidget(self.metric_nodes, 0, 1)
        metrics_grid.addWidget(self.metric_chains, 0, 2)
        metrics_grid.addWidget(self.metric_ports, 1, 0)
        metrics_grid.addWidget(self.metric_tun, 1, 1)

        self.runtime_card = _MetricCard("Runtime", "#1f2b33")
        metrics_grid.addWidget(self.runtime_card, 1, 2)

        layout.addLayout(metrics_grid)

        lower_row = QHBoxLayout()
        lower_row.setSpacing(14)

        self.progress_card = QFrame()
        self.progress_card.setObjectName("dashboardPanel")
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(20, 18, 20, 18)
        progress_layout.setSpacing(12)
        progress_title = QLabel("Quick Start")
        progress_title.setObjectName("dashboardPanelTitle")
        progress_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #1f2b33;")
        progress_layout.addWidget(progress_title)

        self.step_sources = QLabel("")
        self.step_nodes = QLabel("")
        self.step_routing = QLabel("")
        self.step_core = QLabel("")
        self.step_run = QLabel("")

        for label in [
            self.step_sources,
            self.step_nodes,
            self.step_routing,
            self.step_core,
            self.step_run,
        ]:
            label.setWordWrap(True)
            label.setStyleSheet("font-size: 13px; color: #344047;")
            progress_layout.addWidget(label)

        lower_row.addWidget(self.progress_card, 3)

        self.preflight_card = QFrame()
        self.preflight_card.setObjectName("dashboardPanel")
        preflight_layout = QVBoxLayout(self.preflight_card)
        preflight_layout.setContentsMargins(20, 18, 20, 18)
        preflight_layout.setSpacing(12)

        preflight_title = QLabel("Readiness")
        preflight_title.setObjectName("dashboardPreflightTitle")
        preflight_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #1f2b33;")
        preflight_layout.addWidget(preflight_title)

        self.preflight_summary = QLabel("Waiting for workspace analysis.")
        self.preflight_summary.setWordWrap(True)
        self.preflight_summary.setStyleSheet("font-size: 14px; color: #344047;")
        preflight_layout.addWidget(self.preflight_summary)

        self.preflight_details = QLabel("")
        self.preflight_details.setWordWrap(True)
        self.preflight_details.setStyleSheet("font-size: 12px; color: #5d676c;")
        preflight_layout.addWidget(self.preflight_details)

        self.btn_next_step = QPushButton("Open the recommended next step")
        self.btn_next_step.clicked.connect(lambda: self.navigate_requested.emit(self.btn_next_step.property("target") or "subscriptions"))
        preflight_layout.addWidget(self.btn_next_step, alignment=Qt.AlignmentFlag.AlignLeft)
        preflight_layout.addStretch()

        lower_row.addWidget(self.preflight_card, 2)
        layout.addLayout(lower_row)

        self.refresh_table()

    def refresh_table(self) -> None:
        subscriptions = len(self.app_state.subscriptions)
        nodes = len(self.app_state.nodes)
        chains = len(self.app_state.chains)
        ports = len(self.app_state.port_mappings)
        exe_path = self.app_state.core_exe_paths.get(self.app_state.core_type, "")

        self.metric_subscriptions.set_value(
            str(subscriptions),
            "Providers configured" if subscriptions else "Add a provider or paste nodes manually",
        )
        self.metric_nodes.set_value(
            str(nodes),
            "Ready for routing" if nodes else "Import or create nodes first",
        )
        self.metric_chains.set_value(
            str(chains),
            "Route blueprints saved" if chains else "Build at least one chain",
        )
        self.metric_ports.set_value(
            str(ports),
            "Local proxy endpoints" if ports else "Create a binding to expose a route",
        )
        self.metric_tun.set_value(
            "On" if self.app_state.enable_tun else "Off",
            "Selected chain is active for system traffic" if self.app_state.enable_tun else "Optional system-wide routing is disabled",
        )
        self.runtime_card.set_value(
            self._runtime_text,
            f"Core: {self.app_state.core_type}" + (" • executable ready" if exe_path else " • executable missing"),
        )

        sources_text = "Complete" if subscriptions else "Missing"
        nodes_text = "Complete" if nodes else "Missing"
        routing_text = "Complete" if chains and ports else "In progress" if chains or ports else "Missing"
        core_text = "Complete" if exe_path else "Missing"
        run_text = "Ready" if self._can_start else "Blocked"

        self.step_sources.setText(f"1. Sources: {sources_text} — add subscriptions or import individual node URIs.")
        self.step_nodes.setText(f"2. Nodes: {nodes_text} — review the available nodes and remove unusable entries.")
        self.step_routing.setText(f"3. Routing: {routing_text} — build chains and bind them to local ports.")
        self.step_core.setText(f"4. Core setup: {core_text} — confirm the executable path and defaults.")
        self.step_run.setText(f"5. Run: {run_text} — apply configuration and start only when blockers are cleared.")

        self.btn_apply.setEnabled(self._can_apply)
        self.btn_start.setEnabled(self._can_start)
        self.btn_stop.setEnabled(self._runtime_text == "Running")

    def set_runtime_state(self, is_running: bool) -> None:
        self._runtime_text = "Running" if is_running else "Stopped"
        self.refresh_table()

    def set_preflight_summary(
        self,
        blockers: list[str],
        warnings: list[str],
        next_target: str,
        can_apply: bool,
        can_start: bool,
    ) -> None:
        self._can_apply = can_apply
        self._can_start = can_start

        if blockers:
            self.preflight_summary.setText(f"{len(blockers)} blocking issue(s) need attention.")
            details = blockers + ([f"Warning: {warning}" for warning in warnings] if warnings else [])
        elif warnings:
            self.preflight_summary.setText("The workspace is usable, but there are warnings to review.")
            details = [f"Warning: {warning}" for warning in warnings]
        else:
            self.preflight_summary.setText("Everything required for apply/start is in place.")
            details = ["You can apply the configuration and start the selected core now."]

        self.preflight_details.setText("\n".join(f"• {detail}" for detail in details[:6]))
        self.btn_next_step.setProperty("target", next_target)
        self.refresh_table()
