---
name: reindex
description: Audit an existing .claude/knowledge index deterministically without changing files. Use when the user asks to reindex, check knowledge quality, validate links or frontmatter, preview maintenance, or confirm that durable project knowledge is structurally consistent.
---

# Check the project knowledge index

Resolve the plugin root from this installed skill path:
`<plugin-root>/skills/reindex/SKILL.md`.

Read and follow `<plugin-root>/shared/KNOWLEDGE_WORKFLOWS.md`. Run its reindex
command with `--check` and the current project as `--root`.

Treat exit status `1` as a successful audit with maintenance findings, not a
tool failure. Present findings grouped by kind. Explicitly say that this native
slice is read-only and that it did not rebuild indexes or backfill metadata.
