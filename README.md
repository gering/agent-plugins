# Agent Plugins

`agent-plugins` is the native Codex and Grok companion to
[`gering/claude-plugins`](https://github.com/gering/claude-plugins), which
remains the Claude Code distribution and current feature reference. The two
repositories are independently installable and released separately.

This repository is in its foundation phase. Its manifests and marketplace
skeletons are present, but no workflow plugin is installable yet. Availability
will be enabled per runtime only after its skills and behavioral checks exist.
See the [parity ledger](docs/parity.md) for the detailed status.

## Tracked upstream

- Repository: `gering/claude-plugins`
- Reviewed commit: `ee7bb2db650fb790530c7310be4b317a3e49bb56`
- Review date: 2026-07-12
- Upstream versions: knowledge-system 1.8.2, work-system 1.6.0,
  pr-flow 1.2.2, swarm 0.3.0
- Uncommitted upstream changes were detected and explicitly excluded.
- The merged swarm 0.3.0 upstream was reviewed without importing dirty files.
  Use `python3 scripts/check-upstream.py` to compare the recorded state with
  the locally cached upstream `origin/main` ref.

## Plugin status

| Plugin | Codex | Grok |
|---|---|---|
| project-adoption | planned | planned |
| knowledge-system | planned | planned |
| work-system | planned | planned |
| pr-flow | planned | planned |

`swarm` is intentionally deferred until the core workflows are stable.

## Codex marketplace

Codex uses `.agents/plugins/marketplace.json` and per-plugin
`.codex-plugin/plugin.json` manifests. The layout follows the current
[OpenAI plugin documentation](https://developers.openai.com/codex/plugins/build)
and was checked with Codex CLI 0.144.1.

Once the marketplace file is writable and the first plugin becomes available:

```bash
codex plugin marketplace add /path/to/agent-plugins
codex plugin list
codex plugin add project-adoption@gering-agent-plugins
```

Start a new Codex session after installing or updating a plugin.

## Grok marketplace

Grok Build 0.2.93 provides native plugin and marketplace commands. This
repository therefore uses `.grok-plugin/marketplace.json` and per-plugin
`.grok-plugin/plugin.json` manifests instead of relying on Grok's Claude
compatibility discovery.

The repeatable local flow is:

```bash
grok plugin marketplace add /path/to/agent-plugins
grok plugin marketplace list
grok plugin validate plugins/project-adoption
```

The Phase 1 Grok marketplace intentionally contains no installable entries.
When an adapter is ready, install it from the registered marketplace or test a
local plugin directly with `grok plugin install ./plugins/<plugin>`.

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
