# ChainPort Gateway

ChainPort Gateway is a desktop proxy-chain manager built with **Go, Wails v3, React and TypeScript**. It manages Base Nodes, ordered multi-hop Chains, subscription sources, local proxy listeners and a single TUN route. sing-box, Xray and Mihomo remain external proxy data planes.

## Features

- Independent Profiles, each with its own Nodes, Groups, Chains, subscriptions and settings.
- Configurable data-root directory containing all profile databases.
- Settings-only JSON import/export without credentials or machine-specific executable paths.
- Password-encrypted full-profile backups containing workspace data and OS-vault credentials.
- Legacy state.json importer. The former Python/PySide6 application and runtime dependencies have been removed; no Python installation is required.

## Technology

- Go and Wails v3
- React, TypeScript, Vite and pnpm
- Tailwind CSS v4 and shadcn/ui Base UI components
- SQLite persistence and OS credential vault integration
- External sing-box, Xray and Mihomo binaries

## Linux prerequisites

Install Go, Node.js 24, pnpm 12, Wails v3 tooling, GTK4 and WebKitGTK 6.0 development/runtime packages. See the [Wails Linux build guide](https://v3.wails.io/guides/build/linux/).

## Build from source

From the repository root:

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
wails3 task linux:build windows:build
./bin/chainport
```

The Linux executable is generated at go-wails3/bin/chainport. Linux packaging tasks are defined in go-wails3/build/linux/Taskfile.yml.

## Profiles and data

The default data root is below the user's OS configuration directory. The active profile uses the existing chainport.db path for upgrade compatibility; additional profiles have independent SQLite databases below profiles/. The profile index and active-profile selection are stored in the data root. A small location pointer in the OS configuration directory allows the data root to be moved without changing the application install path.

Settings > Profiles creates, renames, switches and deletes profiles. Settings > Data Location moves all profiles and data to an empty destination. The previous data directory is retained as a recovery copy; remove it manually only after verifying the new location.

## Import and export

- **Settings Only** exports portable application/core preferences as JSON. Machine-specific core executable paths and custom runtime output paths are omitted and retained locally on import.
- **Encrypted Profile Backup** includes the active workspace and its credentials. It uses AES-256-GCM with PBKDF2-HMAC-SHA256 key derivation. The password is required to restore the backup; ChainPort cannot recover a forgotten password.
- Legacy state.json import migrates old credentials into the OS credential vault.

Never commit workspace databases, subscription URLs, authorization headers, proxy credentials, private keys, generated core configurations or runtime logs.

## Release boundary

Go tests, race tests, vet, frontend production build and Linux Wails build are verification gates. They do not certify external-site connectivity or privileged TUN packet flow. Xray native TUN is explicitly rejected; sing-box and Mihomo generate native TUN configurations. Windows/macOS packaging, signing and platform lifecycle behavior still require release acceptance testing.

## Developer documentation

- Developer guide: AGENTS.md
- Current handover: docs/HANDOVER.md
- Detailed Go/Wails implementation handover: docs/GO-WAILS3-IMPLEMENTATION-HANDOVER.md
- Rewrite architecture and historical assessment: docs/GO-WAILS3-REWRITE-PLAN.md

MIT License.
