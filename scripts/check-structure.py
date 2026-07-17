#!/usr/bin/env python3
"""Validate plugin structure, runtime boundaries, parity, and provenance."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ("project-adoption", "knowledge-system", "work-system", "pr-flow")
UPSTREAM_PLUGINS = (*PLUGINS, "swarm")
AVAILABLE_CODEX_PLUGINS = {"project-adoption", "knowledge-system"}
AVAILABLE_GROK_PLUGINS = {"project-adoption", "knowledge-system"}
ALLOWED_AUTHENTICATION = {"ON_INSTALL", "ON_USE"}
ALLOWED_MANIFEST_KEYS = {
    "id",
    "name",
    "version",
    "description",
    "skills",
    "apps",
    "mcpServers",
    "interface",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
}
ALLOWED_GROK_MANIFEST_KEYS = {
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "logo",
    "skills",
}
ALLOWED_INTERFACE_KEYS = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "websiteURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
    "brandColor",
    "composerIcon",
    "logo",
    "logoDark",
    "screenshots",
    "defaultPrompt",
    "default_prompt",
}
ALLOWED_PARITY_STATES = {
    "missing",
    "planned",
    "partial",
    "parity",
    "intentional-divergence",
}
SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
FORBIDDEN_REFERENCE_PATTERNS = (
    (
        "Claude plugin root",
        re.compile(r"\$(?:\{CLAUDE_PLUGIN_ROOT\}|CLAUDE_PLUGIN_ROOT\b)"),
    ),
    ("Claude manifest path", re.compile(r"\.claude-plugin")),
    (
        "Claude executable",
        re.compile(
            r"(?<![A-Za-z0-9_.-])(?:[^\s\"'`|;&()]*/)?"
            r"claude(?:\.(?:exe|cmd|bat))?(?![A-Za-z0-9_.-])",
            re.IGNORECASE,
        ),
    ),
    ("Claude Workflow tool", re.compile(r"\bWorkflow\s*\(\s*\{")),
    (
        "Claude slash-command tool",
        re.compile(r"\bSlashCommand\s*\(\s*[\"']"),
    ),
)
CLAUDE_DOC_COMMAND = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[^\s\"'`|;&()]*/)?"
    r"claude(?:\.(?:exe|cmd|bat))?"
    r"(?:\s+(?:--?[A-Za-z0-9]|resume\b|continue\b)|(?=`))",
    re.IGNORECASE,
)
BINARY_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".webp",
    ".zip",
}
PROSE_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
ADOPTION_SIGNATURES = "plugins/project-adoption/shared/signatures.json"
ADOPTION_PATH_KEYS = {
    "agent_guidance",
    "reference_guidance",
    "runtime_root",
    "settings",
    "settings_local",
    "knowledge",
    "rules",
    "legacy_worktrees",
    "neutral_worktrees",
    "task_handoff",
    "tasks",
}
ADOPTION_PATTERN_IDS = {
    "claude-plugin-root",
    "claude-cli",
    "claude-workflow-tool",
    "claude-slash-command-tool",
}
EXPECTED_LICENSE_SHA256 = "c920e7838ac1a06728211ce607e0c73f19bb566823eb888b6a6647c80300aaf1"

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def load_json(relative: str) -> dict[str, Any] | None:
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing required file: {relative}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid JSON in {relative}: {exc}")
        return None
    if not isinstance(data, dict):
        fail(f"invalid JSON in {relative}: root must be an object")
        return None
    return data


def load_text(relative: str) -> str | None:
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing required file: {relative}")
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        fail(f"invalid text in {relative}: {exc}")
        return None


def require_non_empty_string(
    payload: dict[str, Any], key: str, relative: str, *, prefix: str = ""
) -> None:
    value = payload.get(key)
    field = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, str) or not value.strip():
        fail(f"{relative}: {field} must be a non-empty string")


def validate_manifest(plugin: str, runtime: str) -> dict[str, Any] | None:
    relative = f"plugins/{plugin}/.{runtime}-plugin/plugin.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return None
    plugin_root = ROOT / "plugins" / plugin
    if runtime == "codex":
        for key in sorted(set(data) - ALLOWED_MANIFEST_KEYS):
            fail(f"{relative}: unsupported Codex manifest field {key!r}")
    else:
        for key in sorted(set(data) - ALLOWED_GROK_MANIFEST_KEYS):
            fail(f"{relative}: unsupported Grok manifest field {key!r}")
    if data.get("name") != plugin:
        fail(f"{relative}: name must equal plugin directory {plugin!r}")
    version = data.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        fail(f"{relative}: version must be strict semver")
    require_non_empty_string(data, "description", relative)
    author = data.get("author")
    if not isinstance(author, dict):
        fail(f"{relative}: author must be an object")
    else:
        for key in sorted(set(author) - {"name", "email", "url"}):
            fail(f"{relative}: unsupported author field {key!r}")
        require_non_empty_string(author, "name", relative, prefix="author")
    if data.get("license") != "MIT":
        fail(f"{relative}: license must be MIT")
    keywords = data.get("keywords")
    if not isinstance(keywords, list) or any(
        not isinstance(item, str) or not item.strip() for item in keywords
    ):
        fail(f"{relative}: keywords must be strings")
    for field in ("homepage", "repository"):
        value = data.get(field)
        if value is not None:
            parsed = urlparse(value) if isinstance(value, str) else None
            if parsed is None or parsed.scheme != "https" or not parsed.netloc:
                fail(f"{relative}: {field} must be an absolute HTTPS URL")
    if runtime == "codex":
        interface = data.get("interface")
        if not isinstance(interface, dict):
            fail(f"{relative}: interface must be an object")
        else:
            for key in sorted(set(interface) - ALLOWED_INTERFACE_KEYS):
                fail(f"{relative}: unsupported interface field {key!r}")
            for field in (
                "displayName",
                "shortDescription",
                "longDescription",
                "developerName",
                "category",
            ):
                require_non_empty_string(interface, field, relative, prefix="interface")
            if "defaultPrompt" not in interface and "default_prompt" not in interface:
                fail(f"{relative}: interface.defaultPrompt is required")
            else:
                prompt = interface.get("defaultPrompt", interface.get("default_prompt"))
                if not (
                    isinstance(prompt, str)
                    and prompt.strip()
                    or isinstance(prompt, list)
                    and 0 < len(prompt) <= 3
                    and all(isinstance(item, str) and item.strip() for item in prompt)
                ):
                    fail(f"{relative}: interface.defaultPrompt must be non-empty")
            capabilities = interface.get("capabilities")
            if not isinstance(capabilities, list) or any(
                not isinstance(item, str) or not item.strip() for item in capabilities
            ):
                fail(f"{relative}: interface.capabilities must be strings")
            for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
                value = interface.get(field)
                if value is not None:
                    parsed = urlparse(value) if isinstance(value, str) else None
                    if parsed is None or parsed.scheme != "https" or not parsed.netloc:
                        fail(f"{relative}: interface.{field} must be HTTPS")
        for field, expected in (("skills", "./skills/"), ("apps", "./.app.json")):
            value = data.get(field)
            if value is not None and value != expected:
                fail(f"{relative}: {field} must equal {expected}")
            elif value is not None:
                target = plugin_root / value.removeprefix("./")
                if field == "skills" and not target.is_dir():
                    fail(f"{relative}: declared skills directory does not exist")
                if field == "apps" and not target.is_file():
                    fail(f"{relative}: declared app manifest does not exist")
        mcp_servers = data.get("mcpServers")
        if mcp_servers is not None and not (
            isinstance(mcp_servers, dict) or mcp_servers == "./.mcp.json"
        ):
            fail(f"{relative}: mcpServers must be an object or ./.mcp.json")
        elif isinstance(mcp_servers, str):
            target = plugin_root / mcp_servers.removeprefix("./")
            if not target.is_file():
                fail(f"{relative}: declared MCP manifest does not exist")
        elif isinstance(mcp_servers, dict):
            for value in iter_strings(mcp_servers):
                for label, pattern in FORBIDDEN_REFERENCE_PATTERNS:
                    if pattern.search(value):
                        fail(f"{relative}: inline MCP config contains forbidden {label}")
    if runtime == "grok":
        skills = data.get("skills")
        if plugin in AVAILABLE_GROK_PLUGINS:
            if skills != "./grok/skills/":
                fail(f"{relative}: skills must equal \"./grok/skills/\" for available Grok plugins")
        if skills is not None:
            if skills != "./grok/skills/":
                fail(f"{relative}: skills must equal \"./grok/skills/\" if declared")
            target = plugin_root / "grok/skills"
            if not target.is_dir():
                fail(f"{relative}: declared skills directory does not exist")
    return data


def validate_codex_marketplace() -> None:
    relative = ".agents/plugins/marketplace.json"
    data = load_json(relative)
    if not isinstance(data, dict):
        return
    if set(data) - {"name", "interface", "plugins"}:
        fail(f"{relative}: unsupported top-level marketplace field")
    if data.get("name") != "gering-agent-plugins":
        fail(f"{relative}: unexpected marketplace name")
    interface = data.get("interface")
    if not isinstance(interface, dict):
        fail(f"{relative}: interface must be an object")
    else:
        require_non_empty_string(interface, "displayName", relative, prefix="interface")
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
        elif not (ROOT / "plugins" / plugin / ".codex-plugin/plugin.json").is_file():
            fail(f"{relative}: {plugin} source does not contain a Codex manifest")
        policy = entry.get("policy")
        if not isinstance(policy, dict):
            fail(f"{relative}: {plugin} is missing policy")
            continue
        expected_installation = (
            "AVAILABLE" if plugin in AVAILABLE_CODEX_PLUGINS else "NOT_AVAILABLE"
        )
        if policy.get("installation") != expected_installation:
            fail(
                f"{relative}: {plugin} must use installation policy "
                f"{expected_installation}"
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
    if set(data) - {"name", "description", "owner", "plugins"}:
        fail(f"{relative}: unsupported top-level marketplace field")
    if data.get("name") != "gering-agent-plugins":
        fail(f"{relative}: unexpected marketplace name")
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        fail(f"{relative}: description is required")
    owner = data.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner.get("name", "").strip():
        fail(f"{relative}: owner.name is required and must be non-empty")
    entries = data.get("plugins")
    if not isinstance(entries, list):
        fail(f"{relative}: plugins must be an array")
        return
    if any(not isinstance(e, dict) for e in entries):
        fail(f"{relative}: every plugin entry must be an object")
        return
    names = [e.get("name") for e in entries if isinstance(e, dict)]
    if any(not isinstance(n, str) or not n.strip() for n in names):
        fail(f"{relative}: every plugin name must be a non-empty string")
        return
    if len(names) != len(set(names)):
        fail(f"{relative}: duplicate plugin names are not allowed")
    expected = set(AVAILABLE_GROK_PLUGINS)
    if set(names) != expected:
        fail(f"{relative}: Grok plugins must match {sorted(expected)} when advertised (only after full validation)")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name not in AVAILABLE_GROK_PLUGINS:
            continue
        source = entry.get("source")
        # Grok supports flat path string or nested object for local sources
        expected_flat = f"./plugins/{name}"
        expected_nested = {"source": "local", "path": expected_flat}
        if source not in (expected_flat, expected_nested):
            fail(f"{relative}: {name} must use local source {expected_flat} or {expected_nested}")
        if not (ROOT / f"plugins/{name}" / ".grok-plugin/plugin.json").is_file():
            fail(f"{relative}: {name} source does not contain a Grok manifest")
        # description optional but recommended
        if "description" in entry and not isinstance(entry.get("description"), str):
            fail(f"{relative}: {name} description must be string if present")


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
        return None
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
    observed = upstream.get("latest_observed_commit")
    if not isinstance(observed, str) or not re.fullmatch(r"[0-9a-f]{40}", observed):
        fail(f"{relative}: latest_observed_commit must be a full Git SHA")
    observed_date = upstream.get("latest_observed_date")
    if not isinstance(observed_date, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", observed_date
    ):
        fail(f"{relative}: latest_observed_date must use YYYY-MM-DD")
    plugins = data.get("plugins")
    if not isinstance(plugins, dict) or set(plugins) != set(UPSTREAM_PLUGINS):
        fail(f"{relative}: plugin state must match the tracked upstream plugin set")
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


def validate_adoption_signatures() -> None:
    data = load_json(ADOPTION_SIGNATURES)
    if not isinstance(data, dict):
        return
    if set(data) != {"paths", "content_patterns", "agent_specific_patterns"}:
        fail(f"{ADOPTION_SIGNATURES}: unsupported top-level fields")
    paths = data.get("paths")
    if not isinstance(paths, dict) or set(paths) != ADOPTION_PATH_KEYS:
        fail(f"{ADOPTION_SIGNATURES}: paths must match the adoption inventory schema")
    else:
        for name, value in paths.items():
            candidate = Path(value) if isinstance(value, str) else None
            if (
                candidate is None
                or candidate.is_absolute()
                or ".." in candidate.parts
                or not candidate.parts
            ):
                fail(f"{ADOPTION_SIGNATURES}: invalid relative path for {name}")
    patterns = data.get("content_patterns")
    seen_ids: set[str] = set()
    if not isinstance(patterns, list):
        fail(f"{ADOPTION_SIGNATURES}: content_patterns must be an array")
    else:
        for index, item in enumerate(patterns):
            if not isinstance(item, dict) or set(item) != {"id", "label", "pattern"}:
                fail(f"{ADOPTION_SIGNATURES}: invalid content pattern at index {index}")
                continue
            pattern_id = item.get("id")
            label = item.get("label")
            expression = item.get("pattern")
            if not isinstance(pattern_id, str) or pattern_id in seen_ids:
                fail(f"{ADOPTION_SIGNATURES}: duplicate or invalid pattern id")
            else:
                seen_ids.add(pattern_id)
            if not isinstance(label, str) or not label.strip():
                fail(f"{ADOPTION_SIGNATURES}: pattern labels must be non-empty")
            if not isinstance(expression, str):
                fail(f"{ADOPTION_SIGNATURES}: invalid regex for pattern {pattern_id!r}")
            else:
                try:
                    re.compile(expression)
                except re.error:
                    fail(f"{ADOPTION_SIGNATURES}: invalid regex for pattern {pattern_id!r}")
        if seen_ids != ADOPTION_PATTERN_IDS:
            fail(f"{ADOPTION_SIGNATURES}: content pattern ids must match the approved detector set")
    agent_patterns = data.get("agent_specific_patterns")
    if not isinstance(agent_patterns, list) or not agent_patterns:
        fail(f"{ADOPTION_SIGNATURES}: agent_specific_patterns must be a non-empty array")
    else:
        for expression in agent_patterns:
            if not isinstance(expression, str):
                fail(f"{ADOPTION_SIGNATURES}: invalid agent-specific regex")
                continue
            try:
                re.compile(expression)
            except re.error:
                fail(f"{ADOPTION_SIGNATURES}: invalid agent-specific regex")


def _validate_frontmatter(text: str | None, relative: str, expected_name: str) -> None:
    if text is None:
        return
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        fail(f"{relative}: missing complete YAML frontmatter")
        return
    frontmatter, body = text[4:].split("\n---\n", 1)
    metadata: dict[str, str] = {}
    for line in frontmatter.splitlines():
        key, separator, value = line.partition(":")
        key = key.strip()
        if not separator or not key or key in metadata or not value.strip():
            fail(f"{relative}: malformed frontmatter")
            continue
        metadata[key] = value.strip()
    if set(metadata) != {"name", "description"}:
        fail(f"{relative}: frontmatter must contain only name and description")
    if metadata.get("name") != expected_name:
        fail(f"{relative}: skill name must be {expected_name}")
    if not body.strip():
        fail(f"{relative}: skill instructions must not be empty")
    if "TODO" in text:
        fail(f"{relative}: unresolved TODO marker")


def _validate_openai_metadata(relative: str, expected_skill: str) -> None:
    agent = load_text(relative)
    if agent is None:
        return
    lines = agent.splitlines()
    values: dict[str, str] = {}
    if not lines or lines[0] != "interface:":
        fail(f"{relative}: root must be interface")
    for line in lines[1:]:
        match = re.fullmatch(r"  ([a-z_]+):\s*(.+)", line)
        if not match or match.group(1) in values:
            fail(f"{relative}: malformed interface metadata")
            continue
        try:
            value = json.loads(match.group(2))
        except json.JSONDecodeError:
            fail(f"{relative}: interface values must be quoted strings")
            continue
        if not isinstance(value, str) or not value.strip():
            fail(f"{relative}: interface values must be non-empty strings")
            continue
        values[match.group(1)] = value
    if set(values) != {"display_name", "short_description", "default_prompt"}:
        fail(f"{relative}: interface fields do not match the required schema")
    short_description = values.get("short_description", "")
    if short_description and not 25 <= len(short_description) <= 64:
        fail(f"{relative}: short_description must be 25-64 characters")
    if f"${expected_skill}" not in values.get("default_prompt", ""):
        fail(f"{relative}: default_prompt must mention ${expected_skill}")
    if "TODO" in agent:
        fail(f"{relative}: unresolved TODO marker")


def validate_project_adoption_slice() -> None:
    required = (
        "plugins/project-adoption/shared/audit_project.py",
        "plugins/project-adoption/shared/ADOPTION_AUDIT.md",
        ADOPTION_SIGNATURES,
        "plugins/project-adoption/skills/adopt-claude-project/SKILL.md",
        "plugins/project-adoption/skills/adopt-claude-project/agents/openai.yaml",
        "plugins/project-adoption/grok/skills/adopt-claude-project/SKILL.md",
        "tests/test_project_adoption.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"project-adoption available slice is missing required file: {relative}")

    skill_relative = "plugins/project-adoption/skills/adopt-claude-project/SKILL.md"
    skill = load_text(skill_relative)
    # frontmatter validated via shared helper below

    agent_relative = (
        "plugins/project-adoption/skills/adopt-claude-project/agents/openai.yaml"
    )
    agent = load_text(agent_relative)
    if agent is not None:
        lines = agent.splitlines()
        values: dict[str, str] = {}
        if not lines or lines[0] != "interface:":
            fail(f"{agent_relative}: root must be interface")
        for line in lines[1:]:
            match = re.fullmatch(r"  ([a-z_]+):\s*(.+)", line)
            if not match or match.group(1) in values:
                fail(f"{agent_relative}: malformed interface metadata")
                continue
            try:
                value = json.loads(match.group(2))
            except json.JSONDecodeError:
                fail(f"{agent_relative}: interface values must be quoted strings")
                continue
            if not isinstance(value, str) or not value.strip():
                fail(f"{agent_relative}: interface values must be non-empty strings")
                continue
            values[match.group(1)] = value
        if set(values) != {"display_name", "short_description", "default_prompt"}:
            fail(f"{agent_relative}: interface fields do not match the required schema")
        short_description = values.get("short_description", "")
        if short_description and not 25 <= len(short_description) <= 64:
            fail(f"{agent_relative}: short_description must be 25-64 characters")
        if "$adopt-claude-project" not in values.get("default_prompt", ""):
            fail(f"{agent_relative}: default_prompt must mention $adopt-claude-project")
        if "TODO" in agent:
            fail(f"{agent_relative}: unresolved TODO marker")

    _validate_frontmatter(skill, skill_relative, "adopt-claude-project")

    # Grok native adapter skill (thin prompt + invocation)
    grok_skill_relative = (
        "plugins/project-adoption/grok/skills/adopt-claude-project/SKILL.md"
    )
    grok_skill = load_text(grok_skill_relative)
    _validate_frontmatter(grok_skill, grok_skill_relative, "adopt-claude-project")
    workflow_relative = "plugins/project-adoption/shared/ADOPTION_AUDIT.md"
    workflow = load_text(workflow_relative)
    workflow_reference = "shared/ADOPTION_AUDIT.md"
    if skill is not None and workflow_reference not in skill:
        fail(f"{skill_relative}: Codex adapter must reference {workflow_reference}")
    if grok_skill is not None and workflow_reference not in grok_skill:
        fail(f"{grok_skill_relative}: Grok adapter must reference {workflow_reference}")
    if workflow is not None and "shared/audit_project.py" not in workflow:
        fail(f"{workflow_relative}: shared workflow must reference shared/audit_project.py")


def validate_knowledge_system_slice() -> None:
    required = (
        "plugins/knowledge-system/shared/knowledge_tool.py",
        "plugins/knowledge-system/shared/KNOWLEDGE_WORKFLOWS.md",
        "plugins/knowledge-system/skills/query/SKILL.md",
        "plugins/knowledge-system/skills/query/agents/openai.yaml",
        "plugins/knowledge-system/skills/reindex/SKILL.md",
        "plugins/knowledge-system/skills/reindex/agents/openai.yaml",
        "plugins/knowledge-system/grok/skills/query/SKILL.md",
        "plugins/knowledge-system/grok/skills/reindex/SKILL.md",
        "tests/test_knowledge_system.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"knowledge-system native slice is missing required file: {relative}")

    workflow_reference = "shared/KNOWLEDGE_WORKFLOWS.md"
    for runtime_root in ("skills", "grok/skills"):
        for skill_name in ("query", "reindex"):
            relative = f"plugins/knowledge-system/{runtime_root}/{skill_name}/SKILL.md"
            skill = load_text(relative)
            _validate_frontmatter(skill, relative, skill_name)
            if skill is not None and workflow_reference not in skill:
                fail(f"{relative}: native adapter must reference {workflow_reference}")

    for skill_name in ("query", "reindex"):
        _validate_openai_metadata(
            f"plugins/knowledge-system/skills/{skill_name}/agents/openai.yaml",
            skill_name,
        )

    workflow = load_text("plugins/knowledge-system/shared/KNOWLEDGE_WORKFLOWS.md")
    if workflow is not None:
        for required_text in ("knowledge_tool.py query", "reindex --check", "read-only"):
            if required_text not in workflow:
                fail(
                    "plugins/knowledge-system/shared/KNOWLEDGE_WORKFLOWS.md: "
                    f"missing required native workflow marker {required_text!r}"
                )

    helper = load_text("plugins/knowledge-system/shared/knowledge_tool.py")
    if helper is not None:
        if "reindex currently requires --check" not in helper:
            fail("knowledge-system shared helper must fail closed without --check")
        if (
            "class StoreAnchor" not in helper
            or "dir_fd=" not in helper
            or "O_NOFOLLOW" not in helper
            or "O_NONBLOCK" not in helper
            or "file_signature" not in helper
        ):
            fail("knowledge-system shared helper must reject raced path traversal")


def validate_adapter_boundaries() -> None:
    for reviewer_root in ROOT.glob("plugins/*/reviewers"):
        if reviewer_root.exists():
            fail(
                f"{reviewer_root.relative_to(ROOT)}: external reviewer code is "
                "fail-closed until its read-only prepared-scope validator is implemented"
            )
    plugins_root = ROOT / "plugins"
    if not plugins_root.is_dir():
        return
    for path in plugins_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative == ADOPTION_SIGNATURES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            fail(f"{path.relative_to(ROOT)}: unreadable runtime file: {exc}")
            continue
        is_manifest = path.name == "plugin.json" and path.parent.name in {
            ".codex-plugin",
            ".grok-plugin",
        }
        is_ui_metadata = path.name == "openai.yaml" and path.parent.name == "agents"
        patterns = (
            FORBIDDEN_REFERENCE_PATTERNS[:2]
            if is_manifest or is_ui_metadata
            else FORBIDDEN_REFERENCE_PATTERNS
        )
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in patterns:
                active_pattern = pattern
                if label == "Claude executable" and path.suffix.lower() in PROSE_SUFFIXES:
                    active_pattern = CLAUDE_DOC_COMMAND
                if active_pattern.search(line):
                    fail(
                        f"{path.relative_to(ROOT)}:{line_number}: native runtime "
                        f"file contains forbidden {label}"
                    )


def validate_docs(upstream_state: dict[str, Any] | None) -> None:
    required = (
        ".gitignore",
        "AGENTS.md",
        "README.md",
        "docs/architecture.md",
        "docs/parity.md",
        "docs/migration-from-claude.md",
        "docs/claude-compatibility-backlog.md",
        "docs/grok-installation.md",
        "scripts/check-upstream.py",
        "LICENSE",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")
    parity_path = ROOT / "docs/parity.md"
    readme_path = ROOT / "README.md"
    if not parity_path.is_file() or not readme_path.is_file():
        return
    parity = load_text("docs/parity.md")
    readme = load_text("README.md")
    if parity is None or readme is None:
        return
    license_text = load_text("LICENSE")
    normalized_license = (license_text or "").replace("\r\n", "\n")
    if hashlib.sha256(normalized_license.encode("utf-8")).hexdigest() != EXPECTED_LICENSE_SHA256:
        fail("LICENSE: content must match the repository MIT license template")
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
        if plugin in AVAILABLE_CODEX_PLUGINS and columns[2] not in {
            "partial",
            "parity",
            "intentional-divergence",
        }:
            fail(f"docs/parity.md: available Codex plugin {plugin} needs runtime evidence")
        if plugin in AVAILABLE_GROK_PLUGINS and columns[3] not in {
            "partial",
            "parity",
            "intentional-divergence",
        }:
            fail(f"docs/parity.md: available Grok plugin {plugin} needs runtime evidence")
    if not upstream_state:
        return
    upstream = upstream_state.get("upstream")
    if not isinstance(upstream, dict):
        return
    commit = upstream.get("last_reviewed_commit")
    date = upstream.get("last_reviewed_date")
    observed = upstream.get("latest_observed_commit")
    if isinstance(commit, str):
        if f"- Last reviewed commit: `{commit}`" not in parity:
            fail(f"docs/parity.md: baseline commit must equal upstream state {commit}")
        if f"- Reviewed commit: `{commit}`" not in readme:
            fail(f"README.md: reviewed commit must equal upstream state {commit}")
    if isinstance(date, str):
        if f"- Last sync review: {date}" not in parity:
            fail(f"docs/parity.md: baseline date must equal upstream state {date}")
        if f"- Review date: {date}" not in readme:
            fail(f"README.md: review date must equal upstream state {date}")
    if isinstance(observed, str) and observed not in parity:
        fail(f"docs/parity.md: missing latest observed upstream commit {observed}")
    tracked_versions_match = re.search(
        r"^- Upstream versions:(.*(?:\n  .*)*)$", readme, re.MULTILINE
    )
    tracked_versions = tracked_versions_match.group(1) if tracked_versions_match else ""
    plugin_state = upstream_state.get("plugins", {})
    for plugin in UPSTREAM_PLUGINS:
        state = plugin_state.get(plugin, {}) if isinstance(plugin_state, dict) else {}
        version = state.get("source_version") if isinstance(state, dict) else None
        row = rows.get(plugin, [])
        if row and isinstance(commit, str) and isinstance(date, str):
            expected_sync = f"{date} / `{commit}`"
            if row[4] != expected_sync:
                fail(f"docs/parity.md: {plugin} Last sync must be {expected_sync}")
        if version is not None and isinstance(commit, str):
            expected_source = f"{version} at `{commit}`"
            if not row or row[1] != expected_source:
                fail(f"docs/parity.md: {plugin} source version must match upstream state")
            version_pattern = re.compile(
                rf"\b{re.escape(plugin)}\s+{re.escape(version)}(?![0-9A-Za-z.+-])"
            )
            if version_pattern.search(tracked_versions) is None:
                fail(f"README.md: missing tracked source version {plugin} {version}")

    readme_rows: dict[str, list[str]] = {}
    for line in readme.splitlines():
        columns = [column.strip() for column in line.split("|")[1:-1]]
        if columns and columns[0] in PLUGINS:
            if columns[0] in readme_rows:
                fail(f"README.md: duplicate plugin status row for {columns[0]}")
            readme_rows[columns[0]] = columns
    for plugin in PLUGINS:
        parity_row = rows.get(plugin, [])
        readme_row = readme_rows.get(plugin, [])
        if len(readme_row) != 3:
            fail(f"README.md: missing three-field plugin status row for {plugin}")
        elif parity_row and readme_row[1:3] != parity_row[2:4]:
            fail(f"README.md: {plugin} statuses must match docs/parity.md")


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
    validate_adoption_signatures()
    validate_project_adoption_slice()
    validate_knowledge_system_slice()
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
