# Task Plan - Cross-Repo Improvement Study

> **ARCHIVED / COMPLETED:** This plan records the earlier 2026-04-28 repository study. The current source-verified rewrite assessment is [`docs/GO-WAILS3-REWRITE-PLAN.md`](docs/GO-WAILS3-REWRITE-PLAN.md).

## Goal
1. Build fresh graph-based view of current `Sing-chain` repo.
2. Compare architecture and UX patterns against `Refer Projects/clash-verge-rev` and `Refer Projects/v2rayn`.
3. Produce concrete improvement plan for this project, biased toward surgical, high-leverage changes.

## Phases
- [x] Phase 1: Restore prior planning context and repo state <!-- id: 0 -->
- [x] Phase 2: Refresh graph inputs for current repo <!-- id: 1 -->
- [x] Phase 3: Inspect reference repos and extract useful patterns <!-- id: 2 -->
- [x] Phase 4: Synthesize gaps, risks, and upgrade opportunities <!-- id: 3 -->
- [x] Phase 5: Deliver prioritized implementation roadmap <!-- id: 4 -->

## Constraints
- Keep recommendations traceable to this repo or reference repos.
- Favor simple changes over speculative platform rewrites.
- Do not refactor code until concrete improvement targets are verified.
- Use narrowed local corpus for graph work; exclude `Refer Projects` from graph input.
- Semantic subagent extraction unavailable under current tool policy; use AST-first graph pass and direct repo inspection.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Shell profile emits conda/PSReadLine noise | 1 | Ignore unless exit code fails |
