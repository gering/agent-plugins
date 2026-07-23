---
name: query
description: Search versioned project knowledge in .claude/knowledge using the native Grok plugin without reading source code or runtime memory. Use when the user asks how something works here, what the project knows about a topic, or wants documented context with file references. Invoke with /query.
---

# Query project knowledge (Grok native)

Resolve the plugin root with `grok plugin details knowledge-system` and use its
`path` value. Read and follow
`<plugin-root>/shared/KNOWLEDGE_WORKFLOWS.md`, then run its query command with
the user's question and the current project as `--root`.
Place helper options before the documented `--` separator so questions that
begin with `-` remain positional query text.

Read only the top matching knowledge files needed to answer, never more than
three. Return a concise answer with consulted paths. Do not broaden the search
to source code unless the user separately approves it.
