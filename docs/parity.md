# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `9fd980c7e72352fec4e6d143053f7d2d4e1931b2`
- Last sync review: 2026-07-14
- Dirty upstream files and untracked directories were excluded from the review.
- Latest observed upstream `main`: `9fd980c7e72352fec4e6d143053f7d2d4e1931b2`.
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
0.3.1; that behavior was reviewed at `59996c2` without importing it. PR #29
added PR-diff review and advanced swarm to 0.4.0; it was reviewed at `9fd980c`
(read-only against cached origin/main, dirty paths excluded). The planned
native mapping is tracked in `tasks/port-swarm-p5.md` and
`tasks/add-opus-to-swarm.md`.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | partial | partial | 2026-07-14 / `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | Codex and Grok ship thin native adapters over the same POSIX-only, read-only shared auditor (audit_project.py). Unbound `--separate-git-dir`, Windows support, and approved apply mode remain planned. Grok uses explicit .grok-plugin + ./grok/skills/ convention. | Complete deterministic test suite; native Grok plugin validation; isolated `GROK_HOME` direct install and single plugin-skill discovery; JSON and text auditor output; current Codex reinstall/list behavior; non-mutating dogfood of the installed Grok adapter against muellmann-app.de with identical pre/post status hashes; fail-closed and read-only guarantees. |
| knowledge-system | 1.8.2 at `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | planned | planned | 2026-07-14 / `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | Native memories are local preference stores; versioned project knowledge remains canonical. | Both manifests validated; no skills imported. |
| work-system | 1.6.0 at `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | planned | planned | 2026-07-14 / `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | Launch/resume will use native Codex and Grok/herdr commands. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.3 at `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | planned | planned | 2026-07-14 / `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | Local review is separated from optional GitHub `@claude review`; upstream's review-table alignment remains unported. | Both manifests validated; PR #27 format changes reviewed; no workflow tests. |
| swarm | 0.4.0 at `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | missing | missing | 2026-07-14 / `9fd980c7e72352fec4e6d143053f7d2d4e1931b2` | Evaluation deferred until core workflows are stable; P5 native mapping is planned but not imported. | Merged upstream behavior through PR #29's PR-diff review reviewed read-only; no runtime implementation. |

## Baseline limitations

- `project-adoption` is advertised and installable for both Codex (via .agents) and
  Grok (via .grok-plugin marketplace + native `grok plugin install` / marketplace).
- `project-adoption` (Codex + Grok) currently requires POSIX descriptor-relative
  no-follow file I/O and fails closed on unsupported hosts, including Windows.
- Git metadata must be rooted normally or bind back through linked-worktree or
  submodule metadata; unbound `--separate-git-dir` layouts are unsupported.
- Fresh-session skill discovery, native manifest validation, marketplace
  registration/install, JSON+text auditor, and read-only dogfood proven for
  the installed Grok adapter; Codex behavior remains unchanged.
- Grok native commands verified with Grok Build 0.2.99; Codex with 0.144.1.
