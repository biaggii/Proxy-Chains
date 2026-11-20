# ChainPort Gateway

The active desktop application is implemented with Go, Wails v3, React and TypeScript. The former Python/PySide6 implementation has been removed from the active source tree. The Go application retains an importer for legacy `state.json` workspaces.

## Stack

- Go 1.27 and Wails v3.1.0
- React 18, TypeScript strict mode and Vite 8
- pnpm 12.15.0 (pinned in `frontend/package.json`)
- Tailwind CSS v4 and shadcn/ui source-owned Base UI components (Nova preset)
- SQLite through `database/sql` and the pure-Go `modernc.org/sqlite` driver

## Development

Run these commands from this directory:

```bash
go test ./...
go vet ./...
pnpm --dir frontend install --frozen-lockfile
wails3 generate bindings -i -ts
gofmt -w main.go internal
pnpm --dir frontend run typecheck
pnpm --dir frontend run build
wails3 dev
```

Wails uses `Taskfile.yml`; its package-manager default is pnpm. Generated Wails bindings live in `frontend/bindings/` and must be regenerated after exported service signatures or bound models change:

```bash
wails3 generate bindings -i -ts
```

Never edit generated bindings manually.

## Current implementation boundary

- `internal/domain`: typed workspace model, user-managed node groups and invariant validation.
- `internal/store`: SQLite schema v1, transactional workspace persistence.
- `internal/service`: workspace, node, custom-group, Chain and subscription CRUD; bounded HTTP refresh; stale-node reconciliation; scheduler; native core executable selection; core lifecycle.
- `internal/security`: OS keyring integration and compressed metadata encoding; no plaintext fallback.
- `internal/parser`: VMess, VLESS, Trojan, Shadowsocks, SOCKS/HTTP share links and Clash YAML parsing.
- `internal/core`: sing-box, Xray and Mihomo configuration generation, ordered outbound chains, DNS and TUN route construction.
- `internal/runtime`: core process supervisor, bounded/redacted logs and atomic private config writes.
- `internal/migration`: legacy `state.json` importer with vault migration and Chain-wrapper expansion.
- `internal/autostart` and `internal/tun`: per-OS startup registration and TUN privilege preflight.
- `frontend/src`: Base / Chain / custom node groups / subscriptions / Settings / runtime controls and log view.

This is the active implementation. It is not yet a fully certified cross-platform release: external ISP-filtered site access, privileged TUN packet flow/teardown, Windows/macOS packaging and signing, tray integration, core-version capability detection, and export-with-secrets remain incomplete. Xray native TUN is explicitly rejected; sing-box and Mihomo generate native TUN configurations. Do not interpret config validation as proof of live proxy or TUN behavior.

## Data safety

The database is created below the user's OS config directory with a private directory and file permissions. Node credentials in the new domain are secret references, not raw credential strings. The node editor retrieves SOCKS5/HTTP username/password values on demand from the OS credential vault; values are not included in Workspace snapshots or SQLite. Replacements are written to the vault before the old references are deleted. Do not add plaintext secrets to logs, support bundles, fixtures or committed JSON. Legacy import must resolve old plaintext credential fields through a SecretStore before any migrated workspace is persisted.

Custom Node Groups are separate from subscription source groups. A node can be assigned to one custom group from its editor; deleting a custom group clears its assignments but does not delete nodes or subscription records.

Settings > Core Engine > Core executable path includes a native Browse dialog. On Unix, selected files must have an executable permission bit. Chain Create/Edit uses a two-column available-node / ordered-hop builder; the right-hand list defines Entry-to-Exit order.

## Architecture and rollout

See [`../docs/GO-WAILS3-REWRITE-PLAN.md`](../docs/GO-WAILS3-REWRITE-PLAN.md) for the historical architecture assessment, [`../docs/HANDOVER.md`](../docs/HANDOVER.md) for the current handover, and [`../docs/GO-WAILS3-IMPLEMENTATION-HANDOVER.md`](../docs/GO-WAILS3-IMPLEMENTATION-HANDOVER.md) for implementation details. Legacy Python source is no longer part of this repository; preserve the Go `state.json` importer for existing users.

## Verification snapshot

Verified in the current Linux development environment:

```bash
gofmt -w main.go internal
go test ./...
go test -race ./...
go vet ./...
wails3 generate bindings -i -ts
npm --prefix frontend run build
wails3 build
```

All listed commands passed. Windows `GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go test -exec=/bin/true ./...` passed; the internal packages also cross-compiled for macOS arm64. A macOS Wails app build was not verified because Wails requires CGO and the Linux host has no macOS toolchain. The Linux binary remained running during an 8-second GUI smoke window. The application config directory and SQLite database were observed with modes `0700` and `0600`, respectively. These checks do not establish live proxy connectivity, real TUN packet flow, or release packaging parity.

The shared Node Add/Edit dialog supports SOCKS5, HTTP and HTTPS (HTTP + TLS), vault-backed credential editing, password reveal/copy, and collapsible transport/TLS options. Custom group chips and node rows support context-menu management; the sidebar is icon-only. See `../docs/GO-WAILS3-IMPLEMENTATION-HANDOVER.md` for implementation details.
