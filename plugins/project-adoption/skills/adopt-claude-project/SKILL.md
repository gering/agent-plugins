---
name: adopt-claude-project
description: Audit an existing Claude-oriented repository for safe Codex and Grok adoption. Use when a project has CLAUDE.md, .claude configuration, agent-specific AGENTS.md guidance, legacy worktrees, installed Claude plugins, or knowledge and memory integrations that must be preserved during migration.
---

# Adopt Claude Project

This is the thin native Codex adapter for the project-adoption plugin.

Resolve the plugin root from this installed skill path:
`<plugin-root>/skills/adopt-claude-project/SKILL.md`.

Read and follow `<plugin-root>/shared/ADOPTION_AUDIT.md`. It is the single
agent-neutral source for audit, reporting, and safety semantics. Do not replace
it with runtime-specific behavior.
