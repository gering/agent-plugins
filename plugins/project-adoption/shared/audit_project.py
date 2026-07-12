#!/usr/bin/env python3
"""Produce a deterministic, read-only agent-adoption audit."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SIGNATURES_PATH = Path(__file__).with_name("signatures.json")
MAX_FILE_SIZE = 256 * 1024
MAX_EVIDENCE_PER_PATTERN = 20
SKIPPED_PARTS = {
    ".git",
    ".worktrees",
    "build",
    "dist",
    "node_modules",
    "secrets",
    "vendor",
    "worktrees",
}
SKIPPED_NAMES = {
    ".env",
    ".env.local",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
SKIPPED_SUFFIXES = {
    ".avif",
    ".env",
    ".key",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".lock",
    ".pdf",
    ".pem",
    ".p12",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
WORKFLOW_PLUGIN_NAMES = ("knowledge-system", "pr-flow", "work-system")


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    for key in list(environment):
        if key == "GIT_CONFIG_COUNT" or key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            environment.pop(key)
    return subprocess.run(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "submodule.recurse=false",
            "-C",
            str(root),
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def load_signatures() -> dict[str, Any]:
    data = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("signature data must be an object")
    return data


def tracked_files(root: Path, is_git: bool) -> list[Path]:
    if is_git:
        result = run_git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if result.returncode == 0:
            return [root / item for item in result.stdout.split("\0") if item]
    candidates: list[Path] = []
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [name for name in names if name not in SKIPPED_PARTS]
        base = Path(directory)
        candidates.extend(base / name for name in files)
        candidates.extend(base / name for name in names if (base / name).is_symlink())
    return candidates


def scannable(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in SKIPPED_PARTS for part in relative.parts):
        return False
    if path.name in SKIPPED_NAMES or path.name.startswith(".env."):
        return False
    if path.suffix.lower() in SKIPPED_SUFFIXES:
        return False
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE_SIZE
    except OSError:
        return False


def add_finding(
    findings: list[dict[str, Any]],
    finding_id: str,
    severity: str,
    category: str,
    message: str,
    recommendation: str,
    evidence: list[str] | None = None,
    change_class: str = "preserve",
) -> None:
    findings.append(
        {
            "id": finding_id,
            "severity": severity,
            "category": category,
            "message": message,
            "evidence": evidence or [],
            "recommendation": recommendation,
            "changeClass": change_class,
        }
    )


def first_symlink(root: Path, path: Path) -> Path | None:
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return current
    return None


def safe_explicit_file(
    root: Path,
    path: Path,
    findings: list[dict[str, Any]],
    finding_id: str,
    label: str,
) -> bool:
    symlink = first_symlink(root, path)
    if symlink is not None:
        add_finding(
            findings,
            finding_id,
            "warning",
            "scope",
            f"{label} is a symbolic link and was not followed.",
            "Inspect the link target explicitly before including it in an adoption audit.",
            [symlink.relative_to(root).as_posix()],
            "approval-required",
        )
        return False
    return path.is_file()


def audit(root: Path, signatures: dict[str, Any]) -> dict[str, Any]:
    paths = signatures["paths"]
    is_git = run_git(root, "rev-parse", "--is-inside-work-tree").returncode == 0
    dirty_count = 0
    worktree_count = 0
    if is_git:
        dirty = run_git(root, "status", "--porcelain")
        dirty_count = len([line for line in dirty.stdout.splitlines() if line])
        worktrees = run_git(root, "worktree", "list", "--porcelain")
        worktree_count = sum(1 for line in worktrees.stdout.splitlines() if line.startswith("worktree "))

    findings: list[dict[str, Any]] = []
    inventory: dict[str, Any] = {
        "gitRepository": is_git,
        "dirtyPathCount": dirty_count,
        "worktreeCount": worktree_count,
        "enabledPlugins": [],
    }

    agent_path = root / paths["agent_guidance"]
    reference_path = root / paths["reference_guidance"]
    agent_present = agent_path.exists() or agent_path.is_symlink()
    agent_safe = safe_explicit_file(
        root, agent_path, findings, "agents-guidance-symlink", "Shared agent guidance"
    )
    if not agent_present:
        add_finding(
            findings,
            "agents-guidance-missing",
            "warning",
            "guidance",
            "Shared agent guidance is missing.",
            "Draft an agent-neutral AGENTS.md and show it before writing.",
            change_class="safe-scaffolding",
        )
    elif agent_safe:
        inventory["agentGuidance"] = True
        try:
            agent_text = agent_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            add_finding(
                findings,
                "agents-guidance-unreadable",
                "warning",
                "guidance",
                "Shared agent guidance is not readable as UTF-8.",
                "Review the file encoding before adoption.",
                [paths["agent_guidance"]],
                "approval-required",
            )
        else:
            matches = [
                pattern
                for pattern in signatures["agent_specific_patterns"]
                if re.search(pattern, agent_text)
            ]
            if matches:
                add_finding(
                    findings,
                    "agents-guidance-runtime-specific",
                    "warning",
                    "guidance",
                    "AGENTS.md contains runtime-specific orchestration that may misdirect another agent.",
                    "Separate durable shared rules from runtime-specific launch and session instructions.",
                    [paths["agent_guidance"]],
                    "approval-required",
                )

    if safe_explicit_file(
        root,
        reference_path,
        findings,
        "reference-guidance-symlink",
        "Reference-runtime guidance",
    ):
        inventory["referenceGuidance"] = True
        imports: list[str] = []
        try:
            for number, line in enumerate(reference_path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("@"):
                    imports.append(f"{paths['reference_guidance']}:{number}")
        except (OSError, UnicodeDecodeError):
            imports = []
        add_finding(
            findings,
            "reference-guidance-present",
            "info",
            "guidance",
            "Reference-runtime guidance is present.",
            "Preserve it; map durable shared rules into AGENTS.md without deleting the source.",
            [paths["reference_guidance"], *imports[:10]],
        )

    for key, finding_id, message in (
        ("knowledge", "versioned-knowledge-present", "Versioned project knowledge is present."),
        ("rules", "runtime-rules-present", "Runtime-specific rule files are present."),
        ("legacy_worktrees", "legacy-worktrees-present", "Legacy worktree storage is present."),
        ("neutral_worktrees", "neutral-worktrees-present", "Agent-neutral worktree storage is present."),
        ("task_handoff", "task-handoff-present", "A task handoff file is present."),
        ("tasks", "task-backlog-present", "A task backlog is present."),
    ):
        candidate = root / paths[key]
        symlink = first_symlink(root, candidate)
        if symlink is not None and symlink == candidate:
            inventory[key] = True
            add_finding(
                findings,
                f"{finding_id}-symlink",
                "info",
                "project-state",
                f"{message} The path is a symbolic link and was not followed.",
                "Preserve the link and inspect its target explicitly before migration.",
                [paths[key]],
            )
        elif symlink is not None:
            continue
        elif candidate.exists():
            inventory[key] = True
            add_finding(
                findings,
                finding_id,
                "info",
                "project-state",
                message,
                "Preserve this location during initial adoption.",
                [paths[key]],
            )

    settings_path = root / paths["settings"]
    if safe_explicit_file(
        root,
        settings_path,
        findings,
        "runtime-settings-symlink",
        "Runtime settings",
    ):
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            enabled = settings.get("enabledPlugins", {}) if isinstance(settings, dict) else {}
            if isinstance(enabled, dict):
                inventory["enabledPlugins"] = sorted(
                    key for key, value in enabled.items() if value is not False
                )
            elif isinstance(enabled, list):
                inventory["enabledPlugins"] = sorted(
                    value for value in enabled if isinstance(value, str)
                )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            add_finding(
                findings,
                "runtime-settings-unreadable",
                "warning",
                "plugins",
                "Runtime settings could not be parsed safely.",
                "Review settings manually; do not rewrite them automatically.",
                [paths["settings"]],
                "approval-required",
            )
        if inventory["enabledPlugins"]:
            add_finding(
                findings,
                "runtime-plugins-enabled",
                "info",
                "plugins",
                "Reference-runtime plugins are enabled.",
                "Map their capabilities before changing installation state.",
                [paths["settings"]],
            )

    candidates = tracked_files(root, is_git)
    memory_integrations: list[str] = []
    for path in candidates:
        relative = path.relative_to(root)
        if any(part in SKIPPED_PARTS for part in relative.parts):
            continue
        has_memory_name = any("memory" in part.lower() for part in relative.parts)
        is_link_helper = "memory" in path.name.lower() and "link" in path.name.lower()
        if is_link_helper or (path.is_symlink() and has_memory_name):
            memory_integrations.append(relative.as_posix())
    memory_integrations = sorted(set(memory_integrations))[:20]
    inventory["memoryIntegrationPaths"] = memory_integrations
    if memory_integrations:
        add_finding(
            findings,
            "memory-integration-present",
            "info",
            "project-state",
            "Project-local memory integration helpers or links are present.",
            "Preserve them and verify their targets before changing knowledge or memory layout.",
            memory_integrations,
        )

    compiled = [
        (item["id"], item["label"], re.compile(item["pattern"]))
        for item in signatures["content_patterns"]
    ]
    pattern_evidence: dict[str, list[str]] = {item[0]: [] for item in compiled}
    pattern_labels = {item[0]: item[1] for item in compiled}
    plugin_evidence: dict[str, list[str]] = {name: [] for name in WORKFLOW_PLUGIN_NAMES}
    for plugin_name, evidence in plugin_evidence.items():
        if any(
            selector == plugin_name or selector.startswith(f"{plugin_name}@")
            for selector in inventory["enabledPlugins"]
        ):
            evidence.append(paths["settings"])
    for path in candidates:
        if not scannable(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(text.splitlines(), 1):
            for pattern_id, _, pattern in compiled:
                evidence = pattern_evidence[pattern_id]
                if len(evidence) < MAX_EVIDENCE_PER_PATTERN and pattern.search(line):
                    evidence.append(f"{relative}:{line_number}")
            for plugin_name, evidence in plugin_evidence.items():
                if (
                    len(evidence) < MAX_EVIDENCE_PER_PATTERN
                    and re.search(rf"(?<![A-Za-z0-9_-]){re.escape(plugin_name)}(?![A-Za-z0-9_-])", line)
                ):
                    evidence.append(f"{relative}:{line_number}")

    for pattern_id, evidence in pattern_evidence.items():
        if evidence:
            add_finding(
                findings,
                f"hardcoded-{pattern_id}",
                "warning",
                "runtime-boundary",
                f"Tracked files contain {pattern_labels[pattern_id]} references.",
                "Map each reference to a native adapter or document it as reference-only.",
                evidence,
                "approval-required",
            )

    referenced_plugins = {
        name: evidence for name, evidence in plugin_evidence.items() if evidence
    }
    inventory["referencedWorkflowPlugins"] = sorted(referenced_plugins)
    if referenced_plugins:
        add_finding(
            findings,
            "workflow-plugin-references",
            "info",
            "plugins",
            "Tracked files reference workflow plugins that need capability mapping.",
            "Map each referenced workflow to native Codex and Grok behavior before migration.",
            [
                f"{name}:{location}"
                for name, locations in referenced_plugins.items()
                for location in locations
            ][:20],
        )

    if dirty_count:
        add_finding(
            findings,
            "dirty-working-tree",
            "warning",
            "provenance",
            "The target working tree has local changes.",
            "Keep the audit read-only and do not use dirty files as import provenance.",
            change_class="preserve",
        )

    counts = Counter(item["severity"] for item in findings)
    return {
        "schemaVersion": 1,
        "root": str(root),
        "readOnly": True,
        "inventory": inventory,
        "summary": {
            "info": counts["info"],
            "warning": counts["warning"],
            "total": len(findings),
        },
        "findings": findings,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "Project adoption audit (read-only)",
        f"Root: {report['root']}",
        f"Findings: {report['summary']['warning']} warning(s), {report['summary']['info']} info",
        "",
    ]
    for finding in report["findings"]:
        lines.append(f"[{finding['severity'].upper()}] {finding['id']}: {finding['message']}")
        for evidence in finding["evidence"]:
            lines.append(f"  - {evidence}")
        lines.append(f"  Recommendation: {finding['recommendation']}")
    lines.append("")
    lines.append("No files were changed.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    root = args.target.expanduser().resolve()
    if not root.is_dir():
        print(f"AUDIT_ERROR target is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        report = audit(root, load_signatures())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"AUDIT_ERROR {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
