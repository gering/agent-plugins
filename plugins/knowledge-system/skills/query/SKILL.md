---
name: query
description: Search versioned project knowledge in .claude/knowledge without reading source code or runtime memory. Use when the user asks how something works here, what the project knows about a topic, or wants documented architecture, feature, deployment, or operational context with file references.
---

# Query project knowledge

Resolve the plugin root from this installed skill path:
`<plugin-root>/skills/query/SKILL.md`.

Read and follow `<plugin-root>/shared/KNOWLEDGE_WORKFLOWS.md`. Run its query
command with the user's question and the current project as `--root`. Read only
the top matching knowledge files needed to answer, never more than three.
Place helper options before the documented `--` separator so questions that
begin with `-` remain positional query text.

Return a concise answer followed by the consulted `.claude/knowledge/` paths.
If no match exists, state that the versioned knowledge has a gap. Do not search
the wider repository unless the user separately approves source exploration.
