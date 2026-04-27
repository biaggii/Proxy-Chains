"""
Dashboard / Home page.

Shows at-a-glance metrics, a guided quick-start checklist, and the
readiness preflight panel.  All action buttons (Apply / Start / Stop)
live in the global action bar — they are NOT duplicated here.
"""

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)

from models.app_state import AppState


class _MetricCard(QFrame):
    """Small stat tile for the dashboard grid."""

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
        self.title_label.setStyleSheet(
            "font-size: 12px; letter-spacing: 0.5px; color: #5f6b70;"
        )
        layout.addWidget(self.title_label)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("font-size: 12px; color: #465158;")
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)

    def set_accent(self, color: str) -> None:
        self.value_label.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {color};"
        )


class DashboardPage(QWidget):
    """Home page with metrics, quick start, and preflight readiness."""

    navigate_requested = Signal(str)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._runtime_text = "Stopped"
        self._can_apply = False
        self._can_start = False
        self._build_ui()
        self._init_animations()

    def _init_animations(self) -> None:
        self.opacity_effect = QGraphicsOpacityEffect(self.runtime_card)
        self.runtime_card.setGraphicsEffect(self.opacity_effect)

        self.heartbeat = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.heartbeat.setDuration(1500)
        self.heartbeat.setStartValue(1.0)
        self.heartbeat.setKeyValueAt(0.5, 0.4)
        self.heartbeat.setEndValue(1.0)
        self.heartbeat.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.heartbeat.setLoopCount(-1)

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

        # ── Hero banner ─────────────────────────────────
        hero = QFrame()
        hero.setObjectName("dashboardHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(10)

        eyebrow = QLabel("OVERVIEW")
        eyebrow.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: #c46a2e;"
        )
        hero_layout.addWidget(eyebrow)

        title = QLabel("Control Deck")
        title.setObjectName("dashboardHeroTitle")
        title.setStyleSheet("font-size: 30px; font-weight: 700; color: #1f2b33;")
        hero_layout.addWidget(title)

        subtitle = QLabel(
            "Build routes, publish local proxy ports, and start the selected core "
            "from the global action bar below."
        )
        subtitle.setObjectName("dashboardHeroSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 14px; color: #41505a;")
        hero_layout.addWidget(subtitle)

        # Navigation shortcuts only — no duplicate Apply/Start/Stop.
        nav_row = QHBoxLayout()
        nav_row.setSpacing(10)

        self.btn_open_sources = QPushButton("Open Sources")
        self.btn_open_sources.clicked.connect(
            lambda: self.navigate_requested.emit("subscriptions")
        )
        nav_row.addWidget(self.btn_open_sources)

        self.btn_open_routing = QPushButton("Open Routing")
        self.btn_open_routing.clicked.connect(
            lambda: self.navigate_requested.emit("routing")
        )
        nav_row.addWidget(self.btn_open_routing)

        nav_row.addStretch()
        hero_layout.addLayout(nav_row)
        layout.addWidget(hero)

        # ── Metric grid ─────────────────────────────────
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

        # ── Lower panels ────────────────────────────────
        lower_row = QHBoxLayout()
        lower_row.setSpacing(14)

        # Quick Start checklist (single source — not duplicated in Settings)
        self.progress_card = QFrame()
        self.progress_card.setObjectName("dashboardPanel")
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(20, 18, 20, 18)
        progress_layout.setSpacing(12)
        progress_title = QLabel("Quick Start")
        progress_title.setObjectName("dashboardPanelTitle")
        progress_title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1f2b33;"
        )
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

        # Readiness / Preflight panel
        self.preflight_card = QFrame()
        self.preflight_card.setObjectName("dashboardPanel")
        preflight_layout = QVBoxLayout(self.preflight_card)
        preflight_layout.setContentsMargins(20, 18, 20, 18)
        preflight_layout.setSpacing(12)

        preflight_title = QLabel("Readiness")
        preflight_title.setObjectName("dashboardPreflightTitle")
        preflight_title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1f2b33;"
        )
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
        self.btn_next_step.clicked.connect(
            lambda: self.navigate_requested.emit(
                self.btn_next_step.property("target") or "subscriptions"
            )
        )
        preflight_layout.addWidget(
            self.btn_next_step, alignment=Qt.AlignmentFlag.AlignLeft
        )

        preflight_layout.addStretch()

        lower_row.addWidget(self.preflight_card, 2)
        layout.addLayout(lower_row)

        self.refresh()

    # ── Public API ──────────────────────────────────────

    def refresh(self) -> None:
        """Reload all dashboard data from the current state."""
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
            "Selected chain is active for system traffic"
            if self.app_state.enable_tun
            else "Optional system-wide routing is disabled",
        )
        self.runtime_card.set_value(
            self._runtime_text,
            f"Core: {self.app_state.core_type}"
            + (" • executable ready" if exe_path else " • executable missing"),
        )

        sources_text = "Complete" if subscriptions else "Missing"
        nodes_text = "Complete" if nodes else "Missing"
        routing_text = (
            "Complete"
            if chains and ports
            else "In progress"
            if chains or ports
            else "Missing"
        )
        core_text = "Complete" if exe_path else "Missing"
        run_text = "Ready" if self._can_start else "Blocked"

        self.step_sources.setText(
            f"1. Sources: {sources_text} — add subscriptions or import individual node URIs."
        )
        self.step_nodes.setText(
            f"2. Nodes: {nodes_text} — review the available nodes and remove unusable entries."
        )
        self.step_routing.setText(
            f"3. Routing: {routing_text} — build chains and bind them to local ports."
        )
        self.step_core.setText(
            f"4. Core setup: {core_text} — confirm the executable path and defaults."
        )
        self.step_run.setText(
            f"5. Run: {run_text} — apply configuration and start only when blockers are cleared."
        )

    def set_runtime_state(self, is_running: bool) -> None:
        self._runtime_text = "Running" if is_running else "Stopped"
        if is_running:
            self.heartbeat.start()
            self.runtime_card.set_accent("#2ecc71")
        else:
            self.heartbeat.stop()
            self.opacity_effect.setOpacity(1.0)
            self.runtime_card.set_accent("#1f2b33")
        self.refresh()

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
            self.preflight_summary.setText(
                f"{len(blockers)} blocking issue(s) need attention."
            )
            details = blockers + (
                [f"Warning: {warning}" for warning in warnings] if warnings else []
            )
        elif warnings:
            self.preflight_summary.setText(
                "The workspace is usable, but there are warnings to review."
            )
            details = [f"Warning: {warning}" for warning in warnings]
        else:
            self.preflight_summary.setText(
                "Everything required for apply/start is in place."
            )
            details = [
                "You can apply the configuration and start the selected core now."
            ]

        self.preflight_details.setText(
            "\n".join(f"• {detail}" for detail in details[:6])
        )
        self.btn_next_step.setProperty("target", next_target)
        # NOTE: Do NOT call self.refresh() here — that was causing
        # recursive refresh loops.  The caller already handles refresh.
