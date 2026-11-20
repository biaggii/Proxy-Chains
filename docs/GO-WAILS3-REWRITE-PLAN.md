# ChainPort Go + Wails v3 Rewrite Plan

**Current status (2026-11-19):** Go/Wails is the active implementation, integrated into `main` from `rewrite/go-wails3`. The former Python/PySide6 source, tests and dependency manifests have been removed from the active tree. The Go legacy `state.json` importer remains.
**Historical scope:** The pre-rewrite inventory, Python source paths, line counts and behavior notes below were captured on 2026-11-18. They document the migration rationale, not a current runtime or a requirement to restore Python.
**Assessment date:** 2026-11-18
**Active application:** `go-wails3/`
**Active stack:** Go + Wails v3 + React + TypeScript + Vite + pnpm + shadcn/ui.

## 1. Executive decision

Decision implemented: the application shell and services are Go/Wails; sing-box, Xray and Mihomo remain external proxy data planes. Go owns domain state, subscriptions, route composition, configuration generation, validation, process lifecycle, TUN integration, persistence, diagnostics and platform integration. Wails provides the desktop runtime bridge; React/TypeScript owns presentation.

The Go rewrite is now the active application. The former Python source has been removed after the rewrite branch was reviewed for integration. The legacy `state.json` format remains an import compatibility contract; do not reintroduce a Python runtime to support it.

Wails v3 is now a stable desktop release line, not the old v3 alpha. The current official status page describes stable desktop support for Windows, macOS and Linux; Wails v3 requires Go 1.26+, and Linux uses GTK4 + WebKitGTK 6.0 by default. Pin an exact stable Wails version rather than tracking nightly builds. The local development environment observed during this assessment is Go 1.27.4, Node 24.22.1 and pnpm 12.15.0.

## 2. Historical Python repository inventory (2026-11-18)

This section records the 7,347-line Python/PySide6 implementation that was audited before the rewrite. Those application files are no longer in the active source tree; the full source remains recoverable from `backup/main-before-go-wails3-20261119`. The Go importer preserves the legacy `state.json` compatibility boundary. The historical runtime flow was:

```text
PySide6 UI
  -> AppState / Node / Subscription / Chain / PortMapping
  -> subscription fetch + URI / v2rayN / Clash-YAML parsers
  -> sing-box / Xray / Mihomo config adapters
  -> ProcessRunner (external core process, stdout/stderr, stop)
```

### Historical modules and their Go destinations

| Area | Current files | Responsibility / rewrite destination |
|---|---|---|
| Application entry | `main.py`, `app/ui_main_window.py` | Qt startup, top-level tabs, tray, global controls, lifecycle; replace with Wails app bootstrap + Go services. |
| Main UI | `app/ui_pages_node_groups.py`, `app/ui_pages_base_nodes.py`, `app/ui_pages_chains.py`, `app/ui_pages_settings.py` | Base/Chain workspace and settings; replace with React routes/components. |
| Dialogs | `app/dialogs/chain_editor_dialog.py`, `node_edit_dialog.py`, `subscription_edit_dialog.py`, `subscription_manager_dialog.py` | Node, Chain, subscription editing; replace with typed React forms/dialogs. |
| Logs | `app/ui_pages_logs.py` | Runtime log buffer/view; replace with Go event stream + React log viewer. |
| UI utilities | `app/ui_kit/theme.py`, `app/ui_kit/feedback.py` | Qt theme and banner feedback; replace with shadcn tokens/components and toast/banner patterns. |
| Models | `models/app_state.py`, `node.py`, `subscription.py`, `chain.py`, `port_mapping.py` | Domain state and JSON serialization; redesign as explicit Go domain types and versioned persistence. |
| Subscription | `app/workers/subscription_update_worker.py`, `parsers/subscription_fetcher.py` | Async fetch, detect format, parse, update source nodes; replace with cancellable Go jobs and progress events. |
| Parsers | `parsers/uri_parsers.py`, `v2rayn_parser.py`, `clash_yaml_parser.py` | Share links, v2rayN text and Clash YAML; port with fixture-driven parity tests. |
| Core adapters | `core/core_adapter_base.py`, `singbox_adapter.py`, `xray_adapter.py`, `mihomo_adapter.py` | Config generation and check/start commands; port to Go adapter interface with golden config tests. |
| Process | `core/process_runner.py` | Start/stop, child process logs, Xray asset environment; replace with Go `os/exec`, process groups, cancellation and structured events. |
| OS integration | `utils/autorun.py`, `MainWindow` tray/admin methods | Login startup, tray, privilege checks; isolate behind platform interfaces in Go. |

### Current product contract

- Two top-level areas: **Node Groups** (Base and Chain subtabs) and **Settings**.
- One selected Base Node is exposed through one shared local proxy port.
- Each saved Chain has its own local port. With N chains, proxy listeners are Base + N Chain listeners.
- TUN is not a proxy port. Exactly one TUN target is selected: either a Base Node or a complete ordered Chain. A Chain binding must preserve every hop.
- The current core adapters are sing-box, Xray and Mihomo. The core executable performs the actual networking; ChainPort generates config and manages the process.
- Subscription sources currently support `auto`, v2rayN text/share links and Clash YAML. This is not a direct integration with Clash Verge's local profile database.

## 3. Historical UI requests 1–4: implementation checklist

These were the original Python UI requests. Their Go/Wails equivalents are now in the active implementation:

1. **Chain Create/Edit local port:** `ChainEditorDialog` has a `Local Port` spinbox. Create allocates the next available port; Edit loads the current port and saves a changed port to that Chain's existing `PortMapping`. The shared Base port and other Chain ports are excluded from valid choices. Automated coverage verifies the edited mapping changes without changing another Chain's port.
2. **Start does not open Logs:** successful manual Start no longer calls the log dialog/tab. Logs remain available only when the user presses the Logs control. Failure details are buffered and the UI tells the user to open Logs; failure must not force the Logs window open either.
3. **Base heading one row:** `Base Nodes`, active Base Node label and node search are in one horizontal heading row.
4. **Chain heading one row:** `Chain Nodes`, route summary and Create button are in one horizontal heading row.

The screenshots supplied for these requests show an older running GUI state. Restart the Go/Wails application after rebuilding to see code changes.

## 4. Deprecated, stale and misleading repository material

This section distinguishes confirmed dead/stale items from features that are merely candidates for redesign. Do not delete a feature solely because its name looks old.

### Confirmed stale documentation

| File | Finding | Action |
|---|---|---|
| `AGENTS.md` | Its UI inventory still describes Home, Subscriptions, Nodes, Routing and Ports pages and six top-level tabs. Those files are not the active UI. | Update to the actual two-tab architecture and current files. |
| `findings.md` | Refers to old dashboard/routing/subscriptions/ports modules and `utils/pattern_rename.py`; it is a historical audit, not a description of the current tree. | Mark as archived or replace with dated findings. |
| `graphify_ux_audit.md` | Describes deleted pages, duplicate dashboard actions, and style conflicts from an earlier UI generation. | Mark as historical; do not use it as a current cleanup checklist. |
| `progress.md`, `TASKS.md`, `task_plan.md` | Contain milestones for the previous page architecture and earlier project phases. | Retain history if useful, but add a current handover pointer and archive obsolete tasks. |
| `tests/test_chain_building.py` | Several tests manually reproduce a simplified `detour` algorithm instead of calling production adapters. | Keep as domain examples or replace with production adapter golden tests; do not treat its simulated config as adapter coverage. |

### Confirmed UI/runtime dead or ineffective elements

| Item | Evidence in current source | Recommendation |
|---|---|---|
| `MainWindow._open_tab()` | No production call sites found; tests replace it with a spy to assert that Start does not open Logs. | Remove after updating that test to spy on the Logs dialog directly; use explicit tab/dialog actions. |
| `MainWindow.lbl_context` | Constructed and assigned text, but not inserted into the global controls layout. | Remove or deliberately place it; do not leave invisible status state. |
| `LogsPage.refresh()` | Empty `pass`; no refresh work exists. | Remove from the page contract or implement only if logs gain filtering/state reload. |
| `ChainsPage._sync_actions()` | Only copies `app_state.chains` into `_row_chains`; `refresh()` already rebuilds the same list before calling it, and the selection callback also copies an unchanged list. | Remove the redundant helper and its selection callback during UI cleanup; keep `_row_chains` assignment in `refresh()`. |
| `PortMapping.remark` | Serialized/deserialized but no UI or runtime consumer found. | Decide whether a per-port label is a real feature; otherwise omit in the new schema and preserve it during legacy import if needed. |
| `Subscription.raw_text` | Populated after fetch but deliberately omitted from `to_dict()`. | Treat as transient fetch data; do not assume it survives restart. If raw subscription caching is required, design an explicit cache with retention limits. |

### UI fields with no demonstrated runtime behavior

The following subscription fields are displayed, editable and serialized, but repository search found no runtime consumer in the fetcher, parser or core adapters. `previous_proxy_remarks` and `next_proxy_remarks` are used only by a UI helper to select a profile name; they do not configure an actual upstream/downstream proxy. The other fields are retained conversion metadata or memo data, not active ChainPort runtime controls:

- `convert_target_type`
- `previous_proxy_remarks` / `next_proxy_remarks`
- `custom_config_core` / `custom_config_socks_port`
- `remarks_memo`

These are currently misleading controls unless there is an external workflow not represented in this repository. Before the rewrite, choose one of two explicit options per field: implement and test the behavior, or remove it from the UI and migrate/retain the stored value without pretending it is active. Do not silently discard existing user data.

`Node.raw_dict` is persisted and populated by parsers, but no production consumer reads it after parsing; current references are model serialization and parser tests. It is a retained raw-import snapshot, not an active runtime field. Decide whether to keep it as an opt-in import/debug attachment or remove it from the canonical Go `Node` schema after proving it is not required for protocol round-trip.

### Risky or duplicated data design

- `Node` stores both normalized fields and a `raw_dict` copy of imported source data. This can duplicate secrets and protocol metadata, and makes the canonical source of truth unclear. Keep raw source only as an optional, bounded diagnostic/import artifact; adapters must consume validated normalized fields.
- WireGuard private keys and node credentials are serialized in `state.json` as ordinary JSON. The Go rewrite should move secrets to OS credential storage where available and store secret references in the database; provide explicit export-with-secrets confirmation.
- `AppState` is a large mutable global state object used by UI, adapters and persistence. Replace it with domain services and explicit repository interfaces; avoid a single mutable application god-object.
- Each core adapter separately translates the same Node protocols. Add shared validation/capability metadata, while keeping each core's output translation explicit and independently tested.
- The current `ProcessRunner` accepts loosely typed `**kwargs` for `on_exit`, and process environment compatibility flags are applied to every core. The Go runner should use explicit options and per-core environment configuration.
- `subscription_update_worker.py` uses a worker thread, while UI owns timer scheduling and state reconciliation. Move scheduling, cancellation, deduplication and update result reconciliation into a subscription service; UI should only observe progress/results.

### Features that are active and must not be deleted as “legacy”

- Subscription CRUD, manual update, update-all, auto-update interval, User-Agent and custom HTTP headers.
- URI paste/manual node add, v2rayN text/base64 parser, Clash YAML parser.
- Node/Chain CRUD, hop reordering, local port collision checks, Base selection and full-Chain TUN binding.
- sing-box/Xray/Mihomo adapters and their independent validation commands.
- Runtime log capture, tray behavior, platform autorun and privilege checks (some require platform-specific test coverage).
- Import/export of existing profiles and backward-compatible `state.json` migration.

## 5. v2rayN reference: what to copy and what not to copy

The official v2rayN repository describes a cross-platform GUI client supporting Xray, sing-box and additional cores. Its wiki separates subscription behavior, core configuration, routing and pre-/landing-proxy concepts. Its subscription documentation lists VMess, Shadowsocks, SOCKS, VLESS, Trojan, Hysteria2, TUIC, WireGuard and AnyTLS, plus standard and v2rayN-specific subscription formats.

### Behaviors to adopt

1. **Subscription Group Manager:** named sources, URL, enabled state, interval, User-Agent, HTTP headers, ordering, manual update, update-all, status, node count, last update, per-source errors and per-source filtering.
2. **Node table:** fast filter, source tabs, stable identity, clear protocol/host/port/TLS/transport/status columns, context actions, ping/latency and speed test where actually implemented.
3. **Core-aware validation:** show whether a profile is supported by the selected core before generating config; report unsupported fields rather than silently dropping them.
4. **Pre-/landing proxy semantics:** chain hop order must be defined by traffic flow (entry/first proxy to exit/last proxy) and reflected identically in UI, config generation, logs and docs.
5. **Config lifecycle:** generate, validate, start, stop, restart, capture logs, and expose actionable failures as separate states.
6. **Import fidelity:** retain original URI/source payload where necessary for round-trip, but normalize into a typed canonical model and keep credentials out of diagnostic logs.

### Do not clone v2rayN internals blindly

ChainPort is a route/chain manager, not a full clone of every v2rayN feature. Do not add system proxy mode, routing-rule editor, policy groups, subscription conversion service or custom core config templates unless explicitly required. Keep the current product's differentiator: reusable ordered Chains, one local listener per Chain, one shared Base listener and one independent TUN binding to either a Base Node or a complete Chain.

### Current protocol gap

The current `Node` model and Clash map explicitly cover VMess, VLESS, Trojan, Shadowsocks, WireGuard, SOCKS5 and HTTP. The URI parser handles VMess, VLESS, Trojan, SS, SOCKS5 and HTTP(S) URI schemes. v2rayN's current subscription wiki also lists Hysteria2, TUIC and AnyTLS. Those are not first-class node types in this repository and should be a deliberate feature decision in the Go schema and adapter capability matrix.

## 6. Target architecture

```text
React + TypeScript + shadcn/ui (Vite)
  | generated Wails bindings / typed events
Wails v3 desktop shell
  |
Go application services
  +-- Node / Subscription / Chain / Port / TUN domain
  +-- Subscription fetch + format parsers
  +-- Core config adapters (sing-box / Xray / optional Mihomo)
  +-- Core process supervisor + logs + diagnostics
  +-- Persistence + legacy JSON import/export
  +-- OS integration (TUN privilege, tray, autorun, keyring)
  |
External core binaries (sing-box / Xray / Mihomo)
```

### Proposed repository layout

```text
cmd/chainport/main.go
internal/app/                 # Wails application construction and service registration
internal/domain/              # Node, Subscription, Chain, PortBinding, TunBinding, validation
internal/service/             # use cases: nodes, subscriptions, chains, runtime, settings
internal/store/               # SQLite repositories, migrations, JSON importer/exporter
internal/subscription/        # HTTP fetcher, format detection, URI/v2rayN/Clash parsers
internal/core/                # Adapter interface, config generation, validation, capability matrix
internal/process/             # child process supervisor, cancellation, log/event fanout
internal/platform/            # TUN/privilege, autorun, tray, keyring, proxy integration
internal/diagnostics/         # connectivity tests, DNS/TLS timing, redacted support bundle
frontend/src/                 # React + TypeScript + Vite
frontend/src/components/ui/   # shadcn-owned components
frontend/src/features/        # nodes, subscriptions, chains, settings, runtime/logs
frontend/src/bindings/        # generated Wails Go bindings; never hand-edit
frontend/src/lib/             # typed API wrappers, schemas, utilities
docs/                         # architecture, migration, test plan, runbooks
```

### Go service boundaries

Expose user-level operations, not low-level mutable structs:

- `NodeService`: list/filter, add/import, edit, remove, set active Base Node, bind TUN to Base Node.
- `SubscriptionService`: create/edit/delete, update one/all, update progress and per-source result/error events.
- `ChainService`: list/create/edit/remove, validate hop references, reorder hops, set local port, bind TUN to entire Chain.
- `RuntimeService`: preflight, generate config, validate, start, stop, restart, get runtime status, tail logs.
- `SettingsService`: read/update settings and core executable paths.
- `ImportExportService`: import legacy `state.json`, export profiles, report migration warnings.

## 2026-11-19 bug-fix investigation

- Subscription deletion now clears `ActiveNodeID` and a direct Base-Node TUN binding when the deleted feed owned that node. If a Chain still references a feed node, the node is detached from the feed and retained so the Chain remains valid. A regression test covers the active/TUN-bound deletion case.
- Runtime Logs now include ChainPort startup/configuration-validation diagnostics as well as child stdout/stderr. Core preflight output is retained (with credential redaction) instead of being discarded. Regression coverage verifies that application diagnostics are stored, emitted and redacted. Wails v3's official Events API requires matching event names and a frontend listener; this project uses `core:runtime` on both sides.
- Legacy import now also reads the older `auto_update_interval` subscription field when `update_interval` is absent, matching the Python model's backward-compatible `from_dict` behavior.
- The exact failing legacy file and exact Start error from the user's machine have not been supplied. Do not claim the import/run issue is fully resolved until that file (with secrets redacted) is tested against the importer and the migrated workspace is started with the same core version.
- The user's Start screenshot exposed `outbounds[2].plugin: unknown field "plugin"`. Reproducing the supplied C69 feed against the current bundled sing-box 1.14.4 showed a concrete generator bug: Go's `map[key]` returns a nil interface for an absent `plugin`, and comparing that interface to the empty string is true. The adapter consequently emitted a bogus `plugin` field for ordinary VMess/VLESS/Trojan/SS/SOCKS/HTTP nodes. Both sing-box and Mihomo adapters now use a nil-safe string accessor. A regression test asserts that non-plugin nodes do not receive a `plugin` key.
- Running the same real feed through sing-box 1.14.4 then exposed the next schema issue: since sing-box 1.14, domain-name proxy endpoints require `route.default_domain_resolver` or per-outbound `domain_resolver`. The generated route now sets `default_domain_resolver: "local_dns"`, using the configured bootstrap resolver for proxy-server hostnames. This follows the official Dial Fields and migration docs.
- The exact C69 URL was fetched with the application's configured default User-Agent (`v2rayN/7 ChainPort-Gateway`). The endpoint returned HTTP 200, `application/octet-stream`, a standard-base64 body of 23,824 bytes, and 85 links (4 VMess, 51 Shadowsocks, 30 VLESS). The Go refresh path parsed all 85 with zero parse errors. Generated sing-box configs for each of the 85 nodes passed the bundled sing-box 1.14.4 `check` command after the two adapter fixes. A request without that User-Agent returned a 5-byte `error` body; a generic Mozilla User-Agent returned HTTP 403. The app's existing v2rayN User-Agent default is therefore material and must not be removed.
- The screenshot's `already being refreshed` error came from the service rejecting overlapping refresh calls. Calls for the same subscription now coalesce: later callers wait for the in-flight refresh and receive its result rather than failing. A concurrency regression test asserts one HTTP request and identical successful workspace results. Subscription payload detection also accepts URL-safe/unpadded base64 and UTF-8 BOMs.
- Core start diagnostics now record the resolved executable path and its reported version, and surface the redacted core validation output in the Start error instead of only `exit status 1`. The user's selected binary path/version still needs to be checked in their environment; the tested bundled binary here is sing-box 1.14.4.
- Follow-up runtime output from the user's machine showed `DNS server not found: hosts`. An initial tag interpretation was incorrect and has been superseded by the actual sing-box 1.14.4 variant test recorded below: the working Python-compatible form uses the `hosts_dns` server tag for both `server` and `preferred_by`; `preferred_by: hosts` reproduces the user's startup error.
- The user's 2026-11-19 browser screenshot showed `PR_END_OF_FILE_ERROR` on `missav.live` and reported the same ISP-blocked-site regression for `laowang.vip`, which the Python app had previously handled. A direct source comparison found that Python `SingBoxAdapter.generate_config` adds a route-level `action: route-options, tls_record_fragment: true` rule (scoped to `protocol: ["tls"]` when sniffing is enabled), plus sniff and DNS-hijack front rules. Go had only set `tls.fragment` and `tls.record_fragment` on the proxy server's own TLS outbound; it did not fragment the destination TLS ClientHello inside the proxied traffic. This was the functional regression. Go now emits the same route-level rule/order as Python when `EnableFinalFragment` is on, and the same sniff/DNS-hijack rules for mixed inbound traffic.
- The same comparison found Go's DNS bootstrap had diverged from Python: it omitted `direct_dns`, used the bootstrap resolver directly for the DoH hostname, and used different `hosts`/`preferred_by` tags. Go now matches the Python three-stage setup (`local_dns` literal bootstrap, `direct_dns` resolved through `local_dns`, `hosts_dns` static DoH host mapping), routes DoH hostname resolution through `hosts_dns`, and uses `route.default_domain_resolver: {server: "direct_dns", strategy: ...}`. The bundled sing-box 1.14.4 runtime was used to test the tag combinations: `server=hosts_dns, preferred_by=hosts_dns` starts; `preferred_by=hosts` reproduces `DNS server not found: hosts`.
- Regression tests now assert the route-level TLS record-fragment rule, rule ordering, DNS hijack/sniff behavior, and Python-compatible DNS resolver chain. The generated two-hop Chain config with TLS fragmentation, final TLS record fragmentation, sniffing and QUIC blocking passed sing-box 1.14.4 `check` and a four-second real foreground `run` smoke test. This proves config acceptance and successful core initialization; it does not yet prove the user's ISP/site path works from their own network.

## 2026-11-19 UI parity pass

- Removed the separate Subscriptions sidebar destination. Subscription groups now live in the Node Groups/Base workspace as All, Customs (only when manual nodes exist), and one filter chip per subscription ID. Node source labels resolve from the subscription ID rather than displaying the opaque ID.
- Added a Subscription Groups dialog to the Base Nodes view, with Add Subscription, Refresh All, per-feed Update/Pause/Resume/Delete, node counts and update status. This follows the Python BaseNodesPage pattern (`group_tabs` plus `Subscriptions…`) and the supplied v2rayN screenshots.
- Base Node rows now show protocol, remarks, address, port, transport, TLS, subscription group and active state. Single-click selects the active Base Node; double-click opens Edit; right-click offers active selection, TUN binding, Edit, Remove and Create Node.
- Chain rows now support double-click Edit and right-click Edit, Bind TUN, Remove and Create Chain, matching the Python ChainsPage context-menu behavior.
- Added a backend `UpdateNode` operation that edits non-secret node metadata while preserving protocol and all credential-vault references. The editor deliberately does not reveal stored credentials. Regression test verifies protocol and vault secret references survive metadata edits.
- Moved Save Settings from the bottom of the long Settings page into the Settings heading at the top.
- Verification for this UI pass: Go tests and race tests, `go vet`, Wails TypeScript binding generation, frontend TypeScript/Vite production build, Wails Linux build and `git diff --check` passed.

Wails methods should return typed results/errors. Long-running work (subscription update, connectivity checks, core start/stop) should emit typed progress/state events instead of blocking a frontend call. Keep the backend authoritative; frontend state is a projection, not a second source of truth.

### Persistence decision

Use SQLite with explicit schema migrations for operational data (subscriptions, nodes, chains, port bindings, app settings). Preserve stable IDs and chain hop order. Import current `state.json` through a versioned importer; export to a documented portable JSON format. Store secrets through the OS keyring/credential vault and reference them by opaque key. If keyring is unavailable, provide an explicit encrypted-secret fallback rather than plain-text secret storage by default.

Do not store generated core config as the source of truth. Generate it from validated domain state into an application data/config directory, record the exact core version and config hash for diagnostics, and redact secrets in support bundles.

## 7. Frontend stack and UX rules

- **Wails v3:** native desktop window, menus, dialogs, events, tray and generated Go↔TypeScript bindings. Pin the stable `v3.1.0` CLI/module/runtime line as a starting baseline; do not use `nightly` in production builds. The official changelog lists `v3.1.0` as released on 2026-11-01; `v3.2.0-nightly` entries are previews, not the production baseline. Wails v3.1 removes the legacy GTK3/WebKit2GTK 4.1 build path, so Linux packaging must target GTK4 + WebKitGTK 6.0.
- **React + TypeScript + Vite:** single-page frontend with typed service calls and strict TypeScript.
- **pnpm:** pin `packageManager` to `pnpm@12.15.0` initially (matches the local environment checked on 2026-11-18) and commit `pnpm-lock.yaml`. A single frontend package does not need a workspace; add `pnpm-workspace.yaml` only if the project is split into multiple real packages.
- **shadcn/ui:** use its source-owned React components, not a runtime component service. Use the official Dialog, Context Menu, Table and Data Table patterns. For advanced node tables use TanStack Table; do not assume shadcn supplies a full grid implementation by itself.
- **Forms:** React Hook Form + Zod for node/subscription/chain validation; display backend validation errors in the corresponding field.
- **Server state:** TanStack Query for backend state, invalidation and mutation lifecycle. Keep local component state for ephemeral UI only; do not add Redux unless a real cross-feature state requirement appears.
- **Events:** typed Wails events for core logs, process state, subscription update progress and diagnostics. Unsubscribe listeners on component teardown.

### UI layout target

Keep the current two-tab product structure:

1. **Node Groups**
   - Base: source tabs (`ALL`, `Customs`, one per subscription), search/filter, node table, right-click Edit/Remove/Bind TUN, subscription manager.
   - Chain: one row per saved chain with name, ordered route, local port, hop count and TUN binding marker. Create/Edit includes editable local port. Right-click Edit/Remove/Bind TUN to entire chain.
2. **Settings**
   - Core selection and binary path.
   - DNS, TLS fragmentation, QUIC and IPv6 settings only where the selected core supports them.
   - Startup/autorun and platform controls.

Global toolbar: Logs, status/readiness, bound TUN target, TUN switch, Shared Base Port, one Start/Stop button. Start must not open the Logs window. Errors should show an inline banner and retain full details in the Logs view.

## 8. Core adapter and protocol strategy

Keep cores as external executables. Define a Go interface roughly equivalent to:

```go
type CoreAdapter interface {
    Name() string
    Capabilities() CoreCapabilities
    GenerateConfig(ctx context.Context, state RuntimeSnapshot) (GeneratedConfig, error)
    Validate(ctx context.Context, executable string, config GeneratedConfig) error
    StartArgs(config GeneratedConfig) []string
}
```

Requirements:

- Capability matrix per protocol, transport, TLS/Reality, UDP, TUN and fragmentation options. UI must not show a setting as effective when the selected core cannot implement it.
- Golden tests compare normalized generated config against known-good fixtures. Keep credentials redacted in snapshots; inject test secrets only in isolated tests.
- Core binary version detection and compatibility checks before config generation.
- Test every chain hop order and all TUN forms: Base single-hop and complete multi-hop Chain. TUN is a separate inbound/interface, not a proxy port.
- Preserve the proven route semantics: for `[A, B, C]`, traffic enters A then B then C; each later outbound must dial through its previous hop, and final route selection must point at C.
- sing-box and Xray are first-priority parity targets because they are the user's confirmed working references. Keep Mihomo optional and do not let it dictate the domain model.
- Add Hysteria2, TUIC and AnyTLS only after each is represented in the domain schema, parser fixtures, capability matrix and config tests for supported cores.

## 9. Migration phases and gates

### Phase 0 — Freeze and baseline the former Python application (completed historical phase)

- Complete the current UI changes 1–4 and verify all tests.
- Tag/record a known-good Python baseline and export a sanitized sample `state.json` fixture.
- Capture golden configs for Base single-hop, 2-hop and 3-hop routes, Base TUN, full-Chain TUN, DNS, fragment and QUIC behavior for sing-box and Xray.
- Record current core binary versions and checksums in test metadata, not as user secrets.

**Exit gate:** Python tests pass; generated config fixtures validate against pinned core binaries; manual Linux smoke test can start/stop and recover after unexpected process exit.

### Phase 1 — Go domain and compatibility importer

- Implement typed domain models and validation.
- Implement versioned SQLite migrations and `state.json` importer/exporter.
- Round-trip all existing fixture data, including subscriptions, source IDs, node IDs, chain order, ports, active Base and full-Chain TUN binding.
- Decide secret/keyring migration and provide a report for values that cannot be moved automatically.

**Exit gate:** legacy fixture imports with no silent loss; export/re-import preserves semantics; migration is idempotent.

### Phase 2 — Go parsers and subscription services

- Port URI parser and v2rayN/Clash feed parsing with existing test fixtures.
- Add cancellation, HTTP timeouts, size limits, redirect policy, per-source User-Agent/headers and safe error reporting.
- Implement stable node identity/deduplication and stale-node retention used by existing Chains/TUN.
- Add per-source update progress and Update All concurrency limits.

**Exit gate:** same input feeds produce equivalent normalized nodes and actionable errors; failed updates do not destroy last-known-good nodes.

### Phase 3 — Go core adapters and process supervisor

- Port sing-box and Xray config generation first; Mihomo after parity decision.
- Validate config with actual pinned binaries in CI where supported.
- Add child process group management, graceful shutdown, restart, stdout/stderr streaming, crash exit reason and startup timeout.
- Add route/TUN golden tests against sanitized historical fixtures, pinned core schemas and v2rayN reference configs.

**Exit gate:** Base, each Chain port and full-Chain TUN work in a Linux integration environment; Windows/macOS platform checks are separately tracked.

### Phase 4 — Wails shell and React UI

- Bootstrap Wails v3 stable app and generated bindings.
- Implement global toolbar, Base/Chain tabs, subscription manager, Chain editor with port, Settings and Logs.
- Add keyboard accessibility, context menus, responsive sizing, CJK font fallback and high-contrast theme.
- Add frontend component tests and end-to-end desktop smoke tests.

**Exit gate:** feature parity for everyday workflows; no hidden/duplicate controls; Start never opens Logs automatically.

### Phase 5 — Platform integration and release acceptance

- Linux TUN/permissions, GTK/WebKit packaging, autorun and tray.
- Windows UAC, WebView2 packaging, startup registration and process cleanup.
- macOS launch agent, WebKit and TUN privilege strategy.
- Keep the legacy `state.json` importer and document recovery/rollback. The former Python source is preserved in the backup branch, not shipped in the active tree.
- Complete signed packaging and install/upgrade/uninstall validation on supported operating systems.

**Exit gate:** install/upgrade/uninstall, state import, start/stop, crash recovery, TUN and subscription update tests on each supported OS.

## 10. Testing strategy

| Layer | Required tests |
|---|---|
| Domain | ID stability, validation, chain ordering, full-chain TUN vs Base-node TUN, port collisions, stale node references. |
| Persistence | SQLite migrations, JSON import/export, idempotence, secret references, crash-safe writes. |
| Parsers | Golden URI/v2rayN/Clash fixtures, malformed entries, partial success, unknown protocol behavior. |
| Subscription | timeout, cancellation, HTTP error, invalid YAML, duplicate nodes, update rollback, update-all concurrency. |
| Core adapters | golden config fixtures, core `check`/`-test`, per-core capability checks, DNS/TLS/QUIC rules, chain hop order. |
| Process | start/stop, startup timeout, early exit, log fanout, process group cleanup, restart and binary missing. |
| TUN | privileged integration tests for Base node and full multi-hop Chain; no config-only test should be called an end-to-end TUN test. |
| Frontend | component tests, validation forms, context menus, event subscription cleanup, Start does not open Logs. |
| Desktop E2E | Windows, Linux and macOS install/run/import/update/TUN flows. |

## 11. Risks and decisions still open

1. **Wails Linux runtime dependencies:** the stable desktop contract depends on GTK4 + WebKitGTK 6.0 by default. Confirm the target distro baseline and packaging before choosing it as the only desktop shell.
2. **TUN implementation:** Wails does not provide proxy TUN itself. Continue delegating packet handling to sing-box/Xray/Mihomo and implement only lifecycle/privilege/OS integration in Go.
3. **Core capability mismatch:** one generic Node model can accidentally imply that every core supports every protocol/option. Make capabilities explicit and validate before launch.
4. **Secrets:** existing JSON state may contain credentials and WireGuard private keys. Migration must never log or export secrets silently.
5. **v2rayN feature breadth:** its protocol list is broader than the current ChainPort model. Decide which new protocols are product requirements, not automatic scope creep.
6. **Clash Verge:** current project parses Clash YAML feeds; this is not equivalent to importing Clash Verge's local profile database. Treat direct profile integration as a separate feature with a documented file/API contract.
7. **Platform feature parity:** tray, autorun, UAC, Linux capabilities and macOS TUN permissions differ. Keep platform-specific code behind Go interfaces and test each OS.
8. **Release compatibility:** pin exact Go/Wails/pnpm/Node versions and core versions for reproducible builds; update deliberately after CI passes.

## 12. Official references checked on 2026-11-18

- Wails v3 technical overview: https://v3.wails.io/contributing/overview/
- Wails v3 stable status and desktop compatibility: https://wails.io/status/
- Wails v3 releases and version pinning: https://github.com/wailsapp/wails/releases
- Wails v3 changelog (v3.1.0 stable release and later nightly previews): https://wails.io/changelog/
- Wails v3 Linux packaging requirements: https://v3.wails.io/guides/build/linux/
- Wails v3 binding system: https://v3.wails.io/contributing/binding-system/
- Wails v3 first app / generated bindings: https://v3.wails.io/quick-start/first-app/
- pnpm installation and supported versions: https://pnpm.io/installation/
- pnpm workspace and shared lockfile behavior: https://pnpm.io/workspaces/
- shadcn/ui manual installation: https://ui.shadcn.com/docs/installation/manual
- shadcn/ui Vite + React installation: https://ui.shadcn.com/docs/installation/vite
- shadcn/ui Context Menu: https://ui.shadcn.com/docs/components/base/context-menu
- shadcn/ui Dialog: https://ui.shadcn.com/docs/components/base/dialog
- shadcn/ui Data Table / TanStack Table patterns: https://ui.shadcn.com/docs/components/base/data-table
- v2rayN repository and supported desktop platforms: https://github.com/2dust/v2rayN
- v2rayN subscription format/protocol documentation: https://github.com/2dust/v2rayN/wiki/Description-of-subscription
- v2rayN UI and chain ordering documentation: https://github.com/2dust/v2rayN/wiki/Description-of-some-ui
- v2rayN FAQ and config-generation flow: https://github.com/2dust/v2rayN/wiki/Faq

## 13. Current Go/Wails handover commands

Run from `go-wails3/`:

```bash
pnpm --dir frontend install --frozen-lockfile
wails3 generate bindings -i -ts
gofmt -w main.go internal
go test ./...
go test -race ./...
go vet ./...
pnpm --dir frontend run typecheck
pnpm --dir frontend run build
wails3 build
./bin/chainport
```

Before editing, read `AGENTS.md`, `README.md`, this plan and the relevant tests. Do not commit `state.json`, subscription URLs/tokens, generated core configs, logs, credentials or private keys. Update `graphify-out` with `graphify update .` after structural code changes if the graph is being maintained.

## 14. Remaining acceptance criteria for a production release

- [x] The four UI requests in section 3 were implemented and regression-tested in the Go/Wails application.
- [x] Go/Wails implementation is maintained on `rewrite/go-wails3`; legacy Python source was removed from the active tree.
- [ ] Sanitized golden state and core-config fixtures are checked in.
- [ ] Full-Chain TUN semantics are represented in the domain and all adapters.
- [ ] Subscription fields with no runtime consumer are either implemented or explicitly removed from the new UI/schema migration plan.
- [ ] Protocol scope is decided (current set vs Hysteria2/TUIC/AnyTLS additions).
- [x] OS credential-vault storage and the Go legacy JSON importer are implemented; additional real-world legacy fixtures remain a release test.
- [x] Wails stable version and Linux build/package task definitions are pinned.
- [x] Go service APIs and generated frontend bindings are implemented; keep bindings regenerated after exported API changes.

**Recommended next engineering action:** complete core-version golden tests, real traffic tests, privileged TUN lifecycle tests and Windows/macOS release packaging. Keep the legacy `state.json` importer covered by sanitized fixtures.

## 15. Verification snapshot and handover status (2026-11-18)

The following results are a historical verification snapshot of the former Python application before its source was removed. The Python test suite passed 108 tests immediately before cleanup; no Python runtime is required by the active application.

| Check | Result | Notes |
|---|---|---|
| `pytest tests/ -q` | **108 passed** after adding the failed-Start regression test | Final run on 2026-11-18. |
| `python -m compileall app core models parsers` | Passed | Compile check only; does not replace runtime smoke tests. |
| UI request 1 — Create/Edit port | Implemented in working tree | Create and Edit share collision checks against the Base port and other Chain mappings. |
| UI request 2 — Start does not open Logs | Implemented in working tree | Success and failure paths both have regression coverage. |
| UI requests 3–4 — one-row headings | Implemented in working tree | Geometry assertions cover Base and Chain heading rows at a 1400 px window width. Narrow-window behavior still needs manual review. |
| Full-Chain TUN | Implemented in working tree | State migration and sing-box/Xray/Mihomo adapter tests cover ordered multi-hop TUN routes. |

**Important checkout condition:** these changes were already present as uncommitted modifications when this review session opened. They are not represented by the current `HEAD` commit (`4b35386` at review time). Do not assume the checked-out commit alone contains requests 1–4. Preserve the dirty worktree, review its complete diff, run the tests, and create a deliberate baseline commit only after the owner approves the full change set.

**Manual verification still required:** restart the application from this working tree and inspect both headings at the intended minimum window size; create a Chain with a custom port; edit it to another free port; confirm the Base port and other Chain ports do not change; start successfully and confirm Logs stays closed; then open Logs manually and verify output is present. Test a failed start and confirm it also leaves Logs closed. Privileged TUN and each OS packaging path require separate integration testing.

**Version research correction:** Wails' status page still describes the v3.0.0 desktop compatibility contract, while the official changelog records v3.1.0 as released on 2026-11-01 and v3.2.0 nightly previews in November. Pin the stable v3.1.0 line and re-check the changelog immediately before implementation. pnpm 12 is the current line; the official compatibility table lists Node 24 as supported. The locally observed pnpm 12.15.0 / Node 24.22.1 pair is therefore a reasonable reproducible starting point, not a permanent compatibility guarantee.

## 16. Go rewrite implementation status (branch `rewrite/go-wails3`)

The active implementation lives under [`../go-wails3/`](../go-wails3/). The former Python application is no longer present in the active source tree. This branch is the Go/Wails product line; remaining release acceptance gaps are listed below.

### Implemented in the current rewrite branch

- Wails v3.1.0 app shell, React 18 + TypeScript strict mode + Vite 8, pnpm 12.15.0, Tailwind CSS v4, shadcn/ui Base UI components (Nova preset) and Lucide.
- Typed Go domain models for subscriptions, protocol nodes, ordered Chains, local port bindings, TUN target and settings. Credential values are represented as references, not plaintext fields.
- SQLite schema v1, transactional workspace writes, foreign-key and unique-port constraints, private database file permissions, and workspace read/write tests.
- OS credential vault integration through `github.com/go-keyring/keyring` (macOS Keychain, Windows Credential Manager, Linux Secret Service; unavailable stores fail closed without a plaintext fallback).
- Legacy `state.json` importer: subscription URLs, HTTP header values, node credentials, WireGuard private keys and runtime-used protocol `extra` metadata move into the OS credential vault. `extra` is gzip-compressed to reduce credential-vault item size and is resolved only in backend code. Debug-only `raw_dict` is deliberately omitted and reported as a warning. Legacy Chain wrapper nodes are expanded into ordered canonical Chain records. The original source file is never deleted or overwritten. Import refuses to run over a non-empty new workspace and rolls back secrets if validation fails.
- Legacy migration preserves ordered multi-hop Chains, full-Chain TUN selection, active Base Node, subscription metadata, node source association, port mappings and settings. Missing Chain ports are allocated with collision checks and reported as warnings.
- Go services for manual node creation, Base selection, Chain create/edit/delete, port allocation/collision validation, TUN target selection, subscription CRUD/refresh/update scheduling, stale-node reconciliation and core process lifecycle.
- URI and Clash YAML parsers for VMess, VLESS, Trojan, Shadowsocks, SOCKS5, HTTP and WireGuard, with credentials and source metadata stored in the OS vault.
- sing-box, Xray and Mihomo config generators with ordered chains, core-specific DNS, QUIC, TLS/REALITY, fragmentation and TUN config generation. Xray native TUN is rejected explicitly rather than silently ignored.
- Process supervisor with bounded/redacted logs, config validation command, Start/Stop and atomic private config writes; per-OS autorun and TUN privilege preflight.
- Frontend Base / Chain / subscription / Settings / Logs views, active-node selection, manual SOCKS5/HTTP entry, Chain editor with hop reordering and editable local port, TUN target configuration, subscription management and runtime controls.
- Wails-generated TypeScript bindings; production Linux binary builds successfully in the current Ubuntu 26.04 / GTK4 / WebKitGTK 6.0 environment.

### Current test/build snapshot

Run in `go-wails3/`:

```bash
go test ./...
go test -race ./...
go vet ./...
wails3 generate bindings -i -ts
cd frontend && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm run build
cd .. && wails3 build
```

The current verification pass reports `go test ./...`, `go test -race ./...`, `go vet ./...`, frontend TypeScript/production build and `wails3 build` all passing. Windows package cross-compilation passed with `GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go test -exec=/bin/true ./...`; internal packages cross-compiled for macOS arm64. The complete macOS Wails app was not cross-built because Wails requires CGO and no macOS toolchain is available on the Linux host. The compiled Linux binary remained running during an 8-second GUI smoke window and created its SQLite database with directory mode `0700` and database file mode `0600`. These checks do not establish live proxy connectivity, privileged TUN packet flow, or signed installer behavior.

### Not implemented or not yet certified — do not present as working features

- golden config parity against sanitized historical/v2rayN fixtures and validation against pinned live core binaries;
- live traffic tests through Base and each Chain, unexpected process-exit recovery, startup timeout, and core-version/capability detection;
- actual privileged TUN packet-flow tests and OS-specific interface cleanup (config generation and Linux privilege preflight are not end-to-end TUN support);
- tray integration and Windows/macOS app builds, signed installers and packaging validation;
- complete manual editors for VMess/VLESS/Trojan/Shadowsocks/WireGuard (manual creation currently supports SOCKS5 and HTTP; imported feed protocols are parsed);
- profile export, secret-safe support bundle, full import preview/dry-run and comprehensive error recovery.

shadcn/ui is initialized with the Base UI component library and Nova preset. Source components live in `frontend/src/components/ui`; review generated changes before adding or replacing components.

### Next implementation order

1. Capture sanitized legacy/v2rayN config goldens and run generated configs through the exact supported sing-box/Xray/Mihomo binary versions.
2. Fix adapter differences exposed by those fixtures; explicitly gate unsupported transport/protocol/core combinations rather than dropping fields.
3. Exercise real Base/Chain traffic, crash recovery, start timeout, DNS routing and UDP behavior on Linux; then add Windows/macOS CI and desktop smoke coverage.
4. Complete TUN privilege acquisition, interface lifecycle and packet-flow tests per OS; keep Xray TUN unsupported unless an external bridge is implemented.
5. Add export/import preview, secret-safe diagnostics, complete protocol editors, tray integration and signed packaging.

The legacy source snapshot is retained on `backup/main-before-go-wails3-20261119`. The active Go/Wails branch can be fast-forwarded to `main` after final checks; do not rewrite the backup branch.

## 2026-11-19 local destination routing regression

- The user's browser test used `0.0.0.0:1234` and failed with `ERR_EMPTY_RESPONSE`; the report identified missing localhost/127.0.0.1 bypass. The Go sing-box generator previously placed private/loopback bypass only inside the TUN branch. With TUN disabled, the normal mixed inbound sent every destination to its configured Base/Chain outbound, including local services.
- sing-box now adds global local-destination DIRECT rules before per-inbound Chain routing: `domain_suffix: localhost`, explicit IPv4/IPv6 loopback and unspecified ranges, and `ip_is_private`. The rules apply with TUN on or off. TUN process-loop prevention remains a separate rule.
- Xray now adds `full:localhost` and explicit local/private CIDR DIRECT rules before listener Chain rules. Explicit CIDRs are used instead of `geoip:private` because the Go runner does not configure `XRAY_LOCATION_ASSET`; this avoids requiring a missing geoip.dat file.
- Mihomo listeners no longer use a fixed `proxy` field. Each listener uses a named `rule` sub-rule containing localhost/loopback/private DIRECT rules, optional QUIC rejection, and a final MATCH to that listener's selected Chain. This is required because a non-empty listener `proxy` forces that proxy and skips listener rule evaluation. Mihomo TUN rules use the same local bypass list.
- `0.0.0.0` is a wildcard bind address; clients should connect to local services via `127.0.0.1` or `localhost`. `0.0.0.0/8` is also DIRECT-routed for compatibility with clients that send wildcard-address URLs.
- Regression tests cover sing-box, Xray and Mihomo rule ordering and fallback. Config validation passed with installed sing-box 1.14.4, Xray 26.11.9 and Mihomo. Runtime HTTP tests through local proxy listeners returned HTTP 200 for IPv4 loopback and localhost in all three cores, wildcard IPv4 and IPv6 loopback in sing-box. Temporary test configs and servers were removed.
- Full handover and verification details: [`GO-WAILS3-IMPLEMENTATION-HANDOVER.md`](GO-WAILS3-IMPLEMENTATION-HANDOVER.md).

## 2026-11-19 UX follow-up

- The Go SOCKS5/HTTP node editor now retrieves username/password on demand from the OS credential vault and supports replacing/clearing them without persisting plaintext in Workspace or SQLite. Other protocols' secret fields remain protected.
- Custom node groups are stored in workspace preferences and assigned with `Node.GroupID`, independently of subscription `SourceID`. The Base view supports group creation, rename, deletion and assignment.
- Core executable selection now has a native Wails Browse dialog and validates the selected file (including executable permission on Unix).
- The Chain editor now uses two columns: searchable available Base Nodes and ordered Chain Hops, with Add, Remove, Move Up and Move Down. Hop order remains Entry-to-Exit and is submitted unchanged to the existing Chain service.
- See `GO-WAILS3-IMPLEMENTATION-HANDOVER.md` for exact behavior, credential lifecycle and verification commands.
