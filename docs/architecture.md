# Architecture

## Purpose

`agent-plugins` is the Codex and Grok companion to
`gering/claude-plugins`. It implements equivalent workflows natively for both
target agents while keeping Claude Code in its existing repository during the
initial migration.

The repositories are related but independently installable:

```text
gering/claude-plugins   Claude Code distribution and current feature reference
gering/agent-plugins    Codex and Grok distribution
```

This architecture was reviewed for the Codex/Grok-only Phase 1 boundary on
2026-07-12. The review used Codex CLI 0.144.1 and Grok Build 0.2.93. In
particular, Grok now exposes native plugin, marketplace, validation, launch,
and resume commands; the design therefore uses Grok's native plugin surface
instead of treating Claude compatibility discovery as the distribution path.

This repository must track upstream feature intent, provenance, parity, and
intentional differences. It must not depend on the Claude repository being
installed at runtime.

## Product boundary

### Initial runtimes

- Codex
- Grok Build / Grok CLI

### Reference runtime

- Claude Code remains implemented and published from `gering/claude-plugins`.
- Claude behavior is an input to porting and parity decisions, not a runtime
  surface shipped from this repository initially.
- Claude may be reconsidered after Codex and Grok workflows are stable. The
  architecture must not prevent that future choice.

## Core principles

### 1. Share semantics, not runtime assumptions

Task state, branch safety, readiness checks, knowledge schemas, and migration
rules should be shared where behavior is genuinely equivalent.

Session launchers, resume commands, skill discovery, prompts, manifests, hooks,
and installation are runtime-specific and must use explicit adapters.

### 2. Keep `AGENTS.md` agent-neutral

Codex and Grok both consume `AGENTS.md`. It must contain only durable project
guidance that is correct for both agents.

Do not put statements such as "you are the Grok orchestrator" or Codex-specific
CLI instructions into shared `AGENTS.md` files. Put those instructions in the
corresponding adapter skill or runtime documentation.

### 3. Preserve observable behavior deliberately

Porting a file is not proof of parity. A plugin reaches parity only when:

- its user-visible workflow is mapped
- runtime differences are documented
- structure and behavior checks pass
- the relevant agent has exercised the workflow
- the upstream Claude commit is recorded

### 4. Prefer incremental migration

Existing Claude projects may contain `CLAUDE.md`, Grok-specific `AGENTS.md`,
`.claude/knowledge/`, `.claude/rules/`, and `.claude/worktrees/`. Adoption must
detect these structures and preserve them unless an explicit migration is
approved.

### 5. Keep repository ownership clear

- Make Codex/Grok implementation changes in `agent-plugins`.
- Make Claude runtime changes in `claude-plugins` through separate tasks and
  pull requests.
- Record compatibility proposals here before opening Claude-side tasks.
- Never mutate the sibling repository as a side effect of a sync operation.

## Repository layout

The initial target layout is:

```text
agent-plugins/
  AGENTS.md
  README.md
  TASK.md
  .agents/
    plugins/
      marketplace.json
    upstream/
      claude-plugins.json
  .grok-plugin/
    marketplace.json
  docs/
    architecture.md
    parity.md
    migration-from-claude.md
    claude-compatibility-backlog.md
  scripts/
    check-structure.*
    check-upstream.*
  plugins/
    project-adoption/
      .codex-plugin/plugin.json
      .grok-plugin/plugin.json
      shared/
      codex/
      grok/
    knowledge-system/
      .codex-plugin/plugin.json
      .grok-plugin/plugin.json
      shared/
      codex/
      grok/
    work-system/
      .codex-plugin/plugin.json
      .grok-plugin/plugin.json
      shared/
      codex/
      grok/
    pr-flow/
      .codex-plugin/plugin.json
      .grok-plugin/plugin.json
      shared/
      codex/
      grok/
```

The implementation may refine this tree after testing actual marketplace and
skill discovery behavior. The separation between shared semantics and native
adapters is mandatory even if directory names change.

## Distribution architecture

### Codex

Codex distribution uses:

- `.agents/plugins/marketplace.json` for the repository marketplace
- `.codex-plugin/plugin.json` for each installable plugin
- Codex skills with native metadata and optional `agents/openai.yaml`
- native Codex CLI commands for launch, resume, and review

Codex adapter skills must not reference `${CLAUDE_PLUGIN_ROOT}`, Claude tool
names, or Claude session commands.

### Grok

Grok distribution uses its native plugin interface, verified with Grok Build
0.2.93:

- `.grok-plugin/marketplace.json` for the repository marketplace
- `.grok-plugin/plugin.json` for each Grok plugin
- `grok plugin marketplace add` for marketplace registration
- `grok plugin install` for direct local or Git installation
- `grok plugin validate` for manifest validation

Grok can discover compatible Claude components in existing installations, but
that compatibility bridge is not this repository's distribution mechanism.
Native manifests and runtime-specific adapters make installation explicit and
prevent accidental dependence on a sibling Claude checkout.

Grok adapters own:

- Grok TUI launch and resume commands
- herdr launch/resume behavior
- Grok skill discovery and installation instructions
- Grok-specific review or memory integrations

The Phase 1 marketplace is intentionally empty until the first Grok adapter is
behaviorally usable. This avoids advertising manifest-only scaffolds as
installable plugins.

### Claude

Claude distribution remains in `gering/claude-plugins` with its existing
marketplace and `.claude-plugin` manifests. This repository links to it and
tracks its versions, but does not duplicate its install surface initially.

## Plugin model

### Shared layer

The shared layer may contain:

- workflow specifications
- agent-neutral scripts
- schemas and fixtures
- readiness and safety rules
- output format definitions
- migration detection logic

Shared scripts must accept paths and runtime choices explicitly. They must not
infer a Claude plugin root or launch an agent directly unless the runtime is an
explicit input.

### Adapter layer

Each adapter contains the smallest runtime-specific surface necessary:

- skill entrypoints and triggering metadata
- tool and prompt conventions
- session launcher/resume implementation
- manifest and installation metadata
- runtime-only documentation

Avoid a single large skill full of `if Claude`, `if Codex`, and `if Grok`
branches. Separate entrypoints should call shared helpers or reference shared
specifications.

Optional external reviewer families are a separate boundary under
`plugins/<plugin>/reviewers/<family>/`. They are not host adapters, remain
read-only, receive an explicit prepared scope, and must degrade cleanly when
their CLI or authentication is unavailable. For example, a future Opus voice
may use `reviewers/anthropic/`; Claude CLI calls must not appear in `shared/`,
`codex/`, or `grok/`. Such a reviewer owns only backend invocation and bounded
result translation; shared orchestration owns scope preparation, schema
validation, secret redaction, and consensus. Reviewer code remains fail-closed
until deterministic tests prove prepared-scope isolation, read-only behavior,
unavailable/error handling, and malformed-output rejection.

## Knowledge and memory

### Canonical project knowledge

Durable project knowledge must be versioned in the project repository. Native
Claude, Codex, and Grok memories are local state and must not be the only store
for project facts.

Existing `.claude/knowledge/` installations are supported as a compatibility
location. Do not move them automatically merely to obtain an agent-neutral
name. A future neutral knowledge location requires an explicit migration design
and compatibility tests for all active agents.

### Runtime memories

Use native memories primarily for:

- user preferences
- personal workflow defaults
- non-canonical local context

Adoption and knowledge skills must direct durable corrections and architecture
facts back into the versioned knowledge store.

### Always-on guidance

Codex and Grok receive shared durable guidance through `AGENTS.md`. Claude has
different startup and rules behavior in the sibling repository. Do not invent a
fake universal rules directory or assume `@` import expansion across agents.

## Tasks and worktrees

### Tasks

Keep `tasks/` as the canonical task backlog directory. It is already
agent-neutral and moving it would add churn without improving interoperability.

`TASK.md` remains the task handoff inside an active worktree or bootstrap
repository.

### Worktrees

The long-term neutral location is:

```text
.worktrees/
```

Existing projects using `.claude/worktrees/` must continue to work. Detection
and compatibility come before migration. A compatibility link may be proposed
only after checking for existing directories, links, active worktrees, and
uncommitted work.

Worktree helpers own repository and task state. Runtime adapters own which agent
is launched inside the worktree.

## Repository relationship and parity

`docs/parity.md` is the public compatibility ledger. It records, per plugin and
agent:

- upstream Claude plugin version
- upstream commit reviewed
- implementation status
- last synchronization date
- intentional differences
- validation evidence

README files in both repositories should link to each other. Changes required in
the Claude repository are captured in
`docs/claude-compatibility-backlog.md` and implemented through separate
Claude-side tasks.

Parity states are:

- `missing`
- `planned`
- `partial`
- `parity`
- `intentional-divergence`

Parity is assessed per plugin and runtime, never as one repository-wide claim.

## Upstream synchronization

The planned `sync-claude-plugins` skill automates analysis and controlled
porting from the Claude reference repository.

### State

Tracked upstream state belongs in:

```text
.agents/upstream/claude-plugins.json
```

It records:

- upstream repository URL or configured local path
- last reviewed commit
- per-plugin source version
- imported source files or capability mappings
- intentional divergence identifiers

Do not store machine-specific absolute paths as the only repository locator.

### Sync flow

1. Resolve and inspect upstream without modifying it.
2. Separate committed upstream state from dirty working-tree changes.
3. Diff from the last reviewed commit.
4. Classify changes as shared, Claude-only, metadata/documentation, or uncertain.
5. Map affected capabilities to Codex and Grok adapters.
6. Present a plan and parity impact before editing.
7. Apply only approved changes.
8. Run structure, fixture, and runtime checks.
9. Update parity and upstream state only after validation.
10. Propose Claude-side compatibility tasks when upstream structure blocked a
    clean port.

Audit/plan is the default mode. Using dirty upstream changes or overwriting an
intentional divergence always requires explicit authorization.

## Migration and adoption

The `project-adoption` plugin audits existing Claude Code projects for Codex and
Grok readiness. It detects:

- missing or agent-specific `AGENTS.md`
- `CLAUDE.md` and Claude-only imports
- installed/referenced Claude plugins
- knowledge, rules, memory links, task files, and worktrees
- hardcoded Claude session and plugin-root assumptions

It reports:

- what already works unchanged
- which Codex/Grok adapters are required
- safe scaffolding changes
- behavior-changing migrations needing approval
- knowledge and memory drift risks

Read-only audit is the default for existing projects.

## Validation strategy

### Mechanical checks

- JSON and YAML validity
- marketplace/manifest consistency
- skill name and metadata validity
- internal path and shared-helper references
- prohibited Claude-only references in Codex/Grok adapters
- upstream state and parity-table consistency
- shell syntax for executable helpers

### Behavioral checks

- fresh Codex marketplace installation and new-session discovery
- fresh Grok skill installation and new-session discovery
- native launch and resume behavior per runtime
- fixture-based adoption and migration audits
- worktree safety, branch protection, and dirty-state handling
- PR readiness and merge safety

### Initial fixture

Use `/Users/robse/Projekte/Webs/muellmann-app.de` first in non-mutating audit
mode. Tests must not deploy, expose secrets, rewrite canonical knowledge, or
alter its active worktrees.

## Implementation order

1. Repository guidance, README, marketplace skeleton, parity ledger, and
   validation foundation
2. Project adoption and knowledge workflows
3. Work-system helpers and native session adapters
4. PR-flow port and review-provider differences
5. One documented manual upstream synchronization
6. `sync-claude-plugins` audit mode, followed by approved apply mode
7. Evaluate `swarm` and any future Claude consolidation

## Non-goals

- moving Claude into this repository during the first implementation
- copying the entire Claude repository and declaring parity
- silently consuming uncommitted upstream work
- enforcing identical behavior where agent capabilities genuinely differ
- renaming stable plugin IDs without a technical reason
- destructive migration of existing project knowledge or worktrees
- coupling releases so one unavailable repository breaks another runtime
