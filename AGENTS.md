# AGENTS.md — ChainPort Gateway Developer Guide

## Project status

The active application is Go + Wails v3 + React + TypeScript. The former Python/PySide6 implementation has been removed. Do not reintroduce Python runtime dependencies or duplicate the application in another language without an explicit product decision.

The Go application retains a compatibility importer for existing legacy `state.json` workspaces. This importer is the only active legacy-Python compatibility boundary; it must not require a Python runtime.

## Product model

```text
Subscription / share URI / Clash YAML
    -> Base Nodes
    -> ordered Chain (entry to exit)
    -> local port binding
    -> external sing-box / Xray / Mihomo process
```

A selected Base Node uses one shared local listener. Each saved Chain has one local listener. TUN targets exactly one Base Node or one complete ordered Chain; it does not create another local proxy port.

## Architecture

All application source lives under `go-wails3/`.

| Path | Responsibility |
|---|---|
| `main.go` | Wails application bootstrap, window, tray and application lifecycle |
| `internal/domain` | Workspace, node, subscription, Chain, TUN and settings models; invariants |
| `internal/store` | SQLite persistence and schema |
| `internal/service` | Workspace/node/group/Chain/subscription operations, scheduler and core lifecycle |
| `internal/security` | OS credential vault and protected metadata |
| `internal/parser` | Share URI and Clash YAML parsing |
| `internal/core` | sing-box, Xray and Mihomo config generation |
| `internal/runtime` | Child-process supervision, bounded/redacted logs and private config writes |
| `internal/migration` | Legacy `state.json` import; no Python runtime dependency |
| `internal/autostart` | Per-user OS startup registration |
| `internal/tun` | Platform-specific TUN privilege preflight |
| `frontend/src` | Node Groups, Base, Chain, subscriptions, Settings and Logs UI |
| `frontend/bindings` | Generated Wails TypeScript bindings; never hand-edit |

Keep dependency direction explicit: domain has no application-layer dependencies; store/security are infrastructure; services orchestrate domain and infrastructure; adapters consume resolved domain data; frontend calls exported Wails service APIs.

## Core invariants

- Preserve Chain hop order exactly: entry -> intermediate hops -> exit.
- Every Chain has one unique local listener port; do not collide with the Base listener or another Chain.
- A Chain TUN binding targets the whole Chain, not its final hop.
- Localhost, loopback and private-network bypass rules must precede the inbound-to-Chain fallback.
- DNS bootstrap must not resolve the remote DoH hostname through itself.
- Never put plaintext credentials in Workspace snapshots, SQLite, logs, fixtures or support bundles. Use opaque vault references.
- Do not log subscription URLs, authorization headers, passwords, UUIDs or private keys.
- Validate generated config with the selected real core binary; JSON/YAML serialization alone is not core validation.
- Config validation is not proof of live traffic or privileged TUN packet flow.

## Frontend and UI

Use English for all user-facing UI text, notifications and errors. Keep terminology consistent: Node Groups, Base, Chain, Settings, subscription source, port binding.

Use the installed shadcn/ui source-owned Base UI components. Do not add Radix primitives without an explicit migration decision. Keep Wails bindings generated:

```bash
wails3 generate bindings -i -ts
```

## Coding conventions

- Go: idiomatic names, small focused packages, explicit error handling, context propagation for I/O, and synchronization scoped to shared state.
- TypeScript: strict types; avoid `any`; clean up event subscriptions and listeners.
- Add regression tests for every bug fix, especially routing order, secret handling, import compatibility and process lifecycle.
- Do not silently ignore unsupported protocol/core combinations; return actionable errors.

## Verification

Run from `go-wails3/`:

```bash
gofmt -w main.go internal
go test ./...
go test -race ./...
go vet ./...
wails3 generate bindings -i -ts
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend run typecheck
pnpm --dir frontend run build
wails3 build
git diff --check
```

For Linux packaging, see `build/linux/Taskfile.yml`. Cross-compilation does not replace native platform packaging and runtime tests.

## Data safety and Git

Never commit workspace databases, legacy `state.json`, subscription URLs/tokens, core configs, logs, credentials or private keys. Preserve the legacy importer and test it with redacted fixtures.

Before changing code, inspect `git status --short --branch`, read `docs/HANDOVER.md` and the detailed implementation handover. Preserve unrelated worktree changes. Use small commits and review the complete diff before pushing or merging.

## Graphify

If `graphify-out/graph.json` exists, run `graphify query` for codebase navigation before broad source browsing. After structural code changes, run `graphify update .` to refresh the graph. Graph output is generated analysis, not application source.
