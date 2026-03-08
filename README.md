# ChainPort Gateway

ChainPort Gateway is a Windows desktop GUI for building multi-hop proxy routes, exposing them on local ports, and starting a single proxy core process from one workspace.

Core flow:

```text
Subscription URL -> Download -> Parse into Nodes -> Build Chains -> Bind Local Ports -> Generate Config -> Start Core
```

## What It Does

- Imports provider subscriptions and single share URIs
- Manages nodes for `vmess`, `vless`, `trojan`, `shadowsocks`, `socks5`, and `http`
- Builds ordered chains with one or many hops
- Publishes chains as local SOCKS5 endpoints on different ports
- Supports optional system-wide routing through TUN mode
- Generates configs for `sing-box`, `xray`, and `mihomo`
- Saves the full workspace in `state.json`

## UI Flow

The current UI is organized around six tabs:

1. `Home`
   The dashboard shows readiness, counts, quick actions, and the next required step.
2. `Subscriptions`
   Add provider URLs and refresh imported nodes.
3. `Nodes`
   Review imported nodes, paste node URIs, copy node URIs, and create single-hop chains.
4. `Routing`
   Build chains, create port bindings, and manage the dedicated TUN chain from one combined workspace.
5. `Logs`
   Watch config validation output and live core logs.
6. `Settings`
   Configure the core executable, runtime options, startup behavior, auto-start launch behavior, and profile import/export.

Global actions stay available at the bottom of the window:

- `Apply`
- `Run as Admin`
- `Start`
- `Stop`

## Requirements

- Windows
- Python 3.11 or newer
- Dependencies from `requirements.txt`
- `pywin32` for Windows startup integration

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
pip install pywin32
```

Run the application:

```bash
python main.py
```

Recommended first-run sequence:

1. Open `Home` and review the readiness checklist.
2. Open `Settings` and confirm the core type and executable path.
3. Add subscription sources or paste node URIs in `Nodes`.
4. Build chains and port bindings in `Routing`.
5. Click `Apply`.
6. Click `Start`.

## TUN Mode Notes

- TUN mode routes system traffic through one selected chain.
- TUN mode usually requires administrator privileges on Windows.
- Use `Run as Admin` before starting the core when TUN is enabled.
- Automatic app launch starts chains only and does not enable TUN.

## Project Structure

```text
main.py
state.json
README.md
AGENTS.md

app/
  ui_main_window.py
  ui_pages_dashboard.py
  ui_pages_subscriptions.py
  ui_pages_nodes.py
  ui_pages_routing.py
  ui_pages_chains.py
  ui_pages_ports.py
  ui_pages_logs.py
  ui_pages_settings.py

models/
  app_state.py
  node.py
  subscription.py
  chain.py
  port_mapping.py

parsers/
  subscription_fetcher.py
  clash_yaml_parser.py
  v2rayn_parser.py
  uri_parsers.py

core/
  core_adapter_base.py
  singbox_adapter.py
  xray_adapter.py
  mihomo_adapter.py
  process_runner.py

tests/
  test_clash_parser.py
  test_v2rayn_parser.py
  test_chain_building.py
  test_singbox_adapter.py
```

## Development

Run the test suite:

```bash
python -m pytest tests/ -q
```

Run a compile check:

```bash
python -m compileall app core models parsers
```

Optional Qt smoke test for headless environments:

```bash
set QT_QPA_PLATFORM=offscreen
python -c "from PySide6.QtWidgets import QApplication; from models.app_state import AppState; from app.ui_main_window import MainWindow; app = QApplication([]); MainWindow(AppState()); print('ok')"
```

## License

MIT
