# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `59996c259786eb2d4d6b9805925439745eb5c6e3`
- Last sync review: 2026-07-13
- Dirty upstream files and untracked directories were excluded from the review.
- Latest observed upstream `main`: `59996c259786eb2d4d6b9805925439745eb5c6e3`.
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
subsequent Claude PR #28 structurally fenced backend finding text in swarm's
merge and verifier prompts, added unsafe-path gates, and advanced swarm to
0.3.1; that behavior was reviewed at `59996c2` without importing it. The
planned native mapping is tracked in `tasks/port-swarm-p5.md` and
`tasks/add-opus-to-swarm.md`.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | partial | planned | 2026-07-13 / `59996c259786eb2d4d6b9805925439745eb5c6e3` | Codex ships a POSIX-only, read-only native audit; unbound `--separate-git-dir`, Windows support, Grok adapter, and approved apply mode remain planned. | Complete deterministic test suite; native manifest validation; isolated Codex install; fresh-session skill discovery and non-mutating audit of `muellmann-app.de` with explicit scanned, unscanned, policy-excluded, Git-ignored, and pruned-directory coverage. |
| knowledge-system | 1.8.2 at `59996c259786eb2d4d6b9805925439745eb5c6e3` | planned | planned | 2026-07-13 / `59996c259786eb2d4d6b9805925439745eb5c6e3` | Native memories are local preference stores; versioned project knowledge remains canonical. | Both manifests validated; no skills imported. |
| work-system | 1.6.0 at `59996c259786eb2d4d6b9805925439745eb5c6e3` | planned | planned | 2026-07-13 / `59996c259786eb2d4d6b9805925439745eb5c6e3` | Launch/resume will use native Codex and Grok/herdr commands. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.3 at `59996c259786eb2d4d6b9805925439745eb5c6e3` | planned | planned | 2026-07-13 / `59996c259786eb2d4d6b9805925439745eb5c6e3` | Local review is separated from optional GitHub `@claude review`; upstream's review-table alignment remains unported. | Both manifests validated; PR #27 format changes reviewed; no workflow tests. |
| swarm | 0.3.1 at `59996c259786eb2d4d6b9805925439745eb5c6e3` | missing | missing | 2026-07-13 / `59996c259786eb2d4d6b9805925439745eb5c6e3` | Evaluation deferred until core workflows are stable; P5 native mapping is planned but not imported. | Merged upstream behavior through PR #28's finding-fence and path-safety hardening reviewed; no runtime implementation. |

## Baseline limitations

- Only Codex `project-adoption` is currently advertised as installable; all
  other Codex plugins and every Grok plugin remain unavailable.
- Codex `project-adoption` currently requires POSIX descriptor-relative
  no-follow file I/O and fails closed on unsupported hosts, including Windows.
- Git metadata must be rooted normally or bind back through linked-worktree or
  submodule metadata; unbound `--separate-git-dir` layouts are unsupported.
- Fresh-session discovery is proven for Codex `project-adoption`; other Codex
  plugins and every Grok workflow remain untested and unavailable.
- Grok native plugin commands and local marketplace registration were verified
  with Grok Build 0.2.93, but a real installed adapter session is still pending.
- Codex manifests and isolated local marketplace registration were verified
  with the current plugin validator and Codex CLI 0.144.1.
