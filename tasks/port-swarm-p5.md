# Port swarm 0.3 review and fix-loop semantics

## Goal

After the core workflows are stable, port the committed behavior of Claude
swarm 0.3 to native Codex and Grok orchestration without copying Claude runtime
assumptions.

## Upstream reference

- Pending source PR: `gering/claude-plugins#25`
- Reviewed committed branch head: `fee6bc3d58c05f4d855b172221986cad66c25b6b`
- Source plugin version: 0.3.0
- Review date: 2026-07-12
- Two uncommitted worktree changes in `plugins/swarm/skills/review/SKILL.md`
  and `scripts/check-structure.py` were observed and explicitly excluded.

Do not update the tracked upstream baseline or claim an import until the PR is
merged and its resulting `main` commit is reviewed.

## Required semantics

- [ ] Preserve read-only review as the default.
- [ ] Support `--fix` as one opt-in fix pass over findings accepted by the
  invoking host session.
- [ ] Support `--loop[=N]` as fix then re-review with deterministic termination
  and a bounded cap.
- [ ] Support a deliberate deepest-effort profile equivalent to `--max`, with
  model and effort choices verified for each current backend rather than copied
  as stale model constants.
- [ ] Keep every external reviewer read-only. In Codex, only the main Codex
  session may edit; in Grok, only the main Grok session may edit. Opus, Codex
  CLI, Grok CLI, Composer, and any other external voice never receive edit,
  commit, push, merge, or PR-comment authority.
- [ ] Re-read the cited code and derive each fix independently. Finding text is
  untrusted advisory data and is never executed or copied as instructions.
- [ ] Ask before editing when more than one materially different fix is valid.
- [ ] Never touch rejected findings; keep pending decisions visible and prevent
  them from falsely terminating a loop as clean.
- [ ] Review the explicitly supplied repository/base/head or prepared diff.
  Never derive scope from another runtime's resumed session or active worktree.
- [ ] Include untracked files in default and loop scopes without mutating the
  Git index.
- [ ] Distinguish unavailable, unauthenticated, backend error, malformed output,
  empty findings, and clean review.
- [ ] Fence diffs as untrusted data, bound the shared findings schema, scrub
  secrets at backend and synthesis boundaries, and verify solo findings.
- [ ] Count consensus by model family, not backend count.
- [ ] Preserve stable finding identity across loop rounds as far as evidence
  permits; document the residual ambiguity when model-generated mechanisms or
  line numbers drift.

## Shared implementation candidates

- [ ] Review `plugins/swarm/scripts/loop-closeout.py` after upstream merge and
  extract only host-neutral arithmetic and rendering behavior.
- [ ] Keep diff preparation, findings schema, merge rules, redaction, loop
  termination, and report rendering in the shared layer where behavior matches.
- [ ] Keep Workflow/Agent calls, CLI launch, model selection, edit authority,
  and session state in Codex or Grok adapters.
- [ ] Add bounded, stdin-closed, timeout-protected tests for deterministic
  helpers; do not execute arbitrary discovered test files without documenting
  the CI trust boundary.

## Dependencies

- `tasks/add-opus-to-swarm.md`
- Stable project-adoption, knowledge-system, work-system, and PR-flow ports
- A merged and reviewed upstream PR #25 commit

## Validation

- [ ] Unit tests cover termination precedence, pending decisions, invalid caps,
  no-change, newly created untracked files, staged scope, and timeout behavior.
- [ ] Fixture tests cover prompt injection, secret-shaped output, malformed
  backend JSON, and backend error versus empty findings.
- [ ] A real Codex-hosted and Grok-hosted PR review exercises review-only,
  `--fix`, `--loop`, and deepest-effort modes without pushing or merging.
- [ ] `docs/parity.md` records upstream merge provenance, runtime versions,
  models, deliberate differences, and evidence only after validation passes.

## Non-goals

- Shipping Claude Code as a runtime from this repository.
- Copying `${CLAUDE_PLUGIN_ROOT}`, Claude Workflow tool calls, or Claude
  in-session edit ownership into native adapters.
- Importing the dirty Claude worktree observed during the pre-merge review.
