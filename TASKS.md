# ChainPort Gateway — Current Task Board

The former Python implementation task list is archived in Git history. The active application is under `go-wails3/`.

## Release acceptance still required

- [ ] Validate generated configurations against pinned sing-box, Xray and Mihomo binaries in CI.
- [ ] Add sanitized golden configuration fixtures for Base, multi-hop Chains, DNS, TLS fragmentation, QUIC and TUN.
- [ ] Run end-to-end Base/Chain TCP and UDP traffic tests.
- [ ] Verify DNS routing and local/private destination bypass across all cores.
- [ ] Complete privileged TUN packet-flow and teardown tests on Linux, Windows and macOS.
- [ ] Complete Windows/macOS Wails packaging, signing, tray and startup acceptance.
- [ ] Complete secret-safe export/support bundle workflows.
- [ ] Document upgrade/rollback and legacy workspace migration recovery.

## Verification commands

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
