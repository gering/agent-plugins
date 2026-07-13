# Bootstrap Codex and Grok Plugin Marketplace

## Goal

Build `agent-plugins` as the installable Codex and Grok companion to
`gering/claude-plugins`. Keep Claude Code in its existing repository during the
first milestones, while documenting and automating behavioral parity across all
three agents.

The new repository must provide native Codex and Grok integrations rather than
running Claude-oriented skills through undocumented substitutions.

## Related repositories

- Claude reference: `/Users/robse/Projekte/Plugins/claude-plugins`
- Codex/Grok implementation: `/Users/robse/Projekte/Plugins/agent-plugins`
- Initial integration fixture: `/Users/robse/Projekte/Webs/muellmann-app.de`

Add reciprocal README links:

- `agent-plugins` must link to `gering/claude-plugins` as the current Claude
  distribution and feature reference.
- `claude-plugins` should receive a separate task/PR linking to `agent-plugins`
  as the Codex/Grok companion.
- Do not edit `claude-plugins` from this repository or silently couple releases.

## Product boundary

### In scope initially

- Codex marketplace, plugin manifests, skills, scripts, and installation flow
- Grok skills, adapters, installation flow, and herdr session integration
- Shared behavioral specifications and agent-neutral helpers
- Parity tracking against `claude-plugins`
- Migration/adoption of existing Claude Code projects

### Out of scope initially

- Moving the Claude marketplace into this repository
- Replacing or archiving `gering/claude-plugins`
- Big-bang migration of existing projects
- Claiming parity without executable checks or documented evidence

Claude remains a design input and compatibility target. It is not an initial
runtime shipped by this repository.

## Core architecture

Prefer a shared semantic core with thin runtime adapters:

```text
agent-plugins/
  AGENTS.md
  README.md
  .agents/plugins/marketplace.json
  docs/
    architecture.md
    parity.md
    migration-from-claude.md
  scripts/
    check-structure.*
    check-upstream.*
  plugins/
    knowledge-system/
      shared/
      codex/
      grok/
    work-system/
      shared/
      codex/
      grok/
    pr-flow/
      shared/
      codex/
      grok/
    project-adoption/
      shared/
      codex/
      grok/
```

The exact layout may change after a documented architecture review. Preserve
these invariants:

- `AGENTS.md` is agent-neutral because both Codex and Grok consume it.
- Host-specific launch, resume, review, prompt, and installation behavior lives
  in adapter skills or scripts.
- Shared scripts must not depend on `${CLAUDE_PLUGIN_ROOT}` or a Claude-only
  tool API.
- Codex plugins use `.codex-plugin/plugin.json` and a Codex marketplace.
- Grok must have an explicit, repeatable installation mechanism; do not assume
  that Claude plugin discovery is always available.
- Stable plugin and skill names are preferred when their semantics remain
  equivalent.

## Plugin scope

Port in this order:

1. `project-adoption`
   - Provide an `adopt-claude-project` skill for Codex and Grok.
   - Audit `CLAUDE.md`, `AGENTS.md`, installed Claude plugins, worktrees,
     knowledge, rules, and memory integration.
   - Default to read-only reporting when an existing project is already
     configured.
   - Apply only safe changes automatically; show behavior-changing migrations
     before writing.
2. `knowledge-system`
   - Keep durable project knowledge versioned and agent-neutral.
   - Treat native Claude, Codex, and Grok memories as preference/local-state
     stores, not the canonical project database.
   - Support existing `.claude/knowledge/` projects without destructive moves.
3. `work-system`
   - Preserve task, branch, worktree, and main-session/worktree-session
     semantics.
   - Use native launch/resume commands for each agent.
4. `pr-flow`
   - Preserve readiness, rebase, review, and merge safety.
   - Separate local Codex/Grok review from optional GitHub `@claude review`.
5. Evaluate `swarm` after the core workflow is stable.

## Claude compatibility work

While porting, record changes that would make the Claude implementation easier
to share or compare. Do not patch the Claude repository directly. Instead:

- Add proposed Claude-side changes to `docs/claude-compatibility-backlog.md`.
- Each item must include affected Claude files, motivation, expected compatibility
  gain, and whether behavior changes for existing Claude users.
- Create corresponding task files in `claude-plugins/tasks/` only in a separate
  Claude-repository session/branch.
- Prefer neutral helper extraction and explicit path parameters over changes that
  merely rename Claude concepts.

Examples of likely Claude-side tasks:

- accept `.worktrees/` alongside `.claude/worktrees/`
- make reusable scripts independent of `${CLAUDE_PLUGIN_ROOT}` where practical
- separate workflow semantics from Claude session-launch behavior
- emit a machine-readable plugin capability inventory
- document which GitHub review steps are specifically tied to `@claude`

## Parity and divergence tracking

Create `docs/parity.md` as a user-visible status page and link it prominently
from `README.md`.

For every source plugin and skill, record:

| Field | Meaning |
|---|---|
| Claude source | Plugin version and source commit reviewed |
| Codex status | missing, planned, partial, parity, or intentionally divergent |
| Grok status | missing, planned, partial, parity, or intentionally divergent |
| Last sync | Date and upstream commit |
| Differences | User-visible or operational differences |
| Evidence | Tests, fixtures, or review links supporting the status |

The main README must summarize:

- the relationship between both repositories
- current upstream Claude commit/version tracked
- which plugins are installable for Codex and Grok
- known differences and unsupported features
- how to install, update, and verify each runtime
- where compatibility work is tracked

Never use a single repository-wide "fully compatible" badge. Report parity per
plugin and per agent.

## Upstream synchronization skill

After the first manual port establishes the mapping, implement a
`sync-claude-plugins` skill in `agent-plugins`.

The skill must:

1. Locate or accept the Claude repository and determine its current commit.
2. Read the last imported upstream commit from a tracked state file.
3. Summarize upstream commits and changed plugin files since that point.
4. Map changes to Codex/Grok plugins and classify them:
   - shared semantic change
   - Claude-only runtime change
   - documentation/metadata change
   - uncertain and requires review
5. Produce a sync plan and parity impact report before editing.
6. Port approved changes using the native adapter boundaries.
7. Run structure checks and targeted runtime tests.
8. Update `docs/parity.md`, the tracked upstream state, and release notes only
   after validation succeeds.
9. Propose Claude-side compatibility tasks when upstream structure prevented a
   clean port.

Safety constraints:

- Default mode is read-only audit/plan.
- Never copy the dirty working tree from `claude-plugins` implicitly.
- Require an explicit option to use uncommitted upstream changes.
- Never overwrite intentional Codex/Grok divergences without confirmation.
- Never bump parity status solely because files were copied.
- Preserve provenance: upstream commit, source files, and decisions.

Suggested state file:

```text
.agents/upstream/claude-plugins.json
```

The format should track the upstream URL/path, last reviewed commit, per-plugin
source versions, and intentional divergence identifiers.

## Migration and project adoption

Provide a safe audit for representative Claude Code projects. Detect at least:

- `CLAUDE.md` with or without `AGENTS.md`
- Grok-specific `AGENTS.md` content that would misdirect Codex
- `.claude/knowledge/`, `.claude/rules/`, and Claude Auto-Memory links
- `.claude/worktrees/` and future `.worktrees/`
- installed or referenced `work-system`, `pr-flow`, and `knowledge-system`
- hardcoded Claude CLI commands and plugin-root variables

Use `muellmann-app.de` as the first read-only fixture. Its canonical knowledge
must remain intact and no production deployment may be triggered by tests.

## Validation requirements

- Validate Codex behavior using current official Codex documentation and the
  installed Codex CLI, not inferred Claude behavior.
- Validate Grok behavior in a real Grok session for TUI launch/resume and skill
  discovery assumptions.
- Add deterministic structure checks for manifests, marketplace entries, skill
  metadata, internal references, and version/parity state.
- Add fixture-based tests for migration audits and upstream change
  classification.
- Test installation from the local checkout in a fresh Codex session.
- Test the documented Grok installation flow in a fresh Grok session.
- Keep all destructive or external actions behind explicit confirmation.

## Initial implementation plan

### Phase 1: Repository foundation

- [x] Review and finalize `docs/architecture.md` for the Codex/Grok-only scope
- [x] Add agent-neutral `AGENTS.md`
- [x] Add README with reciprocal repository links and honest status reporting
- [x] Add Codex marketplace skeleton and validation
- [x] Define the Grok distribution/install mechanism
- [x] Add parity and Claude compatibility backlog documents
- [x] Record the initial upstream Claude commit without importing dirty changes

### Phase 2: Adoption and knowledge

- [x] Implement Codex `adopt-claude-project`
- [x] Implement Grok adoption adapter (thin native using .grok-plugin + grok/skills/ + shared auditor; no Claude literals)
- [ ] Port knowledge query/curate/reindex behavior
- [x] Validate against `muellmann-app.de` in read-only mode

### Phase 3: Work and PR workflows

- [ ] Port work-system semantics and neutral helpers
- [ ] Implement native Codex launch/resume behavior
- [ ] Implement native Grok/herdr launch/resume behavior
- [ ] Port PR readiness and merge safety
- [ ] Document deliberate GitHub review differences

### Phase 4: Upstream sync

- [ ] Perform and document one manual upstream sync
- [ ] Define the upstream state schema and mapping rules
- [ ] Implement `sync-claude-plugins` in audit mode
- [ ] Add approved port/apply mode
- [ ] Verify that parity docs and compatibility tasks are updated atomically

## Definition of done

- Codex can install the local marketplace cleanly and discover the intended
  skills in a new session.
- Grok has a documented, repeatable installation and discovers its intended
  skills in a new session.
- README and parity documentation accurately link and compare both repositories.
- At least `project-adoption`, `knowledge-system`, and `work-system` have a
  documented Codex/Grok status.
- `muellmann-app.de` passes a non-mutating adoption audit.
- A manual upstream change has been ported with recorded provenance.
- `sync-claude-plugins` can detect newer Claude changes, explain their impact,
  and produce a safe plan without modifying files by default.
- Claude-side compatibility proposals are captured as actionable tasks rather
  than silently changing the reference repository.

## Kickoff instructions

1. Read this file and `docs/architecture.md` completely.
2. Inspect the committed state of `claude-plugins`; separately report its dirty
   working tree and do not import those changes by default.
3. Verify current Codex plugin/marketplace requirements from official sources.
4. Audit the assumptions in the current architecture document against the new
   Codex/Grok-only product boundary.
5. Propose the Phase 1 file tree and first commit boundaries before implementing.
