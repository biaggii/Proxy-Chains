# ChainPort Gateway — Developer Handover

**Updated:** 2026-11-19
**Active branch:** `main` (integrated from `rewrite/go-wails3`)
**Active application:** `go-wails3/`

## Current implementation

ChainPort is a Go/Wails v3 desktop control plane. React/TypeScript provides the UI; SQLite stores workspace state; the OS credential vault stores secrets; sing-box, Xray or Mihomo performs proxy traffic.

The active implementation includes:

- Base Nodes, custom groups and ordered multi-hop Chains.
- Subscription CRUD, HTTP refresh, automatic scheduling and stale-node reconciliation.
- Share URI and Clash YAML parsing.
- sing-box, Xray and Mihomo configuration generation.
- Core preflight, process Start/Stop, bounded logs and secret redaction.
- Legacy `state.json` import into the Go workspace and OS credential vault.
- Per-user startup registration and platform-specific TUN privilege preflight.

The former Python/PySide6 application and its runtime dependencies have been removed from the active repository. Its source is preserved on `backup/main-before-go-wails3-20261119` (baseline commit `790a35b`). The Python test suite passed 108 tests immediately before removal. Existing users can still import legacy `state.json`; no Python installation is required.

## Start here

1. Read [AGENTS.md](../AGENTS.md).
2. Read [GO-WAILS3-IMPLEMENTATION-HANDOVER.md](GO-WAILS3-IMPLEMENTATION-HANDOVER.md) for implementation details, known regressions and exact verification boundaries.
3. Read [GO-WAILS3-REWRITE-PLAN.md](GO-WAILS3-REWRITE-PLAN.md) for the historical architecture assessment and remaining acceptance plan.
4. Work under `go-wails3/`.

## Build and test

```bash
cd go-wails3
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

The Linux executable is `go-wails3/bin/chainport`. Linux package tasks are in `go-wails3/build/linux/Taskfile.yml`.

## Verification boundaries

Passing Go tests, config checks and desktop builds does not prove external-site connectivity, full UDP behavior, privileged TUN packet flow or release packaging parity. Xray native TUN is explicitly unsupported. Native TUN and OS lifecycle behavior still require platform integration tests. Windows/macOS packaging and signing, tray behavior and full release acceptance remain open.

## Git handover

Preserve the legacy `state.json` importer and sanitized migration fixtures. Never commit user state, subscription URLs, authorization headers, generated configs, logs, credentials or private keys. Before pushing or merging, inspect the full diff and rerun the verification commands.
