# Agent Plugins

`agent-plugins` is the native Codex and Grok companion to
[`gering/claude-plugins`](https://github.com/gering/claude-plugins), which
remains the Claude Code distribution and current feature reference. The two
repositories are independently installable and released separately.

This repository is in early implementation. The read-only
`project-adoption` workflow is installable for both Codex and Grok via their
native marketplaces and manifests; the remaining workflows stay unavailable
until their skills and behavioral checks exist. See the [parity ledger](docs/parity.md) for the detailed status.

## Tracked upstream

- Repository: `gering/claude-plugins`
- Reviewed commit: `9fd980c7e72352fec4e6d143053f7d2d4e1931b2`
- Review date: 2026-07-14
- Upstream versions: knowledge-system 1.8.2, work-system 1.6.0,
  pr-flow 1.2.3, swarm 0.3.1
- Uncommitted upstream changes were detected and explicitly excluded.
- The merged swarm 0.3.0 upstream was reviewed without importing dirty files.
  Later knowledge-only reindex/link fixes through `87917b5` were also reviewed;
  PR #27's pr-flow review-table alignment through `390c1ca` and PR #28's
  finding-fence hardening through `59996c2` were reviewed next. No runtime
  implementation was imported.
  Use `python3 scripts/check-upstream.py` to compare the recorded state with
  the locally cached upstream `origin/main` ref.

## Plugin status

| Plugin | Codex | Grok |
|---|---|---|
| project-adoption | partial | partial |
| knowledge-system | planned | planned |
| work-system | planned | planned |
| pr-flow | planned | planned |

`swarm` is intentionally deferred until the core workflows are stable.

## Codex marketplace

Codex uses `.agents/plugins/marketplace.json` and per-plugin
`.codex-plugin/plugin.json` manifests. The layout follows the current
[OpenAI plugin documentation](https://developers.openai.com/codex/plugins/build)
and was checked with Codex CLI 0.144.1.

Install the current Codex marketplace and adoption plugin:

```bash
codex plugin marketplace add gering/agent-plugins --ref main
codex plugin list
codex plugin add project-adoption@gering-agent-plugins
```

`project-adoption` currently requires a POSIX host. It fails closed on Windows
or any host without descriptor-relative no-follow file I/O rather than reducing
its target-containment guarantees.

For local development, substitute the repository checkout path for
`gering/agent-plugins`. Start a new Codex session after installing or updating,
then invoke `$adopt-claude-project` with an explicit target repository. The
initial audit is read-only; it does not rewrite guidance, knowledge, settings,
or worktrees. Its result reports scanned bytes, exceptional unscanned files,
intentional policy exclusions, ignored Git paths, and pruned directory paths as
separate coverage values. Normal repositories, linked worktrees, and bound
submodules are supported; unbound `--separate-git-dir` layouts fail with an
explicit unsupported-layout error.

## Grok marketplace

Grok Build provides native plugin and marketplace commands. This
repository therefore uses `.grok-plugin/marketplace.json` and per-plugin
`.grok-plugin/plugin.json` manifests instead of relying on Grok's Claude
compatibility discovery.

`project-adoption` is the first installable Grok plugin (thin native adapter
delegating to shared read-only auditor).

The repeatable local flow is:

```bash
# 1. Register the marketplace (local checkout)
grok plugin marketplace add /absolute/path/to/agent-plugins
grok plugin marketplace list

# 2. Marketplace install (via TUI `/marketplace` or after registration)
#    or Direct install from source:
grok plugin validate ./plugins/project-adoption
grok plugin install ./plugins/project-adoption
```

Validate always with a directory path (not plugin name). After install start
a fresh session (or use `grok inspect`) to discover the skill. Invoke with
`/adopt-claude-project <target>` (use qualified name if collisions, e.g.
`project-adoption:adopt-claude-project`).

See [Grok installation](docs/grok-installation.md) for details.

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
