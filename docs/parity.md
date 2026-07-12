# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `ee7bb2db650fb790530c7310be4b317a3e49bb56`
- Last sync review: 2026-07-12
- Dirty upstream files and untracked directories were excluded from the review.
- Latest observed upstream `main`: `ee7bb2db650fb790530c7310be4b317a3e49bb56`.
  Run `python3 scripts/check-upstream.py` to audit it against the locally
  cached sibling `origin/main`; refresh remote refs separately for network
  freshness.

## Latest upstream review

Claude PR [`#25`](https://github.com/gering/claude-plugins/pull/25) merged as
`ee7bb2db650fb790530c7310be4b317a3e49bb56` and advances `swarm` to 0.3.0
with opt-in `--fix`, `--loop`, and deepest-effort review behavior. The merged
commit was reviewed on 2026-07-12; dirty sibling files remained excluded and
no implementation was imported. The planned native mapping is tracked in
`tasks/port-swarm-p5.md` and `tasks/add-opus-to-swarm.md`.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | planned | planned | 2026-07-12 / `ee7bb2db650fb790530c7310be4b317a3e49bb56` | Read-only adoption audit will be native to this repository. | Both manifests validated; both local marketplaces registered in isolated homes. No workflow yet. |
| knowledge-system | 1.8.2 at `ee7bb2db650fb790530c7310be4b317a3e49bb56` | planned | planned | 2026-07-12 / `ee7bb2db650fb790530c7310be4b317a3e49bb56` | Native memories are local preference stores; versioned project knowledge remains canonical. | Both manifests validated; no skills imported. |
| work-system | 1.6.0 at `ee7bb2db650fb790530c7310be4b317a3e49bb56` | planned | planned | 2026-07-12 / `ee7bb2db650fb790530c7310be4b317a3e49bb56` | Launch/resume will use native Codex and Grok/herdr commands. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.2 at `ee7bb2db650fb790530c7310be4b317a3e49bb56` | planned | planned | 2026-07-12 / `ee7bb2db650fb790530c7310be4b317a3e49bb56` | Local review is separated from optional GitHub `@claude review`. | Both manifests validated; no workflow tests. |
| swarm | 0.3.0 at `ee7bb2db650fb790530c7310be4b317a3e49bb56` | missing | missing | 2026-07-12 / `ee7bb2db650fb790530c7310be4b317a3e49bb56` | Evaluation deferred until core workflows are stable; P5 native mapping is planned but not imported. | Merged upstream behavior reviewed; no runtime implementation. |

## Baseline limitations

- No plugin is currently advertised as installable for Codex or Grok.
- Fresh-session skill discovery has not been tested because Phase 2 skills do
  not exist yet.
- Grok native plugin commands and local marketplace registration were verified
  with Grok Build 0.2.93, but a real installed adapter session is still pending.
- Codex manifests and isolated local marketplace registration were verified
  with the current plugin validator and Codex CLI 0.144.1.
