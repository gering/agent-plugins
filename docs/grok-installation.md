# Grok installation

Grok Build 0.2.99 was inspected on 2026-07-14. It exposes native `plugin
install`, `plugin marketplace`, `plugin validate`, `--continue`, and `--resume`
interfaces. This repository uses those native surfaces.

## Local marketplace

Register a checkout once:

```bash
grok plugin marketplace add /absolute/path/to/agent-plugins
grok plugin marketplace list
```

Refresh a registered marketplace after pulling changes:

```bash
grok plugin marketplace update
```

`project-adoption` is advertised once its manifest, skills and runtime
behavior pass validation.

## Direct development installation

Validate before installation (always use directory path):

```bash
grok plugin validate ./plugins/project-adoption
grok plugin install ./plugins/project-adoption
grok plugin details project-adoption
```

Marketplace installation is typically done via the TUI (`/marketplace` tab)
after registering the source. See README for examples.

Do not use `--trust` in the documented default flow. Users should see Grok's
trust confirmation for a new local or Git source.

Start a fresh Grok session to verify skill discovery. Launch and resume tests
must exercise Grok-native commands; herdr-specific behavior belongs in the Grok
adapter and is tested separately.

## Compatibility bridge

Grok may also discover Claude-compatible components already installed on a
machine. That bridge is useful during migration but is not a supported install
mechanism for this repository. A clean machine must be able to use the native
Grok marketplace without `claude-plugins` being installed.
