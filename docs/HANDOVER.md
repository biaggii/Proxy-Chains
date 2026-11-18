# ChainPort Gateway — Developer Handover

**Last reviewed:** 2026-11-18
**Current branch:** `main`
**Review baseline commit:** `4b35386` (`fix: align Xray routing and fragmentation with v2rayN`)

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

The rewrite plan is the specification for Go domain/service boundaries and typed Wails APIs/events; SQLite migrations and legacy JSON import/export; subscription parser parity and protocol capability checks; core config golden tests and process supervision; frontend feature structure and shadcn-owned components; TUN, secrets, platform integration and staged rollout.

## Known cleanup candidates

The rewrite plan distinguishes confirmed dead/ineffective UI from active functionality. In particular, review `_open_tab`, the invisible `lbl_context`, the no-op `LogsPage.refresh`, the redundant `ChainsPage._sync_actions`, `PortMapping.remark`, subscription conversion metadata, and `Node.raw_dict`. Do not remove serialized fields or imported data until the migration behavior is specified.

Do not delete active subscription updates, custom HTTP headers/User-Agent, URI/v2rayN/Clash parsing, node/Chain CRUD, port collision checks, full-Chain TUN, core validation, log capture, tray/autorun, or profile import/export merely because they are not part of the first UI surface.

## Security and data handling

- Do not commit `state.json`, subscription URLs/tokens, generated core configs, logs, credentials or WireGuard private keys.
- Treat `Node.raw_dict` and legacy profile JSON as potentially secret-bearing data.
- New support bundles and logs must redact credentials, tokens and private keys.
- Keep explicit user confirmation for exports that include secrets.

## Suggested next steps

1. Re-run the verification commands and complete the manual UI checklist in the rewrite plan.
2. Review and approve the current uncommitted diff; create a clean, tagged Python baseline.
3. Capture sanitized legacy state fixtures and core config goldens.
4. Finalize protocol scope, secret migration and Linux minimum distribution.
5. Start the Go domain/importer and tests before building the Wails frontend.
