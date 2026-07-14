---
name: adopt-claude-project
description: Audit an existing Claude-oriented repository for safe Codex and Grok adoption using the native Grok plugin. Use when a project has CLAUDE.md, .claude configuration, agent-specific AGENTS.md guidance, legacy worktrees, installed Claude plugins, or knowledge and memory integrations that must be preserved during migration. Invoke with /adopt-claude-project.
---

# Adopt Claude Project (Grok Native)

This is the **thin** native Grok adapter for the project-adoption plugin.

It delegates the common audit, reporting and safety semantics to the
agent-neutral reference shipped in `shared/ADOPTION_AUDIT.md` (part of the
plugin). Only Grok-specific installation, path resolution, invocation and
notes live in this adapter file.

**Common procedure:** Read and follow the instructions in the resolved
`<plugin-root>/shared/ADOPTION_AUDIT.md` (agent-neutral reference shipped
with the plugin).

## Grok-specific notes

- Install via native `grok plugin marketplace add` + TUI or direct:
  `grok plugin validate ./plugins/project-adoption`
  `grok plugin install ./plugins/project-adoption`
- The skill appears under `plugin: project-adoption` in `grok inspect`.
  If name collision with global skills use qualified form e.g.
  `project-adoption:adopt-claude-project`.
- Invoke with `/adopt-claude-project <target>`.
- Uses `GROK_PLUGIN_ROOT` / `GROK_PLUGIN_DATA` (hooks); skills derive paths
  from the loaded SKILL.md location or `grok plugin details`.
- Validate the installed plugin with `grok plugin validate <dir>` if needed.

**Name collision note:** Grok may discover a global `~/.grok/skills/adopt-claude-project`
in addition to the plugin skill. Use the qualified name shown by `grok inspect`
(e.g. `project-adoption:adopt-claude-project`) or run in a fresh `GROK_HOME`
environment (no global skills) to guarantee the plugin version is used.
The dogfood against `muellmann-app.de` was performed with the installed plugin
in an environment without the conflicting global skill.
