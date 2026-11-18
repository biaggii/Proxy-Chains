# AGENTS.md - AI Developer Guide

This document gives AI coding assistants the minimum project context needed to work safely and consistently in this repository.

## Project Overview

ChainPort Gateway is a cross-platform desktop GUI for managing proxy nodes, ordered multi-hop Chains, local proxy listeners and one TUN route.

Core flow:

```text
Subscription URL -> Download -> Parse into Nodes -> Build Chains -> Bind Local Ports -> Generate Core Config -> Start Process
```

## Architecture

```text
app/     -> GUI shell and pages
models/  -> data models and JSON persistence
parsers/ -> subscription and URI parsing
core/    -> core config generation and process control
```

Dependency direction is one-way:

```text
app/ -> models/
app/ -> parsers/
app/ -> core/ -> models/
parsers/ -> models/
models/ -> no local package dependencies
```

## Data Models

| Class | File | Purpose |
| :---- | :--- | :------ |
| `Node` | `models/node.py` | One proxy node |
| `Subscription` | `models/subscription.py` | One provider source |
| `Chain` | `models/chain.py` | Ordered hop list of node ids |
| `PortMapping` | `models/port_mapping.py` | Local port bound to a chain |
| `AppState` | `models/app_state.py` | Global app state and persistence |

All models implement:

- `to_dict() -> dict`
- `from_dict(dict) -> Self`
- `__repr__() -> str`

## Core Adapters

`core/core_adapter_base.py` defines:

```python
class CoreAdapterBase(ABC):
    def generate_config(app_state) -> tuple[str, str]
    def get_check_command(config_path, exe_path) -> list[str]
    def get_start_command(config_path, exe_path) -> list[str]
```

Current implementations:

| Adapter | Chain Field | Config Format |
| :------ | :---------- | :------------ |
| `SingBoxAdapter` | `detour` | JSON |
| `XrayAdapter` | `streamSettings.sockopt.dialerProxy` | JSON |
| `MihomoAdapter` | `dialer-proxy` | YAML |

Chain outbound naming rule:

```text
CHAIN_{chain_id}_H{hop_number}
```

## Parsers

Primary entry points:

```python
nodes, errors = fetch_and_parse(subscription)
nodes, errors = parse_text_only(raw_text, sub_name, sub_type)
```

Auto-detection rules:

- If the content contains `proxies:`, treat it as Clash YAML
- Otherwise treat it as v2rayN text, with optional base64 decoding

Supported URI schemes in `parsers/uri_parsers.py`:

`vmess://`, `vless://`, `trojan://`, `ss://`, `socks5://`, `socks://`, `http://`, `https://`

Parser errors should be actionable and include location plus reason.

## GUI Pages

The active UI has exactly two top-level tabs:

| Tab / subtab | File | Responsibility |
| :--- | :--- | :--- |
| Node Groups / Base | `app/ui_pages_node_groups.py`, `app/ui_pages_base_nodes.py` | Base Node table, subscription source tabs, node context menu, active Base selection and Base-node TUN binding. |
| Node Groups / Chain | `app/ui_pages_node_groups.py`, `app/ui_pages_chains.py` | Saved ordered Chains, one local port per Chain, create/edit/remove and whole-Chain TUN binding. |
| Settings | `app/ui_pages_settings.py` | Core executable, DNS, network/fragment options, startup behavior and profile import/export. |
| Runtime Logs dialog | `app/ui_pages_logs.py` | Live core stdout/stderr, validation output, clear/copy snapshot. Open only from the global Logs control; Start must not open it automatically. |

Dialogs:

| File | Responsibility |
| :--- | :--- |
| `app/dialogs/chain_editor_dialog.py` | Create/edit Chain name, ordered hops and its local listen port. |
| `app/dialogs/node_edit_dialog.py` | Edit one Base Node. |
| `app/dialogs/subscription_edit_dialog.py` | Create/edit a subscription source. |
| `app/dialogs/subscription_manager_dialog.py` | Manage sources and trigger updates. |

`app/ui_main_window.py` owns the two top-level tabs and global Logs/status/TUN/Shared Port/Start-Stop toolbar. It generates and validates the selected core config before starting the external process, bridges background logs into the GUI thread with `LogBridge(QObject)` and `Signal`, and saves `state.json` when pages emit `data_changed`.

TUN binding is exactly one target: one Base Node or one complete ordered Chain. A Chain binding must preserve all hops and order; never convert it to one hop. `AppState.tun_chain_id` stores the full Chain binding, while `tun_node_id` stores a Base Node binding.

For the verified current architecture, migration assessment and handover plan, read `docs/GO-WAILS3-REWRITE-PLAN.md`. Older audits and task notes may describe a previous multi-tab UI and are historical only.

## Language And UI Policy

- All user-facing UI text must be English
- All dialogs, notifications, runtime logs, parser error messages, and generated default display names must be English
- New or modified comments and docstrings should be English
- Keep Node Groups, Base, Chain, Settings and the global action bar terminology consistent across UI and docs

Preferred product terms:

- Use `source` or `subscription source` instead of untranslated provider wording
- Use `binding` or `port binding` when describing the UI
- Use `Chain` for a saved ordered route; each Chain has one local proxy port

## Coding Conventions

### Naming

- Variables use `snake_case`
- Constants use `UPPER_SNAKE_CASE`
- Classes use `PascalCase`

### Functions

- Prefer functions at or under 40 lines when practical
- Keep each file focused on one responsibility
- Add type hints to all functions

### Error Handling

- Parsing should collect recoverable errors into `error_messages: list[str]`
- Error messages should include location, content preview, and a concrete reason when possible
- `fetch_and_parse()` should not raise for normal parsing failures; return errors instead

## Testing

Primary verification commands:

```bash
python -m pytest tests/ -q
python -m compileall app core models parsers
```

Recommended Qt smoke test for UI-impacting changes:

```bash
set QT_QPA_PLATFORM=offscreen
python -c "from PySide6.QtWidgets import QApplication; from models.app_state import AppState; from app.ui_main_window import MainWindow; app = QApplication([]); MainWindow(AppState()); print('ok')"
```

Important coverage areas:

- `tests/test_clash_parser.py`
- `tests/test_v2rayn_parser.py`
- `tests/test_chain_building.py`
- `tests/test_singbox_adapter.py`

## Adding Support

### Add a New URI Protocol

1. Add `parse_xxx_uri()` in `parsers/uri_parsers.py`
2. Add a matching branch in `parse_single_uri()`
3. Add a node type constant in `models/node.py`
4. Add outbound support in each relevant adapter
5. Add tests in `tests/test_v2rayn_parser.py`

### Add a New Core Engine

1. Add `core/xxx_adapter.py` and inherit from `CoreAdapterBase`
2. Implement `generate_config()`, `get_check_command()`, and `get_start_command()`
3. Add the adapter branch in `app/ui_main_window.py`
4. Add the UI option in `app/ui_pages_settings.py`

## Important Paths

| Purpose | Path |
| :------ | :--- |
| App state | `./state.json` |
| sing-box config | `./singbox_config.json` |
| Xray config | `./xray_config.json` |
| Mihomo config | `./mihomo_config.yaml` |

@RTK.md

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
