# Native knowledge workflows

Durable project knowledge remains canonical in the versioned
`.claude/knowledge/` compatibility location. Codex and Grok memory stores may
hold preferences or local context, but they are not a substitute for these
files.

The native helper requires POSIX descriptor-relative, nonblocking, no-follow
I/O with bounded directory snapshots plus file and directory signature checks.
It fails closed when that containment guarantee is unavailable or a scanned
directory changes during inspection.

## Query

Run the shared helper from the target project:

```bash
python3 <plugin-root>/shared/knowledge_tool.py query --root . -- "<question>"
```

Put all helper options before `--`; the separator keeps questions beginning
with `-`, including `--help`, from being interpreted as helper options.

The helper reads only Markdown files below `.claude/knowledge/`, tokenizes the
question, and ranks matches from document bodies, titles, extension-free paths,
and live index descriptions. Frontmatter plus fenced and indented block-code
examples are not query content; inline identifiers remain searchable. It
returns paths and titles rather than file contents. Read at most the top three
matching files, answer concisely, and cite every consulted path. Do not fall
back to source-code exploration silently. If documented knowledge has a gap,
say so and ask before broadening the scope.

## Reindex check

This first native reindex slice is deliberately read-only:

```bash
python3 <plugin-root>/shared/knowledge_tool.py reindex --check --root .
```

It checks root-index coverage, stale index entries, required provenance keys,
selected non-empty values, calendar-valid dates, inline and reference-style
Markdown links, wikilinks, size and entry-count limits, UTF-8, and
descriptor-anchored race/symlink containment. `createdFrom` and `updatedFrom`
must exist but may be empty when their origin is unresolved; `title`, all three
dates, `pluginVersion`, and `prime` must be non-empty. Link and index checks
ignore frontmatter, HTML comments, and Markdown block-code examples. Finding
counts cover the complete audit while serialized details are bounded and report
their truncation explicitly. Exit status `0` means clean, `1` means maintenance
findings, and `2` means the inspection could not complete safely.

Do not edit the knowledge store while following this workflow. Index and
frontmatter writes, semantic duplicate/staleness analysis, cross-link
proposals, and the run log belong to the later approved write-capable slice
with `curate`.
