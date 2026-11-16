# ChainPort Gateway

ChainPort Gateway is a cross-platform desktop manager for importing proxy nodes, composing reusable multi-hop chains, and exposing each route through a local proxy port. It generates configuration for sing-box, Xray, or Mihomo; those external core binaries handle the network data plane.

## Product model

```text
v2rayN / Clash-compatible subscription / share URI
                    |
                    v
                Base Nodes
                    |
          Create Chain / reorder hops
                    |
                    v
              Chain Node
          (one saved route)
                    |
                    v
           Local port binding
                    |
                    v
        sing-box / Xray / Mihomo
```

- **Base nodes** are individual VLESS, VMess, Trojan, Shadowsocks, SOCKS5, HTTP, or WireGuard profiles.
- **Chain nodes** are the saved routes themselves: one ordered list of base nodes, with an automatically allocated local proxy port. There is no second wrapper object for the same route.
- **Subscriptions** import v2rayN share-link feeds and Clash YAML feeds. Clash Verge-compatible subscription URLs are supported when the provider returns a Clash-compatible YAML document; this is not a direct Clash Verge profile-database integration.
- **Port bindings** expose a route on a local mixed (HTTP and SOCKS) proxy listener.

## Interface

The main window has exactly two top-level tabs:

1. **Node Groups** — one chain-node list with Create, Add, Edit, and Remove actions. Add opens base-node import and management actions.
2. **Settings** — core selection, executable paths, DNS, TLS fragmentation, QUIC, and startup preferences.

The bottom action bar provides Start, Stop, and Logs. Start generates and validates the selected core configuration before launching it; there is no separate Apply step. Runtime logs open in a separate window. TUN is a single switch in Node Groups and follows the currently selected chain node.

### Create a chain node

1. Choose **Node Groups → Add** to import a subscription, paste a share URI, create a base node manually, or manage imported profiles.
2. Choose **Create**, name the route, and select its base-node hops in entry-to-exit order.
3. Save the chain. ChainPort automatically allocates a local mixed-proxy port.
4. Select a chain node and enable the TUN switch if system-wide routing is required.
5. Choose **Start**. ChainPort generates and validates the configuration, then starts the selected core.

Existing profiles created by earlier versions are migrated from the old duplicate Chain Node wrapper into the single canonical Chain model. Missing base-node references invalidate a route rather than silently changing its path.

## Requirements

- Python 3.11 or newer (Python 3.12 is recommended).
- PySide6, Requests, and PyYAML from `requirements.txt`.
- One supported core executable: sing-box, Xray, or Mihomo.
- Linux TUN mode requires root privileges and the platform's TUN support. Windows TUN mode requires administrator privileges.

`ctypes`, `os`, `sys`, `json`, `subprocess`, `uuid`, and other Python standard-library modules are not installed with pip.

## Install

Create an isolated environment:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install runtime dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install development/test dependencies when contributing:

```bash
python -m pip install -r requirements-dev.txt
```

## Core executable paths

The application detects the platform-specific binaries in these locations when present:

| Core | Linux | Windows |
|---|---|---|
| sing-box | `bin/sing_box/sing-box` | `bin/sing_box/sing-box.exe` |
| Xray | `bin/xray/xray` | `bin/xray/xray.exe` |
| Mihomo | `bin/mihomo/mihomo` | `bin/mihomo/mihomo.exe` |

Core binaries are not distributed in this repository. Download the correct release for the operating system and architecture, place it in the matching directory, and select it in **Settings** if automatic detection does not find it. On Linux, ensure the binary is executable (`chmod +x path/to/core`). Paths saved by another operating system are discarded and re-detected on load.

## Run

```bash
python main.py
```

Recommended first run:

1. Use **Add** to import a subscription or paste a share URI.
2. Choose **Create** and arrange the base-node hops.
3. Confirm the core executable in Settings.
4. Choose **Start**. A local proxy port is allocated automatically for every chain.

Use the HTTP CONNECT endpoint for browser/system proxy settings when you want the hostname to reach ChainPort for proxy-side DNS resolution. SOCKS clients should use remote DNS (often called `socks5h`) rather than resolving target hostnames locally.

## Platform behaviour

- **Windows:** Run as Admin uses UAC. Login startup uses the current-user Run registry key.
- **Linux:** UAC controls are hidden. Login startup uses `~/.config/autostart/chainport-gateway.desktop` (or `$XDG_CONFIG_HOME/autostart`). Run `sudo python main.py` only when TUN mode requires root; ordinary local proxy mode should run as the desktop user.
- **macOS:** Core management is supported by the Python/Qt application where the selected core is available. Login startup integration is not implemented yet.

## Configuration and data

- `state.json` is created locally and is intentionally excluded from Git. It stores subscriptions, nodes, chains, port bindings, and application settings.
- Generated core configurations and runtime logs are written to the configured output directory (default: `logs/`).
- Do not commit subscription URLs, access tokens, private keys, passwords, or personal proxy profiles.

## Development

Run tests:

```bash
python -m pytest tests/ -q
```

Compile-check Python modules:

```bash
python -m compileall -q app core models parsers utils tests
```

Run the GUI headlessly for a smoke test:

```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; from models.app_state import AppState; from app.ui_main_window import MainWindow; app = QApplication([]); window = MainWindow(AppState('/tmp/chainport-smoke-state.json')); print([window.tabs.tabText(i) for i in range(window.tabs.count())])"
```

See [the Rust and Go migration assessment](docs/architecture-rust-go.md) for the proposed next-generation implementation strategy.

## License

MIT
