# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `f443fbb24fbcc06853de666a3737fbebe3064f1f`
- Last sync review: 2026-07-12
- Dirty upstream files and untracked directories were excluded from the review.
- Newer unreviewed upstream `main` observed: `2e6c8d4947488890ae6d7b86c295a780f76aa2ad`
  (includes swarm 0.2.1). Run `python3 scripts/check-upstream.py` to audit drift.

## Pending upstream review

Claude PR
[`#25`](https://github.com/gering/claude-plugins/pull/25) advances `swarm` to
0.3.0 with opt-in `--fix`, `--loop`, and deepest-effort review behavior. Its
committed branch head `3fdf817f576a44ef1a4553dfee5b6815a7dabe55` was inspected
on 2026-07-12, but it is not the tracked baseline and has not been imported.
Changes first observed while uncommitted were excluded until they became part
of that committed head. After the PR merges, review the resulting upstream
`main` commit before updating this ledger or
`.agents/upstream/claude-plugins.json`. The planned native mapping is tracked
in `tasks/port-swarm-p5.md` and `tasks/add-opus-to-swarm.md`.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | planned | planned | 2026-07-12 / `f443fbb24fbcc06853de666a3737fbebe3064f1f` | Read-only adoption audit will be native to this repository. | Both manifests validated; both local marketplaces registered in isolated homes. No workflow yet. |
| knowledge-system | 1.8.2 at `f443fbb24fbcc06853de666a3737fbebe3064f1f` | planned | planned | 2026-07-12 / `f443fbb24fbcc06853de666a3737fbebe3064f1f` | Native memories are local preference stores; versioned project knowledge remains canonical. | Both manifests validated; no skills imported. |
| work-system | 1.6.0 at `f443fbb24fbcc06853de666a3737fbebe3064f1f` | planned | planned | 2026-07-12 / `f443fbb24fbcc06853de666a3737fbebe3064f1f` | Launch/resume will use native Codex and Grok/herdr commands. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.2 at `f443fbb24fbcc06853de666a3737fbebe3064f1f` | planned | planned | 2026-07-12 / `f443fbb24fbcc06853de666a3737fbebe3064f1f` | Local review is separated from optional GitHub `@claude review`. | Both manifests validated; no workflow tests. |
| swarm | 0.2.0 at `f443fbb24fbcc06853de666a3737fbebe3064f1f`; PR #25 (0.3.0) pending | missing | missing | 2026-07-12 / `f443fbb24fbcc06853de666a3737fbebe3064f1f` | Evaluation deferred until core workflows are stable; P5 native mapping is planned but not imported. | Phase 1 deferral plus reviewed pending tasks; no runtime implementation. |

## Baseline limitations

- No plugin is currently advertised as installable for Codex or Grok.
- Fresh-session skill discovery has not been tested because Phase 2 skills do
  not exist yet.
- Grok native plugin commands and local marketplace registration were verified
  with Grok Build 0.2.93, but a real installed adapter session is still pending.
- Codex manifests and isolated local marketplace registration were verified
  with the current plugin validator and Codex CLI 0.144.1.
