# Parity status

This ledger reports compatibility per plugin and runtime. `parity` is used only
after the workflow has executable or reviewed behavioral evidence; repository
scaffolding alone does not qualify.

## Upstream baseline

- Claude source: [`gering/claude-plugins`](https://github.com/gering/claude-plugins)
- Last reviewed commit: `bd33b57bbd4982d45e190a913ffe85260a566c14`
- Last sync review: 2026-07-16
- Dirty upstream files and untracked directories were excluded from the review.
- Latest observed upstream `main`: `bd33b57bbd4982d45e190a913ffe85260a566c14`.
  Run `python3 scripts/check-upstream.py` to audit it against the locally
  cached sibling `origin/main`; refresh remote refs separately for network
  freshness.

## Latest upstream review

Committed changes through `bd33b57` were reviewed read-only while dirty sibling
paths remained excluded. Since the previous baseline, upstream added a
repository changelog, deterministic and hardened Swarm PR publishing, Grok
0.2.101 model/effort compatibility (`swarm` 0.4.2), a Claude-specific work
statusline (`work-system` 1.7.0), and a display-only knowledge statusline update
(`knowledge-system` 1.9.0). The statusline, Swarm, and Work changes remain
unported. This slice maps only query and read-only reindex-check behavior; its
deliberate native differences are recorded below.

Allowed states are `missing`, `planned`, `partial`, `parity`, and
`intentional-divergence`.

| Plugin | Claude source | Codex status | Grok status | Last sync | Differences | Evidence |
|---|---|---|---|---|---|---|
| project-adoption | New companion capability; no single Claude plugin source | partial | partial | 2026-07-16 / `bd33b57bbd4982d45e190a913ffe85260a566c14` | Codex and Grok ship thin native adapters over the same POSIX-only, read-only shared auditor (audit_project.py). Unbound `--separate-git-dir`, Windows support, and approved apply mode remain planned. | Deterministic suite, native manifest validation, isolated install/discovery, and non-mutating muellmann-app.de dogfood. |
| knowledge-system | 1.9.0 at `bd33b57bbd4982d45e190a913ffe85260a566c14` | partial | partial | 2026-07-16 / `bd33b57bbd4982d45e190a913ffe85260a566c14` | Versioned `.claude/knowledge/` remains canonical. Query does not silently fall back to source exploration. Reindex is a deterministic read-only check; writes, semantic cross-link/duplicate/staleness analysis, curate, init, prime, and statusline remain planned. | Shared helper and four native skills validated; 133-test suite; symlink, UTF-8, bounds, link and no-write gates; identical pre/post Git-status and knowledge hashes on muellmann-app.de with two reported metadata findings; Codex cache install and isolated-GROK_HOME discovery of exactly query/reindex from the native plugin. |
| work-system | 1.7.0 at `bd33b57bbd4982d45e190a913ffe85260a566c14` | planned | planned | 2026-07-16 / `bd33b57bbd4982d45e190a913ffe85260a566c14` | Launch/resume will use native Codex and Grok/herdr commands; upstream's Claude statusline is unported. | Both manifests validated; no workflow tests. |
| pr-flow | 1.2.3 at `bd33b57bbd4982d45e190a913ffe85260a566c14` | planned | planned | 2026-07-16 / `bd33b57bbd4982d45e190a913ffe85260a566c14` | Local review is separated from optional GitHub `@claude review`; upstream's review-table alignment remains unported. | Both manifests validated; no workflow tests. |
| swarm | 0.4.2 at `bd33b57bbd4982d45e190a913ffe85260a566c14` | missing | missing | 2026-07-16 / `bd33b57bbd4982d45e190a913ffe85260a566c14` | Evaluation deferred until core workflows are stable; deterministic PR posting and Grok 0.2.101 changes are reviewed but unported. | Committed upstream changes classified read-only; no runtime implementation. |

## Baseline limitations

- `project-adoption` and the read-only `knowledge-system` slice are advertised
  for Codex and Grok through their native marketplaces.
- `project-adoption` (Codex + Grok) currently requires POSIX descriptor-relative
  no-follow file I/O and fails closed on unsupported hosts, including Windows.
- Git metadata must be rooted normally or bind back through linked-worktree or
  submodule metadata; unbound `--separate-git-dir` layouts are unsupported.
- Fresh-session skill discovery, native manifest validation, marketplace
  registration/install, and read-only dogfood are proven for project-adoption;
  knowledge-system installation/discovery evidence is recorded by this slice.
- Grok native commands verified with Grok Build 0.2.101; Codex with 0.144.4.
