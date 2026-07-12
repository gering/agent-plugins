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
ALLOWED_AUTHENTICATION = {"ON_INSTALL", "ON_USE"}
ALLOWED_PARITY_STATES = {
    "missing",
    "planned",
    "partial",
    "parity",
    "intentional-divergence",
}
SEMVER = re.compile(
    r"^(?:0|[1-9]\d*)\."
    r"(?:0|[1-9]\d*)\."
    r"(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
FORBIDDEN_ADAPTER_PATTERNS = (
    ("Claude plugin root", re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}")),
    ("Claude manifest path", re.compile(r"\.claude-plugin")),
    (
        "Claude session command",
        re.compile(r"(?<![\w-])claude\s+(?:--continue|--resume|--print|-c\b|-r\b|-p\b)"),
    ),
    ("Claude Workflow tool", re.compile(r"\bWorkflow\s*\(")),
    ("Claude slash-command tool", re.compile(r"\bSlashCommand\s*\(")),
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
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        fail(f"{relative}: version must be strict semver")
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        fail(f"{relative}: description is required")
    author = data.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str):
        fail(f"{relative}: author.name is required")
    if data.get("license") != "MIT":
        fail(f"{relative}: license must be MIT")
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
    if any(not isinstance(entry, dict) for entry in entries):
        fail(f"{relative}: every plugin entry must be an object")
        return
    names = [entry.get("name") for entry in entries]
    if any(not isinstance(name, str) for name in names):
        fail(f"{relative}: every plugin name must be a string")
        return
    if len(names) != len(set(names)):
        fail(f"{relative}: duplicate plugin names are not allowed")
    by_name = {entry.get("name"): entry for entry in entries}
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
        if policy.get("installation") != "NOT_AVAILABLE":
            fail(
                f"{relative}: unfinished Phase 1 plugin {plugin} must use "
                "installation policy NOT_AVAILABLE"
            )
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
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        fail(f"{relative}: description is required")
    owner = data.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str):
        fail(f"{relative}: owner.name is required")
    entries = data.get("plugins")
    if entries != []:
        fail(f"{relative}: Phase 1 must not advertise unfinished Grok plugins")


def validate_upstream() -> dict[str, Any] | None:
    relative = ".agents/upstream/claude-plugins.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != 1:
        fail(f"{relative}: schema_version must be 1")
    upstream = data.get("upstream")
    if not isinstance(upstream, dict):
        fail(f"{relative}: upstream object is required")
        return data
    if upstream.get("repository") != "https://github.com/gering/claude-plugins.git":
        fail(f"{relative}: unexpected upstream repository")
    local_hint = upstream.get("local_path_hint")
    if not isinstance(local_hint, str) or Path(local_hint).is_absolute():
        fail(f"{relative}: local_path_hint must be a relative path")
    commit = upstream.get("last_reviewed_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        fail(f"{relative}: last_reviewed_commit must be a full Git SHA")
    date = upstream.get("last_reviewed_date")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        fail(f"{relative}: last_reviewed_date must use YYYY-MM-DD")
    if not isinstance(upstream.get("dirty_worktree_excluded"), bool):
        fail(f"{relative}: dirty_worktree_excluded must be boolean")
    plugins = data.get("plugins")
    if not isinstance(plugins, dict) or set(plugins) != set(PLUGINS):
        fail(f"{relative}: plugin state must match the Phase 1 plugin set")
        return data
    for plugin, state in plugins.items():
        if not isinstance(state, dict):
            fail(f"{relative}: {plugin} state must be an object")
            continue
        source_plugin = state.get("source_plugin")
        source_version = state.get("source_version")
        if plugin == "project-adoption":
            if source_plugin is not None or source_version is not None:
                fail(f"{relative}: project-adoption must not claim a Claude source")
        else:
            if source_plugin != plugin:
                fail(f"{relative}: {plugin}.source_plugin must equal {plugin!r}")
            if not isinstance(source_version, str) or not SEMVER.fullmatch(source_version):
                fail(f"{relative}: {plugin}.source_version must be strict semver")
        capabilities = state.get("imported_capabilities")
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) for item in capabilities
        ):
            fail(f"{relative}: {plugin}.imported_capabilities must be strings")
    if not isinstance(data.get("intentional_divergences"), list):
        fail(f"{relative}: intentional_divergences must be an array")
    return data


def validate_adapter_boundaries() -> None:
    for plugin in PLUGINS:
        candidates = [
            ROOT / "plugins" / plugin / ".codex-plugin" / "plugin.json",
            ROOT / "plugins" / plugin / ".grok-plugin" / "plugin.json",
        ]
        for runtime in ("codex", "grok"):
            adapter = ROOT / "plugins" / plugin / runtime
            if adapter.exists():
                candidates.extend(path for path in adapter.rglob("*") if path.is_file())
        for component in ("skills", "agents", "commands", "hooks"):
            root_component = ROOT / "plugins" / plugin / component
            if root_component.exists():
                candidates.extend(
                    path for path in root_component.rglob("*") if path.is_file()
                )
        for path in candidates:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in FORBIDDEN_ADAPTER_PATTERNS:
                if pattern.search(text):
                    fail(
                        f"{path.relative_to(ROOT)}: native runtime file contains "
                        f"forbidden {label}"
                    )


def validate_docs(upstream_state: dict[str, Any] | None) -> None:
    required = (
        "AGENTS.md",
        "README.md",
        "docs/architecture.md",
        "docs/parity.md",
        "docs/migration-from-claude.md",
        "docs/claude-compatibility-backlog.md",
        "docs/grok-installation.md",
        "LICENSE",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")
    parity_path = ROOT / "docs/parity.md"
    readme_path = ROOT / "README.md"
    if not parity_path.is_file() or not readme_path.is_file():
        return
    parity = parity_path.read_text(encoding="utf-8")
    readme = readme_path.read_text(encoding="utf-8")
    rows: dict[str, list[str]] = {}
    for line in parity.splitlines():
        columns = [column.strip() for column in line.split("|")[1:-1]]
        if columns and columns[0] in (*PLUGINS, "swarm"):
            if columns[0] in rows:
                fail(f"docs/parity.md: duplicate status row for {columns[0]}")
            rows[columns[0]] = columns
    if set(rows) != {*PLUGINS, "swarm"}:
        fail("docs/parity.md: status rows must cover every Phase 1 plugin and swarm")
    for plugin, columns in rows.items():
        if len(columns) != 7:
            fail(f"docs/parity.md: {plugin} row must have seven fields")
            continue
        if columns[2] not in ALLOWED_PARITY_STATES:
            fail(f"docs/parity.md: invalid Codex status for {plugin}")
        if columns[3] not in ALLOWED_PARITY_STATES:
            fail(f"docs/parity.md: invalid Grok status for {plugin}")
        if not columns[6].strip():
            fail(f"docs/parity.md: evidence is required for {plugin}")
    if not upstream_state:
        return
    upstream = upstream_state.get("upstream", {})
    commit = upstream.get("last_reviewed_commit")
    date = upstream.get("last_reviewed_date")
    if isinstance(commit, str):
        for relative, text in (("docs/parity.md", parity), ("README.md", readme)):
            if commit not in text:
                fail(f"{relative}: missing reviewed upstream commit {commit}")
    if isinstance(date, str):
        for relative, text in (("docs/parity.md", parity), ("README.md", readme)):
            if date not in text:
                fail(f"{relative}: missing reviewed upstream date {date}")
    plugin_state = upstream_state.get("plugins", {})
    for plugin in PLUGINS:
        state = plugin_state.get(plugin, {}) if isinstance(plugin_state, dict) else {}
        version = state.get("source_version") if isinstance(state, dict) else None
        if version is not None:
            row = rows.get(plugin, [])
            if not row or version not in row[1]:
                fail(f"docs/parity.md: {plugin} source version must match upstream state")
            if version not in readme:
                fail(f"README.md: missing tracked source version {plugin} {version}")

    license_path = ROOT / "LICENSE"
    license_text = (
        license_path.read_text(encoding="utf-8") if license_path.is_file() else ""
    )
    if "MIT License" not in license_text:
        fail("LICENSE: MIT manifests require the MIT license text")


def main() -> int:
    upstream_state = validate_upstream()
    validate_docs(upstream_state)
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
