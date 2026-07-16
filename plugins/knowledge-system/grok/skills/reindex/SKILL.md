---
name: reindex
description: Audit an existing .claude/knowledge index deterministically through the native Grok plugin without changing files. Use when the user asks to reindex, check knowledge quality, validate links or frontmatter, or preview maintenance. Invoke with /reindex.
---

# Check the project knowledge index (Grok native)

Resolve the plugin root with `grok plugin details knowledge-system` and use its
`path` value. Read and follow
`<plugin-root>/shared/KNOWLEDGE_WORKFLOWS.md`, then run its reindex command with
`--check` and the current project as `--root`.

Exit status `1` means the audit completed with maintenance findings. Group the
findings by kind and state that the check was read-only. Do not rebuild indexes
or backfill frontmatter in this slice.
