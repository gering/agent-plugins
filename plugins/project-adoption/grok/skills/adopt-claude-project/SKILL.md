---
name: adopt-claude-project
description: Audit an existing Claude-oriented repository for safe Codex and Grok adoption using the native Grok plugin. Use when a project has CLAUDE.md, .claude configuration, agent-specific AGENTS.md guidance, legacy worktrees, installed Claude plugins, or knowledge and memory integrations that must be preserved during migration. Invoke with /adopt-claude-project.
---

# Adopt Claude Project (Grok Native)

This is the **thin** native Grok adapter for the project-adoption plugin.

It delegates the common audit, reporting, and safety semantics to the
agent-neutral reference shipped in `shared/ADOPTION_AUDIT.md` (part of the
plugin). Only Grok-specific installation, path resolution, invocation and
notes live in this adapter file.

Resolve the plugin root with `grok plugin details project-adoption` and use its
`path` value. Then read and follow `<plugin-root>/shared/ADOPTION_AUDIT.md`.
It is the single agent-neutral source for audit, reporting, and safety
semantics. Do not replace it with runtime-specific behavior.

## Grok-specific notes

- Install via native `grok plugin marketplace add` + TUI or direct:
  `grok plugin validate ./plugins/project-adoption`
  `grok plugin install ./plugins/project-adoption`
- The skill appears under `plugin: project-adoption` in `grok inspect`.
- Invoke with `/adopt-claude-project <target>`.
- Validate the installed plugin with `grok plugin validate <dir>` if needed.

**Name collision note:** Before invoking, inspect the matching skill entries
with `grok inspect --json`. If a global
`~/.grok/skills/adopt-claude-project` is also active, do not use the ambiguous
slash command. Run with an isolated `GROK_HOME` that contains only the plugin,
or ask the user to rename or disable the legacy global skill first. Grok 0.2.99
does not expose a documented qualified slash-command syntax.
