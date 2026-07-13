# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2`
- Last sync review: 2026-07-13
- Dirty upstream files and untracked directories were excluded from the review.
- Latest observed upstream `main`: `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2`.
  Run `python3 scripts/check-upstream.py` to audit it against the locally
  cached sibling `origin/main`; refresh remote refs separately for network
  freshness.

## Latest upstream review

Claude PR [`#25`](https://github.com/gering/claude-plugins/pull/25) merged as
`ee7bb2db650fb790530c7310be4b317a3e49bb56` and advances `swarm` to 0.3.0
with opt-in `--fix`, `--loop`, and deepest-effort review behavior. The merged
commit was reviewed on 2026-07-12; dirty sibling files remained excluded and
no implementation was imported. Later knowledge-only reindex and link fixes
through `87917b5` were also reviewed without changing source plugin versions or
native mappings. Claude PR #27 then aligned pr-flow's review-table semantics
with the swarm findings-table family and advanced pr-flow to 1.2.3; that
format-only behavior was reviewed at `390c1ca` without importing it. The
planned native mapping is tracked in `tasks/port-swarm-p5.md` and
`tasks/add-opus-to-swarm.md`.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | partial | planned | 2026-07-13 / `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | Codex ships a read-only native audit; Grok adapter and approved apply mode remain planned. | 88 deterministic tests; native manifest validation; isolated Codex install; fresh-session skill discovery and non-mutating audit of `muellmann-app.de` with expected guidance, knowledge, memory, plugin, and worktree findings. |
| knowledge-system | 1.8.2 at `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | planned | planned | 2026-07-13 / `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | Native memories are local preference stores; versioned project knowledge remains canonical. | Both manifests validated; no skills imported. |
| work-system | 1.6.0 at `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | planned | planned | 2026-07-13 / `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | Launch/resume will use native Codex and Grok/herdr commands. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.3 at `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | planned | planned | 2026-07-13 / `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | Local review is separated from optional GitHub `@claude review`; upstream's review-table alignment remains unported. | Both manifests validated; PR #27 format changes reviewed; no workflow tests. |
| swarm | 0.3.0 at `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | missing | missing | 2026-07-13 / `390c1caa2ddd1230c4dc5cee7be40f30fae1d3f2` | Evaluation deferred until core workflows are stable; P5 native mapping is planned but not imported. | Merged upstream behavior, knowledge maintenance, and PR #27 table alignment reviewed; no runtime implementation. |

## Baseline limitations

- Only Codex `project-adoption` is currently advertised as installable; all
  other Codex plugins and every Grok plugin remain unavailable.
- Fresh-session discovery is proven for Codex `project-adoption`; other Codex
  plugins and every Grok workflow remain untested and unavailable.
- Grok native plugin commands and local marketplace registration were verified
  with Grok Build 0.2.93, but a real installed adapter session is still pending.
- Codex manifests and isolated local marketplace registration were verified
  with the current plugin validator and Codex CLI 0.144.1.
