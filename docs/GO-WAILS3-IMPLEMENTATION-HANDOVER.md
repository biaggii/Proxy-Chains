# ChainPort Gateway — Go/Wails 3 Implementation Handover

**Last updated:** 2026-11-19
**Working branch:** `rewrite/go-wails3`
**Implementation path:** `go-wails3/`
**Reference implementation:** Python/PySide6 at the repository root

This document records the Go rewrite work and the user-reported regressions fixed during implementation. It is intended as the starting point for another developer. It does not claim that the Go rewrite has reached full production parity with the Python application.

## 1. Product boundary and status

ChainPort is the control plane. It parses node and subscription data, stores workspace state and secret references, generates core configuration, and supervises external proxy-core processes. sing-box, Xray and Mihomo perform the proxy data plane.

The Go/Wails application is a parallel rewrite. The Python application remains the reference implementation until migration, platform, TUN and real-traffic acceptance gates are complete. Do not remove or replace the Python application as part of routine Go work.

## 2. Technology and repository layout

- Go backend and Wails v3.1.0 desktop runtime.
- React, TypeScript strict mode, Vite 8 and pnpm 12.15.0.
- Tailwind CSS v4 and source-owned shadcn/ui components using the Base UI component library.
- SQLite via database/sql and modernc.org/sqlite.
- OS credential vault integration; workspace records contain opaque secret references, not plaintext credentials.
- External core executables: sing-box, Xray and Mihomo.

Main directories:

| Path | Responsibility |
|---|---|
| `internal/domain` | Workspace, node, subscription, Chain, TUN and settings models; invariant validation |
| `internal/store` | SQLite persistence and schema |
| `internal/service` | Workspace CRUD, node/Chain operations, subscription lifecycle, scheduler and core lifecycle |
| `internal/security` | OS secret-store abstraction and metadata protection |
| `internal/parser` | VMess/VLESS/Trojan/Shadowsocks/SOCKS/HTTP links and Clash YAML |
| `internal/migration` | Legacy Python state.json import |
| `internal/core` | sing-box, Xray and Mihomo config adapters |
| `internal/runtime` | Child-process supervision, runtime state, bounded logs and redaction |
| `internal/tun` | Platform-specific TUN privilege preflight |
| `internal/autostart` | Per-user OS startup registration |
| `frontend/src` | Node Groups, Chain, subscription manager, Settings and runtime UI |

Wails bindings in frontend/bindings are generated. Never edit them by hand. Regenerate them after exported Go method/model changes.

## 3. Build and verification commands

Run from go-wails3/:

```bash
gofmt -w main.go internal
go test ./...
go test -race ./...
go vet ./...
wails3 generate bindings -i -ts
npm --prefix frontend run build
wails3 build
git diff --check
```

The Linux task entry point is also available:

```bash
wails3 task linux:build
./bin/chainport
```

The frontend package manager is pnpm. Use the committed lockfile and `pnpm install --frozen-lockfile` for clean installs. Do not commit bin/, build/, frontend/node_modules/, frontend/dist/, .task/, *.tsbuildinfo, generated core configs, logs, databases, subscription URLs or credentials.

## 4. Implemented user workflows

### Node Groups and subscriptions

- One Node Groups sidebar destination contains Base and Chain views.
- Base Nodes has All, Customs (only when manual nodes exist), and one group per subscription ID.
- Group membership is determined by Node.SourceID, not by comparing display names.
- Base Node table columns: protocol, remarks/name, address, port, transport, TLS, subscription group and active state.
- Single click selects the active Base Node. Double click opens Edit. Right click offers active selection, TUN binding, Edit, Remove and Create Node.
- Subscriptions… opens the Subscription Groups manager. It provides Add Subscription, Refresh All, per-feed Update, Pause/Resume and Delete, with node counts, last update and status.
- Chain rows support double-click Edit and right-click Edit, Bind TUN, Remove and Create Chain.
- Settings Save is in the page heading at the top, not at the bottom of the long form.
- Chain Create/Edit exposes the local listen port. Updating a Chain's port updates its existing binding; other Chain ports and the shared Base port remain collision constraints.
- Start does not automatically open the Logs dialog. Logs remain available from the explicit toolbar control.

### Safe node editing

WorkspaceService.UpdateNode changes public node metadata and custom group assignment. It preserves protocol and all credential-vault references unless the SOCKS5/HTTP editor explicitly submits replacement values. The editor reads only username/password on demand from the OS credential vault; no plaintext credentials enter Workspace snapshots or SQLite. Other protocol credentials are not exposed by this editor. Manual creation currently supports SOCKS5 and HTTP; do not imply that it is a complete editor for all imported protocols.

## 5. User-reported bug fixes and root causes

### Legacy import and subscription deletion

- Legacy import supports both plural core_exe_paths and older singular core_exe_path when a path exists on the current OS. Unavailable or cross-platform paths are ignored with a migration warning.
- Legacy subscription import also accepts auto_update_interval when update_interval is absent.
- Deleting a subscription clears active-node and direct-node TUN references if the removed feed owned those nodes. A node still referenced by a Chain is detached from the feed and retained so the Chain remains valid.
- The exact historical user JSON file was not supplied for a byte-for-byte reproduction. Do not claim every legacy profile is proven until a redacted copy of that file is tested.

### Runtime logs and Core diagnostics

- Runtime Logs retain application startup diagnostics, core config-validation output, and child stdout/stderr.
- Start diagnostics include the resolved executable path and detected core version.
- Sensitive values are redacted. Do not log subscription URLs, authorization headers, passwords, UUIDs, private keys or secret-store contents.

### C69 subscription refresh

- The supplied C69 feed required the existing default User-Agent `v2rayN/7 ChainPort-Gateway`. Tests against the endpoint showed that omitting the User-Agent returned an HTTP 200 response containing only `error`, while a generic browser User-Agent was rejected. Do not remove the application's v2rayN-compatible default User-Agent.
- With that User-Agent the feed returned 85 share links: 4 VMess, 51 Shadowsocks and 30 VLESS. The Go parser parsed all 85 with zero parse errors in the recorded test.
- Same-subscription refresh requests now coalesce: concurrent manual/scheduled refreshes share one in-flight HTTP request and receive its result instead of returning already being refreshed.
- Base64URL, unpadded Base64 and UTF-8 BOM subscription payloads are handled.
- The live feed test was temporary. No subscription URL or node credential was added to fixtures or source control.

### sing-box config generation and startup

- A nil Go map lookup for absent Shadowsocks plugin metadata was incorrectly compared to an empty string. That emitted a bogus plugin field for ordinary VMess/VLESS/Trojan/Shadowsocks/SOCKS/HTTP nodes. Both sing-box and Mihomo adapters now use nil-safe string access; regression tests cover this.
- sing-box 1.14 requires a default or per-outbound domain resolver for domain-name proxy endpoints. The generated route uses default_domain_resolver with the configured bootstrap resolver chain.
- The user's runtime log reported DNS server not found: hosts. A runtime matrix against the bundled sing-box 1.14.4 binary showed that the working Python-compatible DNS rule uses hosts_dns for both server and preferred_by. The preferred_by hosts variant reproduces the reported failure. Keep the three-stage bootstrap (local_dns, direct_dns, hosts_dns) and DoH host mapping aligned with the Python adapter.

### ISP-blocked destination TLS handling

- The Python sing-box adapter has a route-level action route-options with tls_record_fragment true for destination TLS traffic. It is scoped to sniffed TLS when protocol sniffing is enabled.
- The earlier Go adapter only enabled fragmentation on the proxy outbound's own TLS connection. That does not fragment the browser's TLS ClientHello to the destination site inside the tunnel.
- Go now emits the route-level TLS record-fragment rule, plus the Python-compatible sniff and DNS-hijack rules. Regression tests verify rule content and ordering.
- Config validation and local runtime smoke tests do not prove that a particular ISP or destination site is reachable. The user must retest their own ISP path after rebuilding; do not claim live-site success from config tests alone.

### Localhost and private destination bypass — 2026-11-19

The latest user screenshot showed ERR_EMPTY_RESPONSE for `http://0.0.0.0:1234/` and reported that local addresses such as localhost and 127.0.0.1 were not bypassed. The root cause was that Go only had loopback/private bypass rules inside the sing-box TUN branch. With TUN disabled, normal local SOCKS/mixed listener rules sent all destinations to the selected Chain. Mihomo listeners also set a fixed proxy field, which causes Mihomo to route through that proxy directly and skip listener rule matching.

The fix applies to all three adapters:

- **sing-box:** global front route rules send localhost, 127.0.0.0/8, ::1/128, unspecified local ranges (0.0.0.0/8, ::/128) and ip_is_private destinations to DIRECT before the inbound-to-Chain rules. These rules work with normal local proxy listeners even when TUN is disabled. TUN process-loop prevention remains separate.
- **Xray:** explicit full:localhost and private/loopback CIDR rules route to DIRECT before per-inbound Chain rules. Explicit CIDRs are used instead of geoip:private, because the Go process runner does not currently configure an Xray geodata asset directory; this avoids a hidden geoip.dat dependency.
- **Mihomo:** each local listener now uses a named rule sub-rule rather than a fixed proxy field. The sub-rule bypasses localhost/loopback/private ranges, applies QUIC blocking when configured, then falls through to that listener's selected Chain. TUN rules include the same local bypass set before the final TUN Chain route.
- `0.0.0.0` is a wildcard bind address, not the recommended client destination. Open a local service with `http://127.0.0.1:1234/` or `http://localhost:1234/`. `0.0.0.0/8` is also routed DIRECT for compatibility with clients that send wildcard-address URLs.

The fix has regression tests for sing-box, Xray and Mihomo. Generated configurations passed the installed core validators: sing-box check, Xray run -test -c, and Mihomo -t. Actual local HTTP requests through the local proxy listener returned HTTP 200 for 127.0.0.1, localhost and 0.0.0.0 in sing-box, and 127.0.0.1 in Xray and Mihomo. An IPv6 ::1 request through sing-box also returned HTTP 200. These tests used temporary local HTTP servers and were cleaned up; they do not require or contain user subscription credentials.

## 6. Core routing invariants

- A saved Chain preserves ordered hops: [A, B, C] enters A, then B, then C. Each later outbound dials through its preceding hop.
- Each Chain has its own local listener port. The Base Node listener is separate.
- A direct local destination rule must be evaluated before the per-inbound Chain fallback. Do not place MATCH/inbound-to-Chain rules ahead of localhost/private bypass rules.
- Mihomo listeners must use rule with a sub-rule if local bypass is required. A non-empty listener proxy field directly forces that proxy and skips listener rule matching.
- TUN is separate from local proxy listeners. It binds to one Base Node or one complete Chain. Keep process-loop prevention and private/loopback bypass rules ahead of the final TUN Chain fallback.
- DNS bootstrap must not depend on the remote DoH hostname resolving through itself. Preserve the local_dns → direct_dns / hosts_dns bootstrap arrangement and route remote DNS through the selected Chain as designed.

## 7. Verification snapshot and remaining acceptance work

For the 2026-11-19 local-routing change, the following checks passed:

- `go test ./...`
- `go test -race ./...`
- `go vet ./...`
- `wails3 generate bindings -i -ts`
- `npm --prefix frontend run build`
- `wails3 build`
- `git diff --check`
- Installed core config checks: sing-box 1.14.4, Xray 26.11.9 and installed Mihomo.
- Local HTTP routing smoke tests through sing-box, Xray and Mihomo; IPv4 loopback, localhost, wildcard IPv4 and IPv6 loopback cases as described above.

Still not certified:

- Live ISP-specific access to missav.live, laowang.vip or other filtered destinations from the user's own network.
- Privileged native TUN packet flow and teardown on each target OS.
- Windows/macOS Wails packaging, signing, tray integration and full OS startup behavior.
- Full feature parity and migration acceptance against every historical Python state/profile format.
- End-to-end UDP and every protocol/transport combination across all cores.

## 8. Safe handover rules

1. Start with `git status --short`, `git diff --check` and the current branch. Preserve unrelated user changes.
2. Read `docs/GO-WAILS3-REWRITE-PLAN.md` and this file before changing adapters or migration behavior.
3. Add a regression test for each reported bug. Validate generated config with the actual supported core version; a successful JSON marshal alone is not a core validation.
4. Keep Python as the behavior reference and compare the corresponding Python adapter before changing Go routing semantics.
5. Do not add real subscription URLs, tokens, core configs, state databases, logs or credentials to Git.
6. Do not describe config validation as successful live proxy traffic. State exactly which layer was tested.

## 2026-11-19 UX follow-up

- The SOCKS5/HTTP node editor now loads username/password on demand through `GetNodeCredentials`, which reads only those values from the OS credential vault. Workspace snapshots and SQLite still contain only opaque references. When edited, changed values are written to new vault references before old references are deleted; empty submitted fields clear a credential, while null/omitted fields preserve it. Other protocols' credentials remain protected and are not exposed by this editor.
- `Workspace.Groups` stores user-created `NodeGroup` records in the workspace preferences payload; `Node.GroupID` assigns a node to one custom group. This is additive to `Node.SourceID`: subscription groups remain source-managed. The Base view shows All, ungrouped Customs, custom groups and subscription groups. Groups can be created, renamed and deleted; deleting a custom group clears node assignments but does not delete nodes or subscriptions.
- Core Engine executable path has a Browse button wired to Wails' native file picker. The selected path is checked for a regular file and, on Unix, executable permission, then placed in the Settings draft. Save Settings persists it; cancelling the picker leaves the draft unchanged.
- Chain Create/Edit now follows the Python two-column pattern: searchable Available Base Nodes on the left, ordered Chain Hops on the right, Add, Remove, Move Up and Move Down controls, plus name and local listener port fields. Double-clicking an available node also adds it. The right column order is the actual Entry-to-Exit order used by config generation.


## 2026-11-19 Node editor and navigation follow-up

- The shared `NodeEditorDialog` is used for both Add and Edit. Manual protocol choices are SOCKS5, HTTP and HTTPS. HTTPS is represented in the domain as `ProtocolHTTP` with `TLS.Enabled=true`, matching the existing parser representation; no separate protocol enum is introduced. Editing an existing SOCKS5/HTTP node can switch among these choices. Imported non-manual protocols remain fixed.
- Password input has show/hide and native Wails clipboard-copy controls (`@wailsio/runtime` Clipboard). Advanced options are grouped in a collapsible section: transport, SNI, TLS, per-node insecure verification and ALPN, transport path and host. These values are persisted through the existing node TLS/transport fields.
- The node dialog is viewport-bounded, vertically scrollable, initially centered and draggable by its title bar. Drag offsets are clamped so the dialog remains inside the window.
- Custom group chips have a right-click menu for Add Node to Group, Rename Group and Delete Group. Node rows expose Edit/Delete actions and retain their right-click menu. The sidebar is a compact icon-only rail with tooltips and accessible labels.
- HTTPS is configured in sing-box, Xray and Mihomo through the existing HTTP outbound TLS options; regression coverage asserts the generated TLS and SNI fields for all three adapters.
