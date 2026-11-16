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
- **Subscriptions** are managed in a v2rayN-style Subscription Group Manager. Each group stores its URL, source format, update policy, User-Agent, HTTP headers, remarks filter, sorting, and conversion-related settings. v2rayN share-link feeds and Clash YAML feeds are supported; this is not a direct Clash Verge profile-database integration.
- **Port bindings** expose a route on a local mixed (HTTP and SOCKS) proxy listener.

## Interface

The main window has exactly two top-level tabs:

1. **Node Groups** — two subtabs: **Base** and **Chain**. Base is a v2rayN-style individual-node list with subscription groups; Chain is the multi-hop route list.
2. **Settings** — core selection, executable paths, DNS, TLS fragmentation, QUIC, and startup preferences.

The top-right global toolbar is shared by Node Groups and Settings: Logs, runtime/readiness status, the bound TUN node, the TUN switch, editable Shared Port, and one large Run button that changes between Start and Stop. Start generates and validates the selected core configuration before launching it; there is no separate Apply step. Runtime logs open in a separate window.

### Base Nodes

- All individual nodes imported from any subscription or added manually appear in one v2rayN-style table, grouped by their subscription source.
- Base subscription groups are shown as subtabs: `ALL`, `Customs`, and one tab per subscription using its name directly (without a `sub-` prefix).
- **Subscriptions…** opens the v2rayN-style group manager with Add, Delete, Edit, Share, Update, Update All, and Close. Right-click an individual subscription tab to Edit or Remove that group; those group actions are not duplicated as buttons beside the tabs.
- **Edit** and **Remove** are available from the Base node table's right-click menu; there are no duplicate buttons below the table. Manual node creation and URI paste are also available from that menu.
- Add/Edit subscription supports optional URL, Auto/v2rayN/Clash format, Enable update, automatic interval in minutes, remarks regular-expression filter, convert target type, User-Agent, JSON HTTP headers, sort, previous/next proxy remarks with profile selection, custom core, custom SOCKS port, and remarks memo.
- Updates run in the background. Manual Update and Update All are available in the manager; automatic updates run when enabled and the interval is greater than zero. A successful refresh preserves node IDs for matching profiles and retains removed profiles as stale while a Chain, Active Base selection, or TUN binding still references them.
- The selected Base Node is exposed through one shared local proxy endpoint, shown and editable in the global toolbar. The default is `127.0.0.1:10808`.
- Changing the selected Base Node changes the outbound behind that same port. If the core is running, ChainPort regenerates, validates, and restarts it automatically.
- One shared TUN switch sits in the global toolbar. Right-click any Base Node or any individual hop inside a Chain and choose **Bind TUN**. Exactly one node ID is stored as the TUN binding; binding another node replaces it. The toolbar shows the bound node name and the node is marked in its table. TUN creates no extra local proxy port.

### Chain Nodes

1. Choose **Node Groups → Base → Subscriptions… → Add** to create a subscription group and enter its settings. Choose **Update** to refresh one group or **Update All** to refresh every configured URL.
2. Alternatively, right-click the Base node table to paste a share URI or create a single node manually.
3. Choose **Node Groups → Chain**. **Create** is aligned at the right end of the chain summary row. Name the route and select its Base Node hops in entry-to-exit order. Right-click an existing chain to **Edit** or **Remove** it; no duplicate buttons sit below the table.
4. Save the chain. ChainPort automatically allocates one local proxy port for each chain, starting at `127.0.0.1:20001`.
5. Choose **Start**. ChainPort generates and validates the configuration, then starts the selected core.

With one active Base Node and N saved Chains, the local proxy port count is N + 1: one shared Base port plus one port per Chain. TUN is a separate virtual interface and does not add a local proxy port.

Existing profiles created by earlier versions are migrated from the old duplicate Chain Node wrapper into the single canonical Chain model. Legacy TUN chain selections migrate to one Base Node (the old chain's final hop). Missing base-node references invalidate a route rather than silently changing its path.

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

1. Open **Subscriptions… → Add** to configure a subscription, or right-click the Base table to paste a share URI.
2. Choose **Chain → Create** and arrange the base-node hops.
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
