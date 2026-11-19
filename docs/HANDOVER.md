# ChainPort Gateway — Developer Handover

**Last reviewed:** 2026-11-19
**Current branch:** `rewrite/go-wails3`
**Review baseline commit:** `4b35386` (`fix: align Xray routing and fragmentation with v2rayN`)

**Python handover commit:** `790a35b` (`feat: finish chain UI and rewrite handover`), pushed to `origin/main` on 2026-11-18. The parallel Go rewrite is being developed on `rewrite/go-wails3`; see [`../go-wails3/README.md`](../go-wails3/README.md) and section 16 of the rewrite plan.

## Start here

1. Read [`../AGENTS.md`](../AGENTS.md) for repository rules, architecture and test commands.
2. Read [`GO-WAILS3-REWRITE-PLAN.md`](GO-WAILS3-REWRITE-PLAN.md) for the current source audit, stale/dead UI inventory, v2rayN comparison, target architecture, migration phases and acceptance gates.
3. Read [`../README.md`](../README.md) for the current product behavior and user workflows.
4. Inspect `git status --short` and `git diff` before editing. The review checkout already contained uncommitted changes; do not reset or overwrite them.

## Current application

ChainPort Gateway is a Python + PySide6 desktop control plane. It parses subscription feeds and share links, models Base Nodes and ordered Chains, generates sing-box/Xray/Mihomo configurations, and manages those external core processes. The proxy data plane is not implemented by ChainPort itself.

Active top-level UI:

- **Node Groups / Base:** imported/manual nodes, subscription-group tabs, filtering, active Base selection and Base TUN binding.
- **Node Groups / Chain:** saved ordered multi-hop Chains, one local listener per Chain and whole-Chain TUN binding.
- **Settings:** core executable, DNS/network options, startup behavior and profile import/export.
- **Global toolbar:** Logs, runtime status, TUN binding/switch, shared Base port and Start/Stop.

There is one shared Base listener plus one listener per saved Chain. TUN is a separate route/interface and binds to either one Base Node or one complete ordered Chain.

## UI requests 1–4

The reviewed working tree contains implementations for all four requests:

1. Chain Create/Edit exposes a local port. The selected Chain's mapping is updated in place; the Base port and other Chain mappings are excluded from valid choices.
2. Start does not open the Logs dialog on success or failure. Logs remain available from the explicit Logs control.
3. Base Nodes title, active-node label and search field share one heading row.
4. Chain Nodes title, route summary and Create button share one heading row.

Automated tests cover port collision, editing a Chain port without changing another Chain, both heading rows, and Start not opening Logs. Restart the app to see the working-tree UI; an already-running process does not hot-reload Python source. Review the full diff before committing because these edits were uncommitted at handover time.

## Verification

Run from the repository root:

```bash
python -m pytest tests/ -q
python -m compileall -q app core models parsers utils tests
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; from models.app_state import AppState; from app.ui_main_window import MainWindow; app = QApplication([]); MainWindow(AppState('/tmp/chainport-smoke-state.json')); print('ok')"
```

These checks do not replace a manual start/stop test with the actual installed core binaries, privileged TUN test, or platform packaging test.

## Rewrite decision

The proposed next-generation stack is **Go + Wails v3 + React + TypeScript + Vite + pnpm + shadcn/ui**. Keep sing-box and Xray as external core processes; decide Mihomo's status explicitly. Build the new app alongside Python, import legacy `state.json`, and do not remove the Python implementation until parity and migration gates pass.

The rewrite plan is the specification for Go domain/service boundaries and typed Wails APIs/events; SQLite migrations and legacy JSON import; subscription parser parity and protocol capability checks; core config golden tests and process supervision; frontend feature structure and source-owned components; TUN, secrets, platform integration and staged rollout.

## Known cleanup candidates

The rewrite plan distinguishes confirmed dead/ineffective UI from active functionality. In particular, review `_open_tab`, the invisible `lbl_context`, the no-op `LogsPage.refresh`, the redundant `ChainsPage._sync_actions`, `PortMapping.remark`, subscription conversion metadata, and `Node.raw_dict`. Do not remove serialized fields or imported data until the migration behavior is specified.

Do not delete active subscription updates, custom HTTP headers/User-Agent, URI/v2rayN/Clash parsing, node/Chain CRUD, port collision checks, full-Chain TUN, core validation, log capture, tray/autorun, or profile import/export merely because they are not part of the first UI surface.

## Security and data handling

- Do not commit `state.json`, subscription URLs/tokens, generated core configs, logs, credentials or WireGuard private keys.
- Treat `Node.raw_dict` and legacy profile JSON as potentially secret-bearing data.
- New support bundles and logs must redact credentials, tokens and private keys.
- Keep explicit user confirmation for exports that include secrets.

## Go rewrite status — 2026-11-19

The parallel implementation under [`../go-wails3/`](../go-wails3/) now includes the typed domain, SQLite persistence, OS keyring, legacy importer, URI/Clash parsers, subscription refresh/scheduler, sing-box/Xray/Mihomo config generators, process supervisor, Linux TUN privilege preflight, per-OS autorun and the React Base/Chain/Subscriptions/Settings/Logs interface. The Python application remains the production reference; do not replace it or merge the preview as feature parity.

Verification on the current Linux host: `go test ./...`, `go test -race ./...`, `go vet ./...`, `wails3 generate bindings -i -ts`, frontend production build and `wails3 build` passed. Windows Go package cross-compilation passed; internal packages cross-compiled for macOS arm64. Full macOS Wails build, signed packages, live core validation/traffic and privileged TUN packet flow remain unverified. The Linux binary stayed running during an 8-second GUI smoke window; config directory/database permissions were `0700`/`0600`.

### 2026-11-19 user-reported regressions

- Legacy import now migrates both `core_exe_paths` and the older singular `core_exe_path` when the path exists on the current OS. Cross-platform or unavailable paths are ignored with a migration warning. It also supports the older subscription `auto_update_interval` field.
- Subscription deletion clears active-node and direct-node TUN references when those nodes are removed. Nodes still referenced by a Chain remain detached from the deleted feed.
- Runtime Logs now retain application startup errors and core config-validation output in addition to child stdout/stderr, with secret redaction.
- Regression tests added for these cases. `go test ./...`, `go test -race ./...`, `go vet ./...`, frontend build, binding generation and Wails Linux build passed after these changes.
- The user's exact failing historical JSON and the resulting core error have not yet been reproduced. Request a redacted copy plus selected core/version and exact error before calling legacy import/run fully fixed.
- The supplied Start screenshot was reproduced against the real C69 feed: a nil-interface comparison emitted a `plugin` key for ordinary nodes. Both sing-box and Mihomo adapters now omit absent plugin metadata. sing-box 1.14 also requires a default/per-outbound domain resolver for domain-name proxy servers; `route.default_domain_resolver: local_dns` is now generated.
- The C69 endpoint was tested using the app's default `v2rayN/7 ChainPort-Gateway` User-Agent: 85 links were returned and parsed (4 VMess, 51 Shadowsocks, 30 VLESS), zero parse errors; each of the 85 generated sing-box profiles passed the bundled sing-box 1.14.4 `check` command after the fixes. Without the v2rayN User-Agent the endpoint returned a 5-byte `error` response; a generic browser User-Agent returned HTTP 403.
- Concurrent manual/scheduled refreshes for the same subscription now share one in-flight request. Base64URL and BOM payload handling were added. Runtime diagnostics now include the actual executable path/version and validation output.
- The user's subsequent process log exposed a second-stage sing-box 1.14.4 DNS startup failure: `DNS server not found: hosts`. An initial tag interpretation was incorrect; a runtime matrix against sing-box 1.14.4 showed that the working Python-compatible form uses the `hosts_dns` server tag for both `server` and `preferred_by`. The `preferred_by: hosts` variant reproduces the user's startup error.
- The user's latest Firefox screenshot showed `PR_END_OF_FILE_ERROR` on `missav.live` and reported ISP-blocked `laowang.vip` access failing in Go although the Python implementation worked. Python source comparison identified the missing feature: its sing-box generator adds route-level `tls_record_fragment` for destination TLS traffic (and sniff/DNS-hijack rules); Go only fragmented the proxy outbound's own TLS connection. Go now emits the same route-level TLS record-fragment rule and rule ordering. DNS bootstrap was also brought back in line with Python (`local_dns` -> `direct_dns`, `hosts_dns` static mappings, DoH hostname resolved via `hosts_dns`, `default_domain_resolver` via `direct_dns`). Runtime test of sing-box 1.14.4 confirms `preferred_by=hosts_dns` is the working tag form; `preferred_by=hosts` reproduces the prior DNS startup error.
- Added tests for final TLS record fragmentation, sniffing/DNS hijack, QUIC rule order and DNS bootstrap. A representative two-hop Chain config with fragmentation enabled passed sing-box 1.14.4 `check` and a four-second real foreground run. Actual access to `missav.live`/`laowang.vip` from the user's ISP remains to be retested after they rebuild; the local smoke test is not a live-site connectivity claim.
- Latest verification after this pass: `go test ./...`, `go test -race ./...`, `go vet ./...`, frontend build and `wails3 build` passed. The C69 live endpoint test was temporary and removed; no subscription URL or node credentials were added to repository fixtures.

## Suggested next steps

1. Capture sanitized golden configs from the Python implementation and v2rayN for Base, 2-hop/3-hop Chains, DNS, fragmentation, QUIC and TUN.
2. Validate generated configurations using pinned sing-box, Xray and Mihomo binaries, then fix differences before claiming adapter parity.
3. Run real Base/Chain traffic, UDP, DNS, crash-recovery and startup-timeout tests; exercise privileged TUN packet flow and teardown on each OS.
4. Complete tray, Windows/macOS packaging/signing, export-with-secrets and secret-safe diagnostics.
5. Continue implementation and integration acceptance on the pushed `rewrite/go-wails3` branch; keep the Python baseline untouched.

## 2026-11-19 UI parity pass

The Go UI now has one Node Groups sidebar destination; Base Nodes has All/Customs/subscription-ID group chips and a Subscription Groups manager dialog. Base rows follow the v2rayN columns and support single-click active selection, double-click Edit and right-click actions. Chain rows support double-click and right-click Edit/Remove/Bind TUN/Create. Node editing changes public metadata only and keeps credential vault references hidden/preserved. Settings Save is now in the top page heading. Full Go/race/vet, bindings, frontend build, Wails Linux build and diff checks passed after this pass.

## Go/Wails 3 implementation handover — 2026-11-19

The full chronological implementation record, architecture map, build/test commands, user-reported root causes, adapter routing invariants, verification boundaries and remaining acceptance work are now in [`GO-WAILS3-IMPLEMENTATION-HANDOVER.md`](GO-WAILS3-IMPLEMENTATION-HANDOVER.md). Read that file before continuing work under `go-wails3/`.

Latest local-routing fix: all three Go core adapters now bypass localhost/loopback/private destinations before their per-listener Chain fallback. Mihomo listeners use named sub-rules instead of fixed proxy assignment. sing-box 1.14.4, Xray 26.11.9 and Mihomo config checks passed; local HTTP requests through each local proxy listener returned HTTP 200 for loopback targets. This does not certify ISP-blocked external-site reachability or privileged TUN traffic.
