# Findings — Graphify + UI/UX Deep Audit

## Project Overview
- **Name**: ChainPort Gateway
- **Tech Stack**: Python 3.14, PySide6 (Qt6)
- **Core Function**: Proxy routing management (Subscription → Node → Chain → Port → Core Engine)
- **Total UI Code**: 2,858 lines across 10 files

## Critical Discovery: QSS Cascade War
Three separate locations define `QTabBar::tab` styles:
1. `main.py:66-72` — blue underline style
2. `ui_main_window.py:68-77` — filled pill style with `#1f4b99`
3. `ui_pages_routing.py:93-104` — ANOTHER filled style

Qt applies these in cascade order, creating unpredictable rendering. This is the single biggest visual inconsistency.

## Critical Discovery: Duplicate UI Elements
| Element | Location 1 | Location 2 |
|---------|-----------|-----------|
| Apply/Start/Stop buttons | MainWindow bottom bar | Dashboard hero section |
| Metric cards (Chains, Bindings, TUN) | Dashboard | RoutingPage stat row |
| Quick Start 5-step guide | Dashboard | Settings page |

## Code Duplication: `_set_feedback()` 
Identical function body (color dict + CSS template) exists in 4 files:
- `ui_pages_subscriptions.py:207-218`
- `ui_pages_ports.py:422-433`
- `ui_pages_settings.py:314-325`
- `ui_main_window.py:590-602` (as `_show_banner()`)

## Structural Issue: NodesPage Monolith
`ui_pages_nodes.py` is 772 lines containing 3 classes:
- `NodeEditDialog` (lines 28-232) — 204 lines
- `TcpPingWorker` (lines 233-268) — 36 lines
- `NodesPage` (lines 272-772) — 500 lines

## Performance Issue: Broadcast Refresh
Every `data_changed` signal triggers `_refresh_all_pages()` which refreshes ALL 8 pages. With 500+ nodes, this creates noticeable UI lag.

## Language Policy Violation
6+ files contain Chinese comments/docstrings despite AGENTS.md requiring English.

## Dependency Graph
- `app/` → `models/`, `core/`, `parsers/`
- `core/` → `models/`
- `parsers/` → `models/`
- `models/` → (no local dependencies)

## 2026-04-28 Cross-Repo Improvement Study
- `graphify detect .` found `717 files` and about `351,894 words`.
- Corpus split: `654 code`, `26 document`, `37 image`, `0 paper`, `0 video`.
- `3` sensitive files were skipped by detector.
- Top-level file concentration:
  - `Refer Projects`: `660`
  - `app`: `17`
  - `tests`: `7`
  - `core`: `6`
  - `models`: `6`
- This means `graphify .` is dominated by reference repos and is poor default input for improving local app.

## Reference Repo Signals
- `Refer Projects/clash-verge-rev`:
  - Modern desktop stack: `Tauri + Rust + TypeScript`.
  - Explicit feature set includes theming, CSS injection, visual node/rule editing, config backup/sync, TUN mode.
  - Strong signal for product/UX patterns and settings surface, not direct code reuse.
- `Refer Projects/v2rayn`:
  - Mature cross-platform GUI client supporting `Xray`, `sing-box`, and other cores.
  - README is thin; likely better as architectural/feature comparison source than documentation model.

## Local-Only Graph Results
- Narrowed local corpus: `49 files`, about `23,814 words`.
- Mix: `44 code`, `5 document`, `0 image`, `0 video`.
- Structural graph output:
  - `615 nodes`
  - `1766 edges`
  - `24 communities`
- Top graph hubs:
  - `AppState` (`161` edges)
  - `Node` (`155`)
  - `Chain` (`92`)
  - `PortMapping` (`72`)
  - `NodesPage` (`49`)
- Biggest graph takeaway: state and model classes dominate cross-module coupling far more than adapter classes.

## Cross-Repo Improvement Direction
- `clash-verge-rev/src` uses feature-oriented frontend slices: `components`, `hooks`, `pages`, `providers`, `services`, `types`, `utils`.
- `v2rayN/v2rayN` uses multi-project solution layout with explicit service libraries and desktop shell separation.
- Current repo remains strongly page-centric in `app/`, with domain state concentrated in one `AppState` object and no separate service layer.
- Improvement bias should be:
  - split orchestration from Qt pages,
  - reduce `AppState` centrality,
  - introduce feature/service boundaries before any larger UI redesign.
