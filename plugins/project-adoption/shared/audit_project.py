#!/usr/bin/env python3
"""Produce a deterministic, read-only agent-adoption audit."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


SIGNATURES_PATH = Path(__file__).with_name("signatures.json")
MAX_FILE_SIZE = 256 * 1024
MAX_EVIDENCE_PER_PATTERN = 20
MAX_ENABLED_PLUGINS = 100
MAX_PLUGIN_ID_LENGTH = 256
GIT_TIMEOUT_SECONDS = 10
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


class AuditError(RuntimeError):
    """The audit could not complete safely and must fail closed."""


def _git_directories(root: Path) -> tuple[Path, Path] | None:
    dot_git = root / ".git"
    if dot_git.is_symlink():
        raise AuditError(".git is a symbolic link; refusing to load repository metadata")
    if dot_git.is_dir():
        worktree_git_dir = dot_git
    elif dot_git.is_file():
        try:
            marker = dot_git.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise AuditError(f"cannot read .git indirection: {exc}") from exc
        if not marker.startswith("gitdir: "):
            raise AuditError("invalid .git indirection")
        worktree_git_dir = Path(marker[8:])
        if not worktree_git_dir.is_absolute():
            worktree_git_dir = dot_git.parent / worktree_git_dir
        worktree_git_dir = worktree_git_dir.resolve()
        if not worktree_git_dir.is_dir():
            raise AuditError(".git indirection does not name a directory")
    elif dot_git.exists():
        raise AuditError("unsupported .git metadata type")
    else:
        return None

    common_git_dir = worktree_git_dir
    commondir = worktree_git_dir / "commondir"
    if commondir.is_file():
        try:
            common_git_dir = Path(commondir.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError) as exc:
            raise AuditError(f"cannot read Git commondir: {exc}") from exc
        if not common_git_dir.is_absolute():
            common_git_dir = worktree_git_dir / common_git_dir
        common_git_dir = common_git_dir.resolve()
    if not common_git_dir.is_dir() or not (common_git_dir / "objects").is_dir():
        raise AuditError("Git object directory is missing")
    return worktree_git_dir, common_git_dir


def _read_head(worktree_git_dir: Path, common_git_dir: Path) -> str:
    head_path = worktree_git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise AuditError(f"cannot read Git HEAD: {exc}") from exc
    if re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        return head.lower()
    if not head.startswith("ref: refs/") or ".." in Path(head[5:]).parts:
        raise AuditError("Git HEAD is malformed")
    reference = head[5:]
    for base in (worktree_git_dir, common_git_dir):
        loose = base / reference
        if loose.is_file() and not loose.is_symlink():
            try:
                value = loose.read_text(encoding="ascii").strip()
            except (OSError, UnicodeDecodeError) as exc:
                raise AuditError(f"cannot read Git HEAD reference: {exc}") from exc
            if re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
                return value.lower()
            raise AuditError("Git HEAD reference is malformed")
    packed_refs = common_git_dir / "packed-refs"
    if packed_refs.is_file() and not packed_refs.is_symlink():
        try:
            lines = packed_refs.read_text(encoding="ascii").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise AuditError(f"cannot read packed Git references: {exc}") from exc
        for line in lines:
            fields = line.split(" ", 1)
            if len(fields) == 2 and fields[1] == reference and re.fullmatch(
                r"[0-9a-fA-F]{40,64}", fields[0]
            ):
                return fields[0].lower()
    return head


class SafeGit:
    """Run read-only Git queries without loading any target-controlled config."""

    def __init__(self, root: Path):
        self.root = root
        directories = _git_directories(root)
        self.is_repository = directories is not None
        self.worktree_count = 0
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._environment: dict[str, str] | None = None
        if directories is None:
            return
        self.worktree_git_dir, self.common_git_dir = directories
        worktrees = self.common_git_dir / "worktrees"
        linked = (
            sum(1 for item in worktrees.iterdir() if item.is_dir() and not item.is_symlink())
            if worktrees.is_dir()
            else 0
        )
        self.worktree_count = linked + 1

    def __enter__(self) -> "SafeGit":
        if not self.is_repository:
            return self
        self._temporary = tempfile.TemporaryDirectory(prefix="agent-adoption-git-")
        isolated = Path(self._temporary.name)
        (isolated / "objects").mkdir()
        (isolated / "refs" / "heads").mkdir(parents=True)
        (isolated / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
        (isolated / "HEAD").write_text(
            f"{_read_head(self.worktree_git_dir, self.common_git_dir)}\n", encoding="ascii"
        )
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("GIT_"):
                environment.pop(key)
        environment.update(
            {
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_DIR": str(isolated),
                "GIT_INDEX_FILE": str(self.worktree_git_dir / "index"),
                "GIT_OBJECT_DIRECTORY": str(self.common_git_dir / "objects"),
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_WORK_TREE": str(self.root),
            }
        )
        self._environment = environment
        return self

    def __exit__(self, *_: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()

    def run(self, *args: str) -> str:
        if not self.is_repository or self._environment is None:
            raise AuditError("Git query requested outside an isolated repository context")
        try:
            result = subprocess.run(
                [
                    "git",
                    "--no-optional-locks",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "-c",
                    "submodule.recurse=false",
                    *args,
                ],
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
                env=self._environment,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise AuditError(f"Git query timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
        except OSError as exc:
            raise AuditError(f"Git query could not start: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            suffix = f": {detail[0]}" if detail else ""
            raise AuditError(f"Git {' '.join(args)} failed{suffix}")
        return result.stdout


def load_signatures() -> dict[str, Any]:
    data = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("signature data must be an object")
    return data


def tracked_files(root: Path, git: SafeGit) -> list[Path]:
    if git.is_repository:
        output = git.run("ls-files", "-z", "--cached", "--others", "--exclude-standard")
        return sorted(
            (root / item for item in output.split("\0") if item),
            key=lambda item: item.relative_to(root).as_posix(),
        )
    candidates: list[Path] = []
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in SKIPPED_PARTS)
        base = Path(directory)
        candidates.extend(base / name for name in sorted(files))
        candidates.extend(base / name for name in names if (base / name).is_symlink())
    return sorted(candidates, key=lambda item: item.relative_to(root).as_posix())


def scannable(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in SKIPPED_PARTS for part in relative.parts):
        return False
    if path.name in SKIPPED_NAMES or path.name.startswith(".env."):
        return False
    if path.suffix.lower() in SKIPPED_SUFFIXES:
        return False
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AuditError(f"cannot inspect {relative.as_posix()}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return False
    if metadata.st_size > MAX_FILE_SIZE:
        raise AuditError(f"scannable file exceeds {MAX_FILE_SIZE} bytes: {relative.as_posix()}")
    return True


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
    if not path.exists():
        return False
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AuditError(f"cannot inspect explicit input {path.relative_to(root)}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise AuditError(f"explicit input is not a regular file: {path.relative_to(root)}")
    if metadata.st_size > MAX_FILE_SIZE:
        raise AuditError(
            f"explicit input exceeds {MAX_FILE_SIZE} bytes: {path.relative_to(root)}"
        )
    return True


def read_explicit_text(root: Path, path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AuditError(f"cannot read explicit input {path.relative_to(root)} as UTF-8: {exc}") from exc


def enabled_plugins_from_settings(root: Path, path: Path) -> dict[str, bool]:
    try:
        settings = json.loads(read_explicit_text(root, path))
    except json.JSONDecodeError as exc:
        raise AuditError(f"invalid runtime settings JSON in {path.relative_to(root)}: {exc}") from exc
    if not isinstance(settings, dict):
        raise AuditError(f"runtime settings must be an object: {path.relative_to(root)}")
    enabled = settings.get("enabledPlugins", {})
    selectors: dict[str, bool] = {}
    if isinstance(enabled, dict):
        items = enabled.items()
        if any(not isinstance(key, str) or not isinstance(value, bool) for key, value in items):
            raise AuditError(f"enabledPlugins must map strings to booleans: {path.relative_to(root)}")
        selectors = dict(enabled)
    elif isinstance(enabled, list):
        if any(not isinstance(value, str) for value in enabled):
            raise AuditError(f"enabledPlugins must contain only strings: {path.relative_to(root)}")
        selectors = dict.fromkeys(enabled, True)
    else:
        raise AuditError(f"enabledPlugins must be an object or array: {path.relative_to(root)}")
    if len(selectors) > MAX_ENABLED_PLUGINS:
        raise AuditError(
            f"enabledPlugins exceeds {MAX_ENABLED_PLUGINS} entries: {path.relative_to(root)}"
        )
    for selector in selectors:
        if not selector or len(selector) > MAX_PLUGIN_ID_LENGTH:
            raise AuditError(f"invalid enabled plugin identifier in {path.relative_to(root)}")
    return selectors


def ignored_memory_integrations(root: Path, runtime_root: str) -> list[str]:
    integrations: list[str] = []
    for relative_root in (Path(runtime_root), Path("scripts")):
        start = root / relative_root
        if not start.is_dir() or start.is_symlink():
            continue
        for directory, names, files in os.walk(start, followlinks=False):
            names[:] = sorted(name for name in names if name not in SKIPPED_PARTS)
            base = Path(directory)
            for name in names:
                candidate = base / name
                relative = candidate.relative_to(root)
                if candidate.is_symlink() and any(
                    "memory" in part.lower() for part in relative.parts
                ):
                    integrations.append(relative.as_posix())
            for name in sorted(files):
                candidate = base / name
                relative = candidate.relative_to(root)
                if "memory" in name.lower() and "link" in name.lower():
                    integrations.append(relative.as_posix())
    return integrations


def audit(root: Path, signatures: dict[str, Any]) -> dict[str, Any]:
    with SafeGit(root) as git:
        return audit_in_context(root, signatures, git)


def audit_in_context(root: Path, signatures: dict[str, Any], git: SafeGit) -> dict[str, Any]:
    paths = signatures["paths"]
    is_git = git.is_repository
    dirty_count = 0
    worktree_count = git.worktree_count
    if is_git:
        dirty = git.run("status", "--porcelain", "--untracked-files=all")
        dirty_count = len([line for line in dirty.splitlines() if line])

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
        agent_text = read_explicit_text(root, agent_path)
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
        for number, line in enumerate(read_explicit_text(root, reference_path).splitlines(), 1):
            if line.lstrip().startswith("@"):
                imports.append(f"{paths['reference_guidance']}:{number}")
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

    settings_evidence: list[str] = []
    enabled_state: dict[str, bool] = {}
    for settings_key, finding_id, label in (
        ("settings", "runtime-settings-symlink", "Runtime settings"),
        ("settings_local", "runtime-local-settings-symlink", "Local runtime settings"),
    ):
        settings_path = root / paths[settings_key]
        if safe_explicit_file(root, settings_path, findings, finding_id, label):
            enabled_state.update(enabled_plugins_from_settings(root, settings_path))
            settings_evidence.append(paths[settings_key])
    inventory["enabledPlugins"] = sorted(
        selector for selector, enabled in enabled_state.items() if enabled
    )
    if inventory["enabledPlugins"]:
        add_finding(
            findings,
            "runtime-plugins-enabled",
            "info",
            "plugins",
            "Reference-runtime plugins are enabled.",
            "Map their capabilities before changing installation state.",
            settings_evidence,
        )

    candidates = tracked_files(root, git)
    memory_integrations: list[str] = []
    for path in candidates:
        relative = path.relative_to(root)
        if any(part in SKIPPED_PARTS for part in relative.parts):
            continue
        has_memory_name = any("memory" in part.lower() for part in relative.parts)
        is_link_helper = "memory" in path.name.lower() and "link" in path.name.lower()
        if is_link_helper or (path.is_symlink() and has_memory_name):
            memory_integrations.append(relative.as_posix())
    memory_integrations.extend(ignored_memory_integrations(root, paths["runtime_root"]))
    memory_integrations = sorted(set(memory_integrations))[:MAX_EVIDENCE_PER_PATTERN]
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
            evidence.extend(settings_evidence)
    for path in candidates:
        if not scannable(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AuditError(f"cannot scan {relative} as UTF-8: {exc}") from exc
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
    except (
        AuditError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"AUDIT_ERROR {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
