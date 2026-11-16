# Rust / Go Migration Assessment

**Status:** Architecture recommendation; no native rewrite is started by this document.

## Executive recommendation

If ChainPort is migrated, use **Go + Wails v3** for the first native implementation. Keep the existing sing-box, Xray, and Mihomo executables as the data plane. Reimplement the control plane (models, subscriptions, chain composition, config generation, process lifecycle, settings, and packaging) in Go.

Do not rewrite the proxy engines. ChainPort is an orchestrator: the external core performs the network forwarding. Rewriting the GUI and configuration manager in Rust or Go will not make proxied traffic materially faster. The expected gains are a self-contained application, stronger domain types, easier concurrency and distribution, and less runtime dependence on Python/PySide6.

Wails v3.0.0 is now the stable desktop release. Its official compatibility contract covers Windows, macOS, and Linux; it uses native WebViews, generated Go-to-frontend bindings, and requires Go 1.26 or later. Linux builds use GTK4 and WebKitGTK 6.0 by default. See the [Wails v3 status](https://wails.io/status/), [v3 release announcement](https://wails.io/blog/wails-v3-released/), and [installation requirements](https://wails.io/quick-start/installation/).

Tauri v2 is also a mature option. It uses a Rust backend and a web frontend rendered by the platform WebView. See the [Tauri v2 overview](https://v2.tauri.app/start/) and [Tauri crate documentation](https://docs.rs/tauri/latest/tauri/).

## Current system boundaries

| Area | Current implementation | Migration target |
|---|---|---|
| Domain state | `Node`, `Subscription`, `Chain`, `PortMapping`, `AppState` | Typed Go structs and validation methods |
| Persistence | JSON `state.json` | Versioned JSON repository; retain import/export compatibility |
| Subscription download | Requests | Go `net/http` with context, timeout, and cancellation |
| Subscription parsing | v2rayN URI/base64 and Clash YAML parsers | Protocol-specific Go packages and fixture tests |
| Composition | Ordered node IDs; reusable chain nodes | Explicit `ChainNode` aggregate with validated references |
| Core config | sing-box JSON, Xray JSON, Mihomo YAML | Three independent config generators with golden fixtures |
| Process lifecycle | `subprocess` wrapper and Qt signals | `os/exec`, context cancellation, stdout/stderr event stream |
| Desktop UI | PySide6 | Wails v3 + Svelte or React |

The data plane remains external. ChainPort should own configuration generation, validation, process lifecycle, local endpoint presentation, and user settings—not implement VLESS, WireGuard, TLS, or packet forwarding itself.

## Rust vs Go

| Criterion | Rust + Tauri v2 | Go + Wails v3 |
|---|---|---|
| Desktop UI | Web frontend + Rust commands | Web frontend + Go services |
| Type safety | Excellent; strong enums and compile-time modelling | Strong static typing; simpler domain modelling and iteration |
| Async work | Tokio ecosystem; powerful but more concepts | Goroutines and contexts are straightforward for downloads and process streams |
| JSON/YAML | Serde ecosystem is excellent | `encoding/json`; mature YAML libraries available |
| Process management | `std::process`, Tokio process | `os/exec`, contexts |
| Cross-platform desktop | Tauri v2 Windows/macOS/Linux support | Wails v3 stable Windows/macOS/Linux support |
| Linux system dependencies | WebKitGTK / GTK and Tauri prerequisites | GTK4 + WebKitGTK 6.0 by default |
| Learning / porting effort | Higher, especially for async, ownership, and FFI boundaries | Lower for a Python orchestration application |
| Best fit here | If the team prioritises Rust safety and accepts a larger port | If the team prioritises delivery speed and a maintainable orchestration service |

### Why Go is the better first port

1. Most current work is orchestration, parsing, configuration mapping, and child-process management—not low-level packet processing.
2. Go's `net/http`, `context`, goroutines, and `os/exec` map cleanly to the existing subscription and core lifecycle code.
3. Wails v3 provides the desired two-section desktop shell with a web UI while keeping application logic in a native Go binary.
4. Existing JSON profiles can be migrated incrementally without changing the proxy-core configuration contract.

Rust remains a strong alternative if the project later needs a highly constrained native agent, more complex privileged services, or a team already proficient in Rust. It is not justified solely by speed for this application.

## Proposed two-section UX

The simplified product should expose exactly two primary navigation items:

### 1. Node Groups

The main workspace is one chain-node list with four actions:

- **Create:** open a composer to name a route and select/reorder base-node hops.
- **Add:** import a v2rayN or Clash-compatible subscription, paste a share URI, or manage existing base nodes.
- **Edit / Remove:** update or delete the selected chain route.
- A single TUN switch routes system traffic through the currently selected chain.

Each saved `Chain` is the chain node. Do not store a second `Node(type=chain)` wrapper for the same route. Allocate a local mixed-proxy port automatically for each chain.

The chain composer should support:

1. Name the chain.
2. Select one or more base nodes.
3. Reorder hops from entry to exit.
4. Preview the route and protocol compatibility.
5. Save the chain; a local port is assigned automatically.

Subscriptions should be managed inside Node Groups, not as a separate top-level destination. Import formats should be explicit (`Auto`, `v2rayN`, `Clash YAML`) and show parse errors and node counts. Clash Verge compatibility means accepting its Clash-compatible subscription output; it does not imply reading Clash Verge's local application database.

### 2. Settings

Keep runtime and platform controls in one place:

- Core engine and executable path
- Automatic local mixed-proxy port allocation
- DNS provider and bootstrap resolver
- TLS fragmentation and QUIC policy
- Startup behaviour and platform integration
- Import/export and diagnostics

Start must generate and validate the selected core configuration before launching it. There is no separate Apply action. Stop remains a separate action. Logs are a secondary window, not a third primary navigation item.

## Domain model changes recommended before a full port

The current Python implementation uses `Chain` as the single canonical chain-node model. Previous releases also stored a duplicate `Node(type=chain)` wrapper; the current loader migrates those profiles by flattening their references and removing the wrapper. The native model should keep the simpler canonical structure:

```text
Node
  id, name, protocol, endpoint, credentials, tls, transport, source_id

Chain
  id, name, ordered_hops: []BaseNodeID

SubscriptionSource
  id, name, url, format, last_refresh, imported_node_ids

PortBinding
  id, chain_id, listen_host, automatically_assigned_port, protocols
```

Required invariants:

- Every chain reference must resolve to a base node.
- A chain must contain at least one hop.
- Deleting a base node used by a chain must be blocked or require an explicit cascade/replacement.
- Subscription refresh should preserve stable node identity where possible, or report which saved chains became invalid.
- Core generators consume a flattened, validated sequence of protocol nodes. They should never need to understand UI group structures.

## Migration plan

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | Stabilise current Python app and two-tab UX | Current tests pass; profile format documented |
| 1 | Go domain package | Round-trip fixtures for existing `state.json`; chain validation and legacy-wrapper migration tests |
| 2 | Go subscription package | v2rayN and Clash YAML fixture parity; cancellation and timeout tests |
| 3 | Go core generators | Golden output tests for sing-box, Xray, and Mihomo; each core's own config validator passes |
| 4 | Go process manager | Start/stop, stdout/stderr streaming, restart, and crash recovery tests |
| 5 | Wails v3 two-section UI | Node Groups composer and Settings; cross-platform smoke builds |
| 6 | Compatibility and cutover | Import/export old profiles; Windows/Linux/macOS test matrix; signed release packages |

Do not attempt a big-bang rewrite. Keep the Python release working while the Go domain and config generators are proven against existing fixture files. The first native milestone should be a CLI that can load a profile, validate chains, generate all three core configs, and run the relevant core's config checker. Add Wails only after that CLI is stable.

## Risks and decisions

- **Core version drift:** generators must target explicit supported core versions and validate generated output in CI.
- **Subscription format drift:** providers vary. Preserve raw parse diagnostics and fixture-test representative v2rayN and Clash YAML responses.
- **Secret handling:** do not log subscription tokens, passwords, UUIDs, or WireGuard private keys. Consider OS credential storage for secrets in the native version.
- **Privileged TUN operations:** keep elevation isolated to the operation that needs it; do not run the whole GUI as root/admin by default.
- **Linux WebView dependencies:** Wails v3 requires GTK4 and WebKitGTK 6.0 by default. Verify target distributions early; package dependencies or document supported distributions.
- **Profile compatibility:** version the JSON schema and provide one-way migrations with backups. Never overwrite an old profile before a successful migration.

## Decision

**Recommended direction: Go + Wails v3, staged migration, external proxy cores retained.** First finish and validate the simplified two-section Python UX and single canonical Chain model. Then port the domain and core generators to Go with golden tests. This reduces product risk and avoids rewriting the part of the system that already performs the actual proxying.
