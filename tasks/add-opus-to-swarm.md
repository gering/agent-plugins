# Add Opus to the native swarm review ensemble

## Goal

When `swarm` is implemented for `agent-plugins`, include Anthropic Opus as an
optional, independent reviewer family alongside the native Codex and Grok
reviewers.

## Context

Phase 1 deliberately defers `swarm` until the core adoption, knowledge, work,
and PR workflows are stable. The current architecture names Codex and Grok as
the shipped runtimes, but does not guarantee that a future native swarm retains
the Claude/Opus review family used by the reference implementation.

Opus is an optional external review backend, not a runtime distributed by this
repository. Its integration belongs in the narrowly scoped
`plugins/swarm/reviewers/anthropic/` boundary, not in `shared/`, `codex/`, or
`grok/`. It may use an explicit Claude CLI adapter but must not make
`claude-plugins` a runtime dependency.

A Phase 1 dogfood review also showed why scope must be explicit: invoking the
installed Claude swarm from another repository selected an active Claude
worktree instead of the intended `agent-plugins` PR diff. The native adapter
must receive the prepared diff or repository/ref explicitly.

## Requirements

- [ ] Add an optional Opus reviewer adapter using the current supported Claude
  CLI interface and an explicitly selected Opus model.
- [ ] Probe CLI availability and authentication separately; report unavailable,
  unauthenticated, errored, and clean-review states distinctly.
- [ ] Pass a precomputed, fenced diff or explicit repository/base/head scope to
  the adapter. Never infer scope from a resumed Claude session or unrelated
  active worktree.
- [ ] Run Opus read-only with no edit authority. Findings are advisory data and
  use the same bounded schema and secret-redaction boundary as other reviewers.
- [ ] Count Opus as the Anthropic model family for cross-family consensus;
  multiple Anthropic voices still count as one family.
- [ ] Keep Codex and Grok swarm operation functional when Claude CLI or Opus
  access is absent.
- [ ] Do not reference `${CLAUDE_PLUGIN_ROOT}` or require the sibling
  `claude-plugins` checkout from Codex/Grok adapters.
- [ ] Add deterministic tests for scope selection, missing CLI, missing auth,
  backend error, empty findings, malformed output, and successful findings.
- [ ] Exercise a real PR-diff review with Codex, Grok, and Opus and record the
  runtime versions/models and evidence in `docs/parity.md`.

## Non-goals

- Shipping Claude Code as a runtime from `agent-plugins`.
- Installing or modifying the Claude marketplace.
- Giving any external reviewer permission to edit, commit, push, or comment on
  a pull request.

## Relevant files

- Future `plugins/swarm/shared/` review schema and merge logic
- Future `plugins/swarm/reviewers/anthropic/` read-only external adapter
- Future `plugins/swarm/codex/` and `plugins/swarm/grok/` orchestration adapters
- `docs/parity.md`
- `docs/claude-compatibility-backlog.md` when Claude-side changes are needed

## Acceptance

The task is complete when a review started natively from both Codex and Grok
can include an authenticated Opus voice, shows it as a separate Anthropic
family in the merged report, remains read-only, and cannot review a different
repository or worktree than the explicitly supplied scope.

This task is a dependency of `tasks/port-swarm-p5.md`.
