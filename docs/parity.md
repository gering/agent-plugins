# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `f443fbb24fbcc06853de666a3737fbebe3064f1f`
- Last sync review: 2026-07-12
- Dirty upstream files and untracked directories were excluded from the review.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | planned | planned | 2026-07-12 / `f443fbb` | Read-only adoption audit will be native to this repository. | Both manifests validated; both local marketplaces registered in isolated homes. No workflow yet. |
| knowledge-system | 1.8.2 at `f443fbb` | planned | planned | 2026-07-12 / `f443fbb` | Native memories are local preference stores; versioned project knowledge remains canonical. | Both manifests validated; no skills imported. |
| work-system | 1.6.0 at `f443fbb` | planned | planned | 2026-07-12 / `f443fbb` | Launch/resume will use native Codex and Grok/herdr commands. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.2 at `f443fbb` | planned | planned | 2026-07-12 / `f443fbb` | Local review is separated from optional GitHub `@claude review`. | Both manifests validated; no workflow tests. |
| swarm | 0.2.0 at `f443fbb` | missing | missing | 2026-07-12 / `f443fbb` | Evaluation deferred until core workflows are stable. | Explicit Phase 1 deferral. |

## Baseline limitations

- No plugin is currently advertised as installable for Codex or Grok.
- Fresh-session skill discovery has not been tested because Phase 2 skills do
  not exist yet.
- Grok native plugin commands and local marketplace registration were verified
  with Grok Build 0.2.93, but a real installed adapter session is still pending.
- Codex manifests and isolated local marketplace registration were verified
  with the current plugin validator and Codex CLI 0.144.1.
