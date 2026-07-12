# Claude compatibility backlog

Items here are proposals only. They must be implemented in a separate
`claude-plugins` session, branch, task, and pull request.

## Accept neutral worktree locations

- Affected Claude files: `plugins/work-system/skills/*` and worktree helper
  scripts that assume `.claude/worktrees/`.
- Motivation: existing projects need a transition path to the neutral
  `.worktrees/` location without breaking current worktrees.
- Compatibility gain: shared detection and safety logic can support Claude,
  Codex, and Grok while launch behavior stays in adapters.
- Existing-user behavior: additive if `.claude/worktrees/` remains preferred
  when already present; any automatic move would be behavior-changing and is
  not proposed.

## Parameterize reusable plugin roots

- Affected Claude files: scripts under `plugins/knowledge-system/`,
  `plugins/work-system/`, and `plugins/pr-flow/` that read
  `${CLAUDE_PLUGIN_ROOT}`.
- Motivation: agent-neutral helpers need explicit input paths rather than a
  host-specific environment variable.
- Compatibility gain: common validation and workflow logic can be compared or
  extracted without simulating Claude runtime state.
- Existing-user behavior: none if the variable remains the Claude adapter's
  default and explicit parameters are additive.

## Separate review provider from PR safety

- Affected Claude files: `plugins/pr-flow/skills/open/`, `cycle/`, `check/`,
  `fix/`, and related documentation.
- Motivation: readiness, rebase, and merge safety are shared semantics, while
  GitHub `@claude review` is a provider-specific optional step.
- Compatibility gain: Codex and Grok can reuse the safety contract without
  falsely claiming support for Claude's GitHub review loop.
- Existing-user behavior: potentially behavior-changing if defaults move;
  preserve the current Claude default and expose provider choice explicitly.

## Emit a capability inventory

- Affected Claude files: `.claude-plugin/marketplace.json`, plugin manifests,
  and a new deterministic inventory/check script.
- Motivation: version numbers alone do not show which user-visible workflows a
  plugin implements.
- Compatibility gain: upstream sync can map changed capabilities to native
  adapters mechanically and flag uncertain changes.
- Existing-user behavior: none; metadata-only addition.

## Isolate host-neutral swarm loop helpers

- Affected Claude files: `plugins/swarm/scripts/loop-closeout.py`,
  `plugins/swarm/skills/review/SKILL.md`, and associated tests introduced by
  PR #25.
- Motivation: loop termination arithmetic, open-finding trajectories, diff
  scope rules, and report state are potentially shared semantics, while Claude
  Workflow calls and Claude-only edit ownership are runtime behavior.
- Compatibility gain: Codex and Grok adapters can reuse or compare a tested
  neutral contract without importing Claude session assumptions or
  `${CLAUDE_PLUGIN_ROOT}`.
- Existing-user behavior: none if extraction preserves the current Claude
  entrypoint and output; changing who may edit or how scope is inferred would
  be behavior-changing and requires separate review.
