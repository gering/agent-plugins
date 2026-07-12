# Migration from Claude

Migration is incremental and non-destructive. Existing Claude configuration is
an input to an adoption audit, not permission to rename or remove files.

The future `project-adoption` plugin will detect `CLAUDE.md`, `AGENTS.md`,
Claude plugin references, `.claude/knowledge/`, `.claude/rules/`, memory links,
`.claude/worktrees/`, `.worktrees/`, and hardcoded Claude CLI or plugin-root
assumptions.

Default behavior for an already configured project is a read-only report:

1. Identify what Codex and Grok can use unchanged.
2. Identify the native adapters still required.
3. Separate safe scaffolding from behavior-changing migration.
4. Show behavior-changing changes before writing.
5. Preserve canonical knowledge, active worktrees, and dirty files.

The first fixture is `muellmann-app.de`. Audits must not deploy it, expose
secrets, rewrite canonical knowledge, or mutate active worktrees.

Phase 2 will document exact commands after the audit implementation and
fixture tests exist.
