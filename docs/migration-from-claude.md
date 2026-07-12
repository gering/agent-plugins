# Migration from Claude

Migration is incremental and non-destructive. Existing Claude configuration is
an input to an adoption audit, not permission to rename or remove files.

The Codex `project-adoption` plugin detects `CLAUDE.md`, `AGENTS.md`, Claude
plugin references, `.claude/knowledge/`, `.claude/rules/`, project-local memory
links/helpers, `.claude/worktrees/`, `.worktrees/`, and hardcoded Claude CLI or
plugin-root assumptions. The Grok adapter remains planned.

Default behavior for an already configured project is a read-only report:

1. Identify what Codex and Grok can use unchanged.
2. Identify the native adapters still required.
3. Separate safe scaffolding from behavior-changing migration.
4. Show behavior-changing changes before writing.
5. Preserve canonical knowledge, active worktrees, and dirty files.

The first fixture is `muellmann-app.de`. Audits must not deploy it, expose
secrets, rewrite canonical knowledge, or mutate active worktrees.

Install and run the Codex audit from a new session:

```bash
codex plugin marketplace add gering/agent-plugins --ref main
codex plugin add project-adoption@gering-agent-plugins
```

Invoke `$adopt-claude-project` with an explicit target repository. Target
guidance is treated as audit data, not session instructions. The current slice
only reports; any migration or write still requires a separate explicit
approval.
