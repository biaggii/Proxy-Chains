# ChainPort Gateway
只要一機，可以同時開，多端口,連接多proxy主機，鏈式連接，多開神器，養號，刷單一個搞掂
vpn1 vpn2 vpn3 vpn4 -> 20001, 20003, 20004....　可同時連多個機場，影射出來多個端口。
多口socks5，加一口mixed
linux, windows, macos通用。　
```
git clone https://github.com/biaggii/Proxy-Chains.git
cd go-wails3
--liunx
wails3 task linux:build
./bin/chainport >/dev/null 2>&1 & disown
--windows
wails3 task windows:build
--macos
wails3 task macos:build
```
ChainPort Gateway is a cross-platform desktop control plane for importing proxy nodes, composing ordered multi-hop Chains, exposing local proxy listeners, and configuring one TUN route. The active implementation is **Go + Wails v3 + React + TypeScript + Vite + pnpm**.

The external sing-box, Xray or Mihomo process provides the proxy data plane.

## Product model

```text
Subscription / share URI / Clash YAML
                 |
                 v
             Base Nodes
                 |
          Create ordered Chain
                 |
                 v
          Local port binding
                 |
                 v
       sing-box / Xray / Mihomo
```

- Base Nodes represent individual proxy endpoints.
- A Chain is an ordered list of Base Node IDs, from entry to exit.
- Each Chain has one local mixed proxy listener; the selected Base Node has a separate shared listener.
- TUN is a separate route to one Base Node or one complete Chain.

## Technology

- Go and Wails v3
- React, TypeScript strict mode, Vite and pnpm
- Tailwind CSS v4 and source-owned shadcn/ui Base UI components
- SQLite persistence and OS credential vault integration
- External sing-box, Xray and Mihomo binaries

## Linux prerequisites

Install Go, Node.js 24, pnpm 12, Wails v3 tooling, GTK4 and WebKitGTK 6.0 development/runtime packages for your distribution. See the [Wails Linux build guide](https://v3.wails.io/guides/build/linux/).

## Build from source

Run from the repository root:

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
```

The Linux executable is generated at:

```text
go-wails3/bin/chainport
```

Run it with:

```bash
./go-wails3/bin/chainport
```

Linux packaging tasks are defined in `go-wails3/build/linux/Taskfile.yml`. For example:

```bash
wails3 task linux:create:appimage
wails3 task linux:create:deb
wails3 task linux:create:rpm
```

## Data and migration

The application stores its current workspace in SQLite under the user's OS configuration directory. Credentials are stored in the OS credential vault; SQLite stores opaque secret references.

The Go application retains a one-way importer for legacy `state.json` workspaces. The former Python/PySide6 source, dependencies and test suite have been removed from the active repository. No Python runtime is required to build or run ChainPort.

Do not commit state databases, legacy state files, subscription URLs, authorization headers, proxy credentials, private keys, generated core configurations or runtime logs.

## Current release boundary

Go unit/race tests, vet, frontend production build and Linux Wails build are part of the verification workflow. These checks do not certify live external-site connectivity or privileged TUN packet flow. Xray native TUN is rejected explicitly; sing-box and Mihomo generate native TUN configurations. Windows/macOS packaging/signing and some platform-specific lifecycle behavior still require release acceptance testing.

## Developer documentation

- [Current handover](docs/HANDOVER.md)
- [Detailed Go/Wails implementation handover](docs/GO-WAILS3-IMPLEMENTATION-HANDOVER.md)
- [Rewrite architecture and historical assessment](docs/GO-WAILS3-REWRITE-PLAN.md)
- [Go application README](go-wails3/README.md)

MIT License.
