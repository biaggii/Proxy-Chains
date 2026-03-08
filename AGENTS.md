# AGENTS.md - AI Developer Guide

This document gives AI coding assistants the minimum project context needed to work safely and consistently in this repository.

## Project Overview

ChainPort Gateway is a Windows desktop GUI for managing proxy routes for browsers and other applications.

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
| `XrayAdapter` | `proxySettings.tag` | JSON |
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

| Tab | File | Responsibility |
| :-- | :--- | :------------- |
| Home | `app/ui_pages_dashboard.py` | Readiness, quick actions, metrics, and next-step guidance |
| Subscriptions | `app/ui_pages_subscriptions.py` | Provider source management and refresh |
| Nodes | `app/ui_pages_nodes.py` | Node review, manual import, URI copy/paste, and chain helpers |
| Routing | `app/ui_pages_routing.py` | Combined routing workspace that hosts Chains and Ports |
| Logs | `app/ui_pages_logs.py` | Live stdout/stderr and validation output |
| Settings | `app/ui_pages_settings.py` | Core executable, startup behavior, auto-start launch behavior, advanced options, and profile import/export |

Nested routing pages:

| Page | File | Responsibility |
| :--- | :--- | :------------- |
| Chains | `app/ui_pages_chains.py` | Create and edit chains |
| Ports | `app/ui_pages_ports.py` | Manage port bindings and the dedicated TUN route |

`app/ui_main_window.py` is the shell for the whole app:

- Organizes the six top-level tabs with `QTabWidget`
- Keeps `Apply`, `Run as Admin`, `Start`, and `Stop` visible globally
- Runs readiness checks and updates the Home dashboard plus action bar state
- Bridges background process logs into the GUI thread with `LogBridge(QObject)` and `Signal`
- Saves `state.json` whenever a page emits `data_changed`

## Language And UI Policy

- All user-facing UI text must be English
- All dialogs, notifications, runtime logs, parser error messages, and generated default display names must be English
- New or modified comments and docstrings should be English
- Keep the Home dashboard, Routing workspace, and global action bar terminology consistent across UI and docs

Preferred product terms:

- Use `source` or `subscription source` instead of untranslated provider wording
- Use `binding` or `port binding` when describing the UI
- Use `Routing` for the combined Chains plus Ports workspace

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
