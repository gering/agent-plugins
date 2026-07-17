# Native knowledge workflows

Durable project knowledge remains canonical in the versioned
`.claude/knowledge/` compatibility location. Codex and Grok memory stores may
hold preferences or local context, but they are not a substitute for these
files.

The native helper requires POSIX descriptor-relative, nonblocking, no-follow
I/O with file-identity checks and fails closed when that containment guarantee
is unavailable.

## Query

Run the shared helper from the target project:

```bash
python3 <plugin-root>/shared/knowledge_tool.py query "<question>" --root .
```

The helper reads only Markdown files below `.claude/knowledge/`, tokenizes the
question, and ranks matches from document bodies, titles, extension-free paths,
and live index descriptions. Frontmatter and code examples are not query
content. It returns paths and titles rather than file contents. Read at most the
top three matching files, answer concisely, and cite every consulted path. Do
not fall back to source-code exploration silently. If documented knowledge has
a gap, say so and ask before broadening the scope.

## Reindex check

This first native reindex slice is deliberately read-only:

```bash
python3 <plugin-root>/shared/knowledge_tool.py reindex --check --root .
```

It checks root-index coverage, stale index entries, missing provenance fields,
non-empty and calendar-valid frontmatter values, Markdown links, wikilinks,
size limits, UTF-8, and descriptor-anchored race/symlink containment. Link and
index checks ignore frontmatter and Markdown code examples. Exit status `0`
means clean, `1` means maintenance findings, and `2` means the inspection could
not complete safely.

Do not edit the knowledge store while following this workflow. Index and
frontmatter writes, semantic duplicate/staleness analysis, cross-link
proposals, and the run log belong to the later approved write-capable slice
with `curate`.
