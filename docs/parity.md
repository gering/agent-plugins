# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `563daf9c8d38278ee3889cfd337b3c6eed715675`
- Last sync review: 2026-07-17
- Dirty upstream files and untracked directories were excluded from the review.
- Latest observed upstream `main`: `563daf9c8d38278ee3889cfd337b3c6eed715675`.
  Run `python3 scripts/check-upstream.py` to audit it against the locally
  cached sibling `origin/main`; refresh remote refs separately for network
  freshness.

## Latest upstream review

Committed changes through `563daf9` were reviewed read-only while dirty sibling
paths remained excluded. Since the previous baseline, upstream added herdr tab
glyph synchronization across Work and PR Flow (`work-system` 1.8.0,
`pr-flow` 1.3.0) and removed Swarm's retired Grok Composer backend while adding
model-aware Grok readiness (`swarm` 0.4.3). Those runtime-specific changes are
classified but unported. Knowledge remains at 1.9.0; this slice maps only query
and read-only reindex-check behavior.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | partial | partial | 2026-07-17 / `563daf9c8d38278ee3889cfd337b3c6eed715675` | Codex and Grok ship thin native adapters over the same POSIX-only, read-only shared auditor (audit_project.py). Unbound `--separate-git-dir`, Windows support, and approved apply mode remain planned. | Deterministic suite, native manifest validation, isolated install/discovery, and non-mutating muellmann-app.de dogfood. |
| knowledge-system | 1.9.0 at `563daf9c8d38278ee3889cfd337b3c6eed715675` | partial | partial | 2026-07-17 / `563daf9c8d38278ee3889cfd337b3c6eed715675` | Versioned `.claude/knowledge/` remains canonical. Query does not silently fall back to source exploration. Reindex is a deterministic read-only check; writes, semantic cross-link/duplicate/staleness analysis, curate, init, prime, and statusline remain planned. Both native adapters require POSIX descriptor-relative no-follow I/O. | Shared helper and four native skills validated; 141-test suite with descriptor-anchored traversal plus deterministic ranking/frontmatter/Markdown/no-write regression coverage; non-mutating muellmann-app.de dogfood routes `Angebotsrechner` through the index and reports 15 metadata findings without changing knowledge hashes; Codex cache install and isolated-GROK_HOME discovery of query/reindex. |
| work-system | 1.8.0 at `563daf9c8d38278ee3889cfd337b3c6eed715675` | planned | planned | 2026-07-17 / `563daf9c8d38278ee3889cfd337b3c6eed715675` | Launch/resume will use native Codex and Grok/herdr commands; upstream statusline and herdr tab-state glyphs are unported. | Committed herdr glyph changes classified read-only; no native workflow tests. |
| pr-flow | 1.3.0 at `563daf9c8d38278ee3889cfd337b3c6eed715675` | planned | planned | 2026-07-17 / `563daf9c8d38278ee3889cfd337b3c6eed715675` | Local review is separated from optional GitHub `@claude review`; upstream herdr glyph refresh hooks are unported. | Committed PR-side glyph refresh changes classified read-only; no native workflow tests. |
| swarm | 0.4.3 at `563daf9c8d38278ee3889cfd337b3c6eed715675` | missing | missing | 2026-07-17 / `563daf9c8d38278ee3889cfd337b3c6eed715675` | Evaluation deferred until core workflows are stable; Composer removal and model-aware Grok readiness are reviewed but unported. | Committed upstream changes classified read-only; no runtime implementation. |

## Baseline limitations

- `project-adoption` and the read-only `knowledge-system` slice are advertised
  for Codex and Grok through their native marketplaces.
- `project-adoption` (Codex + Grok) currently requires POSIX descriptor-relative
  no-follow file I/O and fails closed on unsupported hosts, including Windows.
- `knowledge-system` uses the same POSIX-only safety floor for anchored reads.
- Git metadata must be rooted normally or bind back through linked-worktree or
  submodule metadata; unbound `--separate-git-dir` layouts are unsupported.
- Fresh-session skill discovery, native manifest validation, marketplace
  registration/install, and read-only dogfood are proven for project-adoption;
  knowledge-system installation/discovery evidence is recorded by this slice.
- Grok native commands verified with Grok Build 0.2.101; Codex with 0.144.4.
