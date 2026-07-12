#!/usr/bin/env python3
"""Validate the Phase 1 marketplace, manifests, parity, and provenance."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ("project-adoption", "knowledge-system", "work-system", "pr-flow")
ALLOWED_INSTALLATION = {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}
ALLOWED_AUTHENTICATION = {"ON_INSTALL", "ON_USE"}
FORBIDDEN_ADAPTER_TEXT = (
    "${CLAUDE_PLUGIN_ROOT}",
    ".claude-plugin",
    "claude --continue",
    "claude --resume",
)

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def load_json(relative: str) -> Any | None:
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing required file: {relative}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid JSON in {relative}: {exc}")
        return None


def validate_manifest(plugin: str, runtime: str) -> dict[str, Any] | None:
    relative = f"plugins/{plugin}/.{runtime}-plugin/plugin.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return None
    if data.get("name") != plugin:
        fail(f"{relative}: name must equal plugin directory {plugin!r}")
    version = data.get("version")
    if not isinstance(version, str) or not re.fullmatch(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?",
        version,
    ):
        fail(f"{relative}: version must be strict semver")
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        fail(f"{relative}: description is required")
    author = data.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str):
        fail(f"{relative}: author.name is required")
    return data


def validate_codex_marketplace() -> None:
    relative = ".agents/plugins/marketplace.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return
    if data.get("name") != "gering-agent-plugins":
        fail(f"{relative}: unexpected marketplace name")
    entries = data.get("plugins")
    if not isinstance(entries, list):
        fail(f"{relative}: plugins must be an array")
        return
    by_name = {
        entry.get("name"): entry for entry in entries if isinstance(entry, dict)
    }
    if set(by_name) != set(PLUGINS):
        fail(f"{relative}: entries must match {', '.join(PLUGINS)}")
    for plugin in PLUGINS:
        entry = by_name.get(plugin)
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        expected_path = f"./plugins/{plugin}"
        if source != {"source": "local", "path": expected_path}:
            fail(f"{relative}: {plugin} must use local source {expected_path}")
        policy = entry.get("policy")
        if not isinstance(policy, dict):
            fail(f"{relative}: {plugin} is missing policy")
            continue
        if policy.get("installation") not in ALLOWED_INSTALLATION:
            fail(f"{relative}: {plugin} has invalid installation policy")
        if policy.get("authentication") not in ALLOWED_AUTHENTICATION:
            fail(f"{relative}: {plugin} has invalid authentication policy")
        if not isinstance(entry.get("category"), str):
            fail(f"{relative}: {plugin} is missing category")


def validate_grok_marketplace() -> None:
    relative = ".grok-plugin/marketplace.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return
    if data.get("name") != "gering-agent-plugins":
        fail(f"{relative}: unexpected marketplace name")
    entries = data.get("plugins")
    if entries != []:
        fail(f"{relative}: Phase 1 must not advertise unfinished Grok plugins")


def validate_upstream() -> None:
    relative = ".agents/upstream/claude-plugins.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return
    upstream = data.get("upstream")
    if not isinstance(upstream, dict):
        fail(f"{relative}: upstream object is required")
        return
    commit = upstream.get("last_reviewed_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        fail(f"{relative}: last_reviewed_commit must be a full Git SHA")
    if upstream.get("dirty_worktree_excluded") is not True:
        fail(f"{relative}: dirty_worktree_excluded must be true")
    plugins = data.get("plugins")
    if not isinstance(plugins, dict) or set(plugins) != set(PLUGINS):
        fail(f"{relative}: plugin state must match the Phase 1 plugin set")


def validate_adapter_boundaries() -> None:
    for plugin in PLUGINS:
        for runtime in ("codex", "grok"):
            adapter = ROOT / "plugins" / plugin / runtime
            if not adapter.exists():
                continue
            for path in adapter.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for forbidden in FORBIDDEN_ADAPTER_TEXT:
                    if forbidden in text:
                        fail(
                            f"{path.relative_to(ROOT)}: native adapter contains "
                            f"forbidden Claude-only reference {forbidden!r}"
                        )


def validate_docs() -> None:
    required = (
        "AGENTS.md",
        "README.md",
        "docs/architecture.md",
        "docs/parity.md",
        "docs/migration-from-claude.md",
        "docs/claude-compatibility-backlog.md",
        "docs/grok-installation.md",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")
    parity_path = ROOT / "docs/parity.md"
    if parity_path.is_file():
        parity = parity_path.read_text(encoding="utf-8")
        for plugin in (*PLUGINS, "swarm"):
            if plugin not in parity:
                fail(f"docs/parity.md: missing status for {plugin}")
        if "f443fbb24fbcc06853de666a3737fbebe3064f1f" not in parity:
            fail("docs/parity.md: missing full reviewed upstream commit")


def main() -> int:
    validate_docs()
    manifests: dict[tuple[str, str], dict[str, Any] | None] = {}
    for plugin in PLUGINS:
        manifests[(plugin, "codex")] = validate_manifest(plugin, "codex")
        manifests[(plugin, "grok")] = validate_manifest(plugin, "grok")
        codex = manifests[(plugin, "codex")]
        grok = manifests[(plugin, "grok")]
        if codex and grok and codex.get("version") != grok.get("version"):
            fail(f"{plugin}: Codex and Grok manifest versions differ")
    validate_codex_marketplace()
    validate_grok_marketplace()
    validate_upstream()
    validate_adapter_boundaries()

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"structure check failed with {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("structure check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
