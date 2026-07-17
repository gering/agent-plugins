# Agent Plugins

`agent-plugins` is the native Codex and Grok companion to
[`gering/claude-plugins`](https://github.com/gering/claude-plugins), which
remains the Claude Code distribution and current feature reference. The two
repositories are independently installable and released separately.

This repository is in early implementation. The read-only `project-adoption`
workflow and the query/read-only-reindex slice of `knowledge-system` are
installable for both Codex and Grok. Remaining workflows stay unavailable until
their skills and behavioral checks exist. See the [parity ledger](docs/parity.md)
for detailed status.

## Tracked upstream

- Repository: `gering/claude-plugins`
- Reviewed commit: `563daf9c8d38278ee3889cfd337b3c6eed715675`
- Review date: 2026-07-17
- Upstream versions: knowledge-system 1.9.0, work-system 1.8.0,
  pr-flow 1.3.0, swarm 0.4.3
- Uncommitted upstream changes were detected and explicitly excluded.
- New committed upstream changes through `563daf9` were classified read-only;
  dirty sibling paths were excluded. Herdr task-state glyph synchronization and
  Swarm's removal of the retired Grok Composer backend remain unported.
  Use `python3 scripts/check-upstream.py` to compare the recorded state with
  the locally cached upstream `origin/main` ref.

## Plugin status

| Plugin | Codex | Grok |
|---|---|---|
| project-adoption | partial | partial |
| knowledge-system | partial | partial |
| work-system | planned | planned |
| pr-flow | planned | planned |

`swarm` is intentionally deferred until the core workflows are stable.

## Codex marketplace

Codex uses `.agents/plugins/marketplace.json` and per-plugin
`.codex-plugin/plugin.json` manifests. The layout follows the current
[OpenAI plugin documentation](https://developers.openai.com/codex/plugins/build)
and was checked with Codex CLI 0.144.4.

Install the current Codex marketplace and available plugins:

```bash
codex plugin marketplace add gering/agent-plugins --ref main
codex plugin list
codex plugin add project-adoption@gering-agent-plugins
codex plugin add knowledge-system@gering-agent-plugins
```

`project-adoption` and `knowledge-system` currently require a POSIX host. They
fail closed on Windows or any host without descriptor-relative no-follow file
I/O rather than reducing their target-containment guarantees.

For local development, substitute the repository checkout path for
`gering/agent-plugins`. Start a new Codex session after installing or updating,
then invoke `$adopt-claude-project` with an explicit target repository. The
initial audit is read-only; it does not rewrite guidance, knowledge, settings,
or worktrees. Its result reports scanned bytes, exceptional unscanned files,
intentional policy exclusions, ignored Git paths, and pruned directory paths as
separate coverage values. Normal repositories, linked worktrees, and bound
submodules are supported; unbound `--separate-git-dir` layouts fail with an
explicit unsupported-layout error.

Invoke `$query` to rank and read up to three matching files from
`.claude/knowledge/`. Invoke `$reindex` for a deterministic read-only index,
frontmatter, and link audit. This slice never writes the knowledge store and
does not silently fall back to source-code exploration.

## Grok marketplace

Grok Build provides native plugin and marketplace commands. This
repository therefore uses `.grok-plugin/marketplace.json` and per-plugin
`.grok-plugin/plugin.json` manifests instead of relying on Grok's Claude
compatibility discovery.

`project-adoption` and `knowledge-system` are installable Grok plugins with thin
native adapters over shared read-only helpers.

The repeatable local flow is:

```bash
# 1. Register the marketplace (local checkout)
grok plugin marketplace add /absolute/path/to/agent-plugins
grok plugin marketplace list

# 2. Marketplace install (open `/plugins`, then use the Marketplace tab)
#    or Direct install from source:
grok plugin validate ./plugins/project-adoption
grok plugin install ./plugins/project-adoption
grok plugin validate ./plugins/knowledge-system
grok plugin install ./plugins/knowledge-system
```

Validate always with a directory path (not plugin name). After install start
a fresh session (or use `grok inspect`) to discover the skill. Invoke with
`/adopt-claude-project <target>`, `/query <question>`, or `/reindex`. If a global
skill has the same name, use an isolated `GROK_HOME` or rename/disable the
legacy skill before invoking.

See [Grok installation](docs/grok-installation.md) for validation and update
details.

## Verify the checkout

```bash
python3 scripts/check-structure.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check-upstream.py  # exits 1 when cached upstream state differs
```

This check validates manifests, marketplace relationships, upstream state,
parity coverage, and forbidden Claude-only references in native adapters. The
regression suite verifies that known-invalid states are rejected.

## Design and migration

- [Architecture](docs/architecture.md)
- [Parity ledger](docs/parity.md)
- [Migration from Claude](docs/migration-from-claude.md)
- [Claude compatibility backlog](docs/claude-compatibility-backlog.md)

Claude-side changes are proposed in the compatibility backlog and implemented
only in a separate Claude-repository task or pull request.
