#!/usr/bin/env python3
"""Produce a deterministic, read-only agent-adoption audit."""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any


SIGNATURES_PATH = Path(__file__).with_name("signatures.json")
MAX_FILE_SIZE = 256 * 1024
MAX_EVIDENCE_PER_PATTERN = 20
MAX_ENABLED_PLUGINS = 100
MAX_PLUGIN_ID_LENGTH = 256
GIT_TIMEOUT_SECONDS = 10
AUDIT_TIMEOUT_SECONDS = 30
MAX_GIT_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_GIT_ERROR_BYTES = 64 * 1024
MAX_GIT_METADATA_BYTES = 4 * 1024 * 1024
MAX_GIT_INDEX_BYTES = 32 * 1024 * 1024
MAX_SHARED_INDEX_FILES = 32
MAX_SCAN_PATHS = 50_000
MAX_SCAN_PATH_BYTES = 8 * 1024 * 1024
MAX_SCANNED_CONTENT_BYTES = 16 * 1024 * 1024
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
PROSE_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}


class AuditError(RuntimeError):
    """The audit could not complete safely and must fail closed."""


def ensure_before_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise AuditError(f"audit timed out after {AUDIT_TIMEOUT_SECONDS} seconds")


def display_path(path: Path) -> str:
    """Render filesystem bytes deterministically without raw surrogate output."""
    return os.fsencode(path.as_posix()).decode("utf-8", "backslashreplace")


def secure_io_supported() -> bool:
    """Return whether descriptor-relative, no-follow reads are available."""
    return (
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and os.open in getattr(os, "supports_dir_fd", set())
    )


class RootAnchor:
    """Keep the audited directory bound to one stable POSIX descriptor."""

    def __init__(self, root: Path):
        self.root = root
        self.descriptor = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            metadata = os.fstat(self.descriptor)
            self.identity = (metadata.st_dev, metadata.st_ino)
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self) -> None:
        try:
            metadata = self.root.lstat()
        except OSError as exc:
            raise AuditError("audit target changed during inspection") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != self.identity
        ):
            raise AuditError("audit target changed during inspection")

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def __enter__(self) -> "RootAnchor":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def open_relative_directory(anchor: RootAnchor, relative: Path) -> int:
    """Open a directory below the anchored root without following links."""
    anchor.verify()
    current = os.dup(anchor.descriptor)
    try:
        for part in relative.parts:
            descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            os.close(current)
            current = descriptor
        return current
    except BaseException:
        os.close(current)
        raise


def inspect_relative(
    anchor: RootAnchor, relative: Path
) -> tuple[os.stat_result | None, Path | None]:
    """Inspect a relative path without following any component symlink."""
    anchor.verify()
    current = os.dup(anchor.descriptor)
    walked = Path()
    try:
        for index, part in enumerate(relative.parts):
            walked /= part
            try:
                metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            except (FileNotFoundError, NotADirectoryError):
                return None, None
            if stat.S_ISLNK(metadata.st_mode):
                return metadata, walked
            if index == len(relative.parts) - 1:
                return metadata, None
            if not stat.S_ISDIR(metadata.st_mode):
                return None, None
            descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            os.close(current)
            current = descriptor
        return os.fstat(current), None
    finally:
        os.close(current)


def read_bounded_at(
    base_descriptor: int,
    relative: Path,
    label: str,
    maximum: int,
    *,
    missing_ok: bool = False,
) -> bytes | None:
    current = os.dup(base_descriptor)
    descriptor = -1
    try:
        for part in relative.parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            os.close(current)
            current = child
        try:
            descriptor = os.open(
                relative.parts[-1],
                os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                dir_fd=current,
            )
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AuditError(f"{label} is not a regular file")
        if metadata.st_size > maximum:
            raise AuditError(f"{label} exceeds {maximum} bytes")
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > maximum:
            raise AuditError(f"{label} exceeds {maximum} bytes")
        return bytes(data)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ENOTDIR) and missing_ok:
            return None
        raise AuditError(f"cannot read {label}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(current)


def read_text_at(
    base_descriptor: int,
    relative: Path,
    label: str,
    maximum: int,
    *,
    missing_ok: bool = False,
) -> str | None:
    data = read_bounded_at(
        base_descriptor, relative, label, maximum, missing_ok=missing_ok
    )
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError(f"{label} is not valid UTF-8") from exc


def open_directory_at(base_descriptor: int, relative: Path, label: str) -> int:
    current = os.dup(base_descriptor)
    try:
        for part in relative.parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            os.close(current)
            current = child
        return current
    except OSError as exc:
        os.close(current)
        raise AuditError(f"cannot open {label}: {exc}") from exc


def verify_directory_identity(path: Path, descriptor: int, label: str) -> None:
    try:
        path_metadata = path.lstat()
        descriptor_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise AuditError(f"{label} changed during inspection") from exc
    if (
        not stat.S_ISDIR(path_metadata.st_mode)
        or (path_metadata.st_dev, path_metadata.st_ino)
        != (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
    ):
        raise AuditError(f"{label} changed during inspection")


def resolve_git_executable(root: Path) -> str:
    safe_entries: list[str] = []
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        resolved = Path(entry).resolve()
        if resolved == root or root in resolved.parents:
            continue
        safe_entries.append(str(resolved))
    candidate = shutil.which("git", path=os.pathsep.join(safe_entries))
    if candidate is None:
        raise AuditError("cannot find Git on an absolute trusted PATH entry")
    resolved_candidate = Path(candidate).resolve()
    if not resolved_candidate.is_file() or not os.access(resolved_candidate, os.X_OK):
        raise AuditError("resolved Git executable is not a regular executable file")
    return str(resolved_candidate)


def read_bounded_relative_metadata(
    anchor: RootAnchor, relative: Path, label: str, maximum: int
) -> str:
    parent = open_relative_directory(anchor, relative.parent)
    descriptor = -1
    try:
        descriptor = os.open(
            relative.name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=parent,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AuditError(f"{label} is not a regular file")
        if metadata.st_size > maximum:
            raise AuditError(f"{label} exceeds {maximum} bytes")
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > maximum:
            raise AuditError(f"{label} exceeds {maximum} bytes")
        try:
            return bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuditError(f"{label} is not valid UTF-8") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _git_directories(
    root: Path, anchor: RootAnchor, deadline: float
) -> tuple[Path, Path, int, int, int, dict[str, str]] | None:
    ensure_before_deadline(deadline)
    dot_git = root / ".git"
    try:
        dot_git_metadata = os.stat(
            ".git", dir_fd=anchor.descriptor, follow_symlinks=False
        )
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(dot_git_metadata.st_mode):
        raise AuditError(".git is a symbolic link; refusing to load repository metadata")
    if stat.S_ISDIR(dot_git_metadata.st_mode):
        worktree_git_dir = dot_git
        worktree_descriptor = open_directory_at(anchor.descriptor, Path(".git"), ".git")
    elif stat.S_ISREG(dot_git_metadata.st_mode):
        marker = read_bounded_relative_metadata(
            anchor, Path(".git"), ".git indirection", 4096
        ).strip()
        if not marker.startswith("gitdir: "):
            raise AuditError("invalid .git indirection")
        worktree_git_dir = Path(marker[8:])
        if not worktree_git_dir.is_absolute():
            worktree_git_dir = dot_git.parent / worktree_git_dir
        worktree_git_dir = worktree_git_dir.resolve()
        if not worktree_git_dir.is_dir():
            raise AuditError(".git indirection does not name a directory")
        worktree_descriptor = os.open(
            worktree_git_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    else:
        raise AuditError("unsupported .git metadata type")

    common_git_dir = worktree_git_dir
    commondir_text = read_text_at(
        worktree_descriptor,
        Path("commondir"),
        "Git commondir",
        4096,
        missing_ok=True,
    )
    if commondir_text is not None:
        common_git_dir = Path(commondir_text.strip())
        if not common_git_dir.is_absolute():
            common_git_dir = worktree_git_dir / common_git_dir
        common_git_dir = common_git_dir.resolve()
    common_descriptor = os.open(
        common_git_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    objects_descriptor = -1
    try:
        objects_descriptor = open_directory_at(
            common_descriptor, Path("objects"), "Git object directory"
        )
        repository_format = _read_repository_format(common_descriptor)
        if stat.S_ISREG(dot_git_metadata.st_mode):
            backlink_text = read_text_at(
                worktree_descriptor,
                Path("gitdir"),
                "Git worktree backlink",
                4096,
                missing_ok=True,
            )
            linked_worktree = False
            if backlink_text is not None:
                backlink = Path(backlink_text.strip())
                if not backlink.is_absolute():
                    backlink = worktree_git_dir / backlink
                linked_worktree = (
                    backlink.resolve() == dot_git.resolve()
                    and worktree_git_dir.parent.resolve()
                    == (common_git_dir / "worktrees").resolve()
                )
            configured_worktree = repository_format.get("core.worktree")
            configured_binding = False
            if configured_worktree:
                configured = Path(configured_worktree)
                if not configured.is_absolute():
                    configured = common_git_dir / configured
                configured_binding = configured.resolve() == root.resolve()
            if not linked_worktree and not configured_binding:
                raise AuditError(
                    ".git indirection is not bound to the audit target; "
                    "unbound --separate-git-dir layouts are unsupported"
                )
    except BaseException:
        if objects_descriptor >= 0:
            os.close(objects_descriptor)
        os.close(common_descriptor)
        os.close(worktree_descriptor)
        raise
    anchor.verify()
    return (
        worktree_git_dir,
        common_git_dir,
        worktree_descriptor,
        common_descriptor,
        objects_descriptor,
        repository_format,
    )


def _read_repository_format(common_descriptor: int) -> dict[str, str]:
    text = read_text_at(
        common_descriptor,
        Path("config"),
        "Git repository config",
        256 * 1024,
        missing_ok=True,
    )
    if text is None:
        return {}
    section = ""
    values: dict[str, str] = {}
    approved = {
        ("core", "repositoryformatversion"),
        ("core", "worktree"),
        ("extensions", "objectformat"),
        ("extensions", "refstorage"),
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.fullmatch(r"\[([A-Za-z0-9.-]+)(?:\s+\"[^\"]*\")?\]", line)
        if match:
            section = match.group(1).lower()
            continue
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        normalized = (section, key.lower())
        if normalized in approved:
            values[f"{section}.{key.lower()}"] = (
                value if normalized == ("core", "worktree") else value.lower()
            )
    object_format = values.get("extensions.objectformat", "sha1")
    ref_storage = values.get("extensions.refstorage", "files")
    if object_format not in {"sha1", "sha256"}:
        raise AuditError(f"unsupported Git object format: {object_format}")
    if ref_storage not in {"files", "reftable"}:
        raise AuditError(f"unsupported Git ref storage: {ref_storage}")
    return values


def _read_head(worktree_descriptor: int, common_descriptor: int) -> str:
    head_text = read_text_at(worktree_descriptor, Path("HEAD"), "Git HEAD", 4096)
    assert head_text is not None
    head = head_text.strip()
    if re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        return head.lower()
    if not head.startswith("ref: refs/") or ".." in Path(head[5:]).parts:
        raise AuditError("Git HEAD is malformed")
    reference = head[5:]
    for base in (worktree_descriptor, common_descriptor):
        loose_text = read_text_at(
            base, Path(reference), "Git HEAD reference", 4096, missing_ok=True
        )
        if loose_text is not None:
            value = loose_text.strip()
            if re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
                return value.lower()
            raise AuditError("Git HEAD reference is malformed")
    packed_text = read_text_at(
        common_descriptor,
        Path("packed-refs"),
        "packed Git references",
        MAX_GIT_METADATA_BYTES,
        missing_ok=True,
    )
    if packed_text is not None:
        lines = packed_text.splitlines()
        for line in lines:
            fields = line.split(" ", 1)
            if len(fields) == 2 and fields[1] == reference and re.fullmatch(
                r"[0-9a-fA-F]{40,64}", fields[0]
            ):
                return fields[0].lower()
    return head


def copy_git_index(worktree_descriptor: int, isolated: Path) -> None:
    total = 0
    names = ["index"]
    with os.scandir(worktree_descriptor) as entries:
        shared = sorted(
            entry.name
            for entry in entries
            if entry.name.startswith("sharedindex.") and not entry.is_dir(follow_symlinks=False)
        )
    if len(shared) > MAX_SHARED_INDEX_FILES:
        raise AuditError(f"Git shared index count exceeds {MAX_SHARED_INDEX_FILES}")
    names.extend(shared)
    for name in names:
        data = read_bounded_at(
            worktree_descriptor,
            Path(name),
            f"Git {name}",
            MAX_GIT_INDEX_BYTES,
            missing_ok=name == "index",
        )
        if data is None:
            continue
        total += len(data)
        if total > MAX_GIT_INDEX_BYTES:
            raise AuditError(f"Git index data exceeds {MAX_GIT_INDEX_BYTES} bytes")
        (isolated / name).write_bytes(data)


class SafeGit:
    """Run read-only Git queries without loading any target-controlled config."""

    def __init__(
        self,
        root: Path,
        deadline: float | None = None,
        anchor: RootAnchor | None = None,
    ):
        self.root = root
        self.git_executable = resolve_git_executable(root)
        self.deadline = deadline or (time.monotonic() + AUDIT_TIMEOUT_SECONDS)
        self.anchor = anchor or RootAnchor(root)
        self._owns_anchor = anchor is None
        try:
            directories = _git_directories(root, self.anchor, self.deadline)
        except BaseException:
            if self._owns_anchor:
                self.anchor.close()
            raise
        self.is_repository = directories is not None
        self.worktree_count = 0
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._environment: dict[str, str] | None = None
        if directories is None:
            return
        (
            self.worktree_git_dir,
            self.common_git_dir,
            self.worktree_descriptor,
            self.common_descriptor,
            self.objects_descriptor,
            self.repository_format,
        ) = directories
        linked = 0
        try:
            worktrees_descriptor = open_directory_at(
                self.common_descriptor, Path("worktrees"), "Git worktrees directory"
            )
        except AuditError:
            worktrees_descriptor = -1
        if worktrees_descriptor >= 0:
            with os.scandir(worktrees_descriptor) as entries:
                for item in entries:
                    ensure_before_deadline(self.deadline)
                    if item.is_dir(follow_symlinks=False):
                        linked += 1
                    if linked > MAX_SCAN_PATHS:
                        raise AuditError(f"Git worktree count exceeds {MAX_SCAN_PATHS}")
            os.close(worktrees_descriptor)
        self.worktree_count = linked + 1

    def __enter__(self) -> "SafeGit":
        if not self.is_repository:
            return self
        self._temporary = tempfile.TemporaryDirectory(prefix="agent-adoption-git-")
        isolated = Path(self._temporary.name)
        (isolated / "objects").mkdir()
        (isolated / "refs" / "heads").mkdir(parents=True)
        config_lines = ["[core]", "\tbare = false"]
        repository_version = self.repository_format.get("core.repositoryformatversion")
        if repository_version is not None:
            config_lines.append(f"\trepositoryformatversion = {repository_version}")
        extensions = {
            key.split(".", 1)[1]: value
            for key, value in self.repository_format.items()
            if key.startswith("extensions.")
        }
        if extensions:
            config_lines.append("[extensions]")
            config_lines.extend(f"\t{key} = {value}" for key, value in sorted(extensions.items()))
        (isolated / "config").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
        (isolated / "HEAD").write_text(
            f"{_read_head(self.worktree_descriptor, self.common_descriptor)}\n",
            encoding="utf-8",
        )
        copy_git_index(self.worktree_descriptor, isolated)
        self._pass_descriptors = {
            self.anchor.descriptor,
            self.worktree_descriptor,
            self.common_descriptor,
            self.objects_descriptor,
        }
        if extensions.get("refstorage") == "reftable":
            self.reftable_descriptor = open_directory_at(
                self.common_descriptor, Path("reftable"), "Git reftable storage"
            )
            self._pass_descriptors.add(self.reftable_descriptor)
            (isolated / "reftable").symlink_to(
                self.common_git_dir / "reftable", target_is_directory=True
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
                "GIT_INDEX_FILE": str(isolated / "index"),
                "GIT_OBJECT_DIRECTORY": str(self.common_git_dir / "objects"),
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_WORK_TREE": str(self.root),
            }
        )
        self._environment = environment
        return self

    def verify_git_layout(self) -> None:
        self.anchor.verify()
        verify_directory_identity(
            self.worktree_git_dir,
            self.worktree_descriptor,
            "Git worktree metadata",
        )
        verify_directory_identity(
            self.common_git_dir,
            self.common_descriptor,
            "Git common metadata",
        )
        verify_directory_identity(
            self.common_git_dir / "objects",
            self.objects_descriptor,
            "Git object directory",
        )
        if getattr(self, "reftable_descriptor", -1) >= 0:
            verify_directory_identity(
                self.common_git_dir / "reftable",
                self.reftable_descriptor,
                "Git reftable storage",
            )

    def __exit__(self, *_: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
        if self._owns_anchor:
            self.anchor.close()
        for name in ("reftable_descriptor", "objects_descriptor", "common_descriptor", "worktree_descriptor"):
            descriptor = getattr(self, name, -1)
            if descriptor >= 0:
                os.close(descriptor)
                setattr(self, name, -1)

    def run(self, *args: str, decode_errors: str = "strict") -> str:
        if not self.is_repository or self._environment is None:
            raise AuditError("Git query requested outside an isolated repository context")
        ensure_before_deadline(self.deadline)
        self.verify_git_layout()
        try:
            process = subprocess.Popen(
                [
                    self.git_executable,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment,
                pass_fds=tuple(self._pass_descriptors),
            )
        except OSError as exc:
            raise AuditError(f"Git query could not start: {exc}") from exc
        assert process.stdout is not None and process.stderr is not None
        selected = selectors.DefaultSelector()
        selected.register(process.stdout, selectors.EVENT_READ, ("stdout", MAX_GIT_OUTPUT_BYTES))
        selected.register(process.stderr, selectors.EVENT_READ, ("stderr", MAX_GIT_ERROR_BYTES))
        output = {"stdout": bytearray(), "stderr": bytearray()}
        command_deadline = min(self.deadline, time.monotonic() + GIT_TIMEOUT_SECONDS)
        try:
            while selected.get_map():
                remaining = command_deadline - time.monotonic()
                if remaining <= 0:
                    raise AuditError(f"Git query timed out after {GIT_TIMEOUT_SECONDS} seconds")
                events = selected.select(timeout=remaining)
                if not events:
                    raise AuditError(f"Git query timed out after {GIT_TIMEOUT_SECONDS} seconds")
                for key, _ in events:
                    name, maximum = key.data
                    chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                    if not chunk:
                        selected.unregister(key.fileobj)
                        continue
                    output[name].extend(chunk)
                    if len(output[name]) > maximum:
                        raise AuditError(f"Git {name} exceeds {maximum} bytes")
            remaining = command_deadline - time.monotonic()
            if remaining <= 0:
                raise AuditError(f"Git query timed out after {GIT_TIMEOUT_SECONDS} seconds")
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise AuditError(f"Git query timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
        except AuditError:
            process.kill()
            process.wait()
            raise
        finally:
            selected.close()
            process.stdout.close()
            process.stderr.close()
        try:
            stdout = output["stdout"].decode("utf-8", errors=decode_errors)
            stderr = output["stderr"].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuditError("Git query returned non-UTF-8 output") from exc
        if returncode != 0:
            detail = stderr.strip().splitlines()
            suffix = f": {detail[0]}" if detail else ""
            raise AuditError(f"Git {' '.join(args)} failed{suffix}")
        self.verify_git_layout()
        return stdout


def load_signatures() -> dict[str, Any]:
    data = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("signature data must be an object")
    return data


def bounded_walk(
    root: Path,
    anchor: RootAnchor,
    start: Path,
    deadline: float,
    label: str,
    budget: dict[str, int] | None = None,
) -> list[tuple[Path, bool]]:
    """Stream a deterministic, no-follow tree inventory below an anchored root."""
    state = budget if budget is not None else {"paths": 0, "bytes": 0, "pruned": 0}
    state.setdefault("pruned", 0)
    pending = [start]
    entries_found: list[tuple[Path, bool]] = []
    while pending:
        ensure_before_deadline(deadline)
        relative_directory = pending.pop()
        try:
            descriptor = open_relative_directory(anchor, relative_directory)
        except OSError as exc:
            if relative_directory == start and exc.errno in (
                errno.ENOENT,
                errno.ENOTDIR,
                errno.ELOOP,
            ):
                return []
            raise AuditError(
                f"{label} directory changed during inspection: "
                f"{relative_directory.as_posix() or '.'}"
            ) from exc
        directories: list[Path] = []
        try:
            with os.scandir(descriptor) as scanned:
                for entry in scanned:
                    ensure_before_deadline(deadline)
                    relative = relative_directory / entry.name
                    state["paths"] += 1
                    state["bytes"] += len(os.fsencode(relative.as_posix()))
                    if state["paths"] > MAX_SCAN_PATHS:
                        raise AuditError(f"{label} path count exceeds {MAX_SCAN_PATHS}")
                    if state["bytes"] > MAX_SCAN_PATH_BYTES:
                        raise AuditError(
                            f"{label} paths exceed {MAX_SCAN_PATH_BYTES} bytes"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKIPPED_PARTS:
                            directories.append(relative)
                        else:
                            state["pruned"] += 1
                    else:
                        entries_found.append((root / relative, entry.is_symlink()))
        finally:
            os.close(descriptor)
        pending.extend(sorted(directories, reverse=True))
    return sorted(
        entries_found, key=lambda item: item[0].relative_to(root).as_posix()
    )


def tracked_files(
    root: Path, git: SafeGit, anchor: RootAnchor, deadline: float
) -> tuple[list[Path], int, int]:
    if git.is_repository:
        output = git.run(
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            decode_errors="surrogateescape",
        )
        items = [item for item in output.split("\0") if item]
        if len(items) > MAX_SCAN_PATHS:
            raise AuditError(f"scan candidate count exceeds {MAX_SCAN_PATHS}")
        if sum(len(os.fsencode(item)) for item in items) > MAX_SCAN_PATH_BYTES:
            raise AuditError(f"scan candidate paths exceed {MAX_SCAN_PATH_BYTES} bytes")
        for item in items:
            candidate = Path(item)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise AuditError(f"Git returned unsafe path: {display_path(candidate)}")
        ignored_output = git.run(
            "ls-files",
            "-z",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "--no-empty-directory",
            decode_errors="surrogateescape",
        )
        ignored = [item for item in ignored_output.split("\0") if item]
        if len(ignored) > MAX_SCAN_PATHS:
            raise AuditError(f"ignored Git path count exceeds {MAX_SCAN_PATHS}")
        if sum(len(os.fsencode(item)) for item in ignored) > MAX_SCAN_PATH_BYTES:
            raise AuditError(f"ignored Git paths exceed {MAX_SCAN_PATH_BYTES} bytes")
        return (
            sorted(
                (root / item for item in items),
                key=lambda item: item.relative_to(root).as_posix(),
            ),
            len(ignored),
            0,
        )
    budget = {"paths": 0, "bytes": 0, "pruned": 0}
    candidates = [
        path
        for path, _ in bounded_walk(
            root, anchor, Path(), deadline, "scan candidate", budget
        )
    ]
    return candidates, 0, budget["pruned"]


def content_excluded(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in SKIPPED_PARTS for part in relative.parts):
        return True
    if path.name in SKIPPED_NAMES or path.name.startswith(".env."):
        return True
    if path.suffix.lower() in SKIPPED_SUFFIXES:
        return True
    return False


def read_candidate_text(
    root: Path, anchor: RootAnchor, path: Path
) -> tuple[str | None, str | None]:
    relative = path.relative_to(root)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise AuditError(f"unsafe scan candidate: {display_path(relative)}")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if not no_follow and inspect_relative(anchor, relative)[1] is not None:
        return None, "symlink"
    current = -1
    descriptor = -1
    try:
        anchor.verify()
        current = os.dup(anchor.descriptor)
        for part in relative.parts[:-1]:
            child = os.open(part, directory_flags | no_follow, dir_fd=current)
            os.close(current)
            current = child
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NONBLOCK | no_follow,
            dir_fd=current,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "non-regular"
        if metadata.st_size > MAX_FILE_SIZE:
            return None, "oversize"
        data = bytearray()
        while len(data) <= MAX_FILE_SIZE:
            chunk = os.read(descriptor, min(64 * 1024, MAX_FILE_SIZE + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_FILE_SIZE:
            return None, "oversize"
        try:
            return bytes(data).decode("utf-8"), None
        except UnicodeDecodeError:
            return None, "non-utf8"
    except OSError as exc:
        if exc.errno == errno.ELOOP or inspect_relative(anchor, relative)[1] is not None:
            return None, "symlink"
        return None, f"unreadable:{exc.errno}"
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if current >= 0:
            os.close(current)


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


def read_explicit_text(
    root: Path,
    anchor: RootAnchor,
    path: Path,
    findings: list[dict[str, Any]],
    finding_id: str,
    label: str,
) -> str | None:
    relative = path.relative_to(root)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise AuditError(f"unsafe explicit input: {relative.as_posix()}")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY
    current = -1
    descriptor = -1
    try:
        anchor.verify()
        current = os.dup(anchor.descriptor)
        for part in relative.parts[:-1]:
            child = os.open(
                part, directory_flags | os.O_NOFOLLOW, dir_fd=current
            )
            os.close(current)
            current = child
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=current,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AuditError(f"explicit input is not a regular file: {relative.as_posix()}")
        if metadata.st_size > MAX_FILE_SIZE:
            raise AuditError(
                f"explicit input exceeds {MAX_FILE_SIZE} bytes: {relative.as_posix()}"
            )
        data = bytearray()
        while len(data) <= MAX_FILE_SIZE:
            chunk = os.read(
                descriptor, min(64 * 1024, MAX_FILE_SIZE + 1 - len(data))
            )
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_FILE_SIZE:
            raise AuditError(
                f"explicit input exceeds {MAX_FILE_SIZE} bytes: {relative.as_posix()}"
            )
        try:
            return bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuditError(
                f"cannot read explicit input {relative.as_posix()} as UTF-8: {exc}"
            ) from exc
    except FileNotFoundError:
        return None
    except OSError as exc:
        _, symlink_relative = inspect_relative(anchor, relative)
        symlink = root / symlink_relative if symlink_relative is not None else None
        if symlink is None:
            raise AuditError(f"cannot read explicit input {relative.as_posix()}: {exc}") from exc
        add_finding(
            findings,
            finding_id,
            "warning",
            "scope",
            f"{label} is a symbolic link and was not followed.",
            "Inspect the link target explicitly before including it in an adoption audit.",
            [(symlink or path).relative_to(root).as_posix()],
            "approval-required",
        )
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if current >= 0:
            os.close(current)


def enabled_plugins_from_settings(root: Path, path: Path, text: str) -> dict[str, bool]:
    try:
        settings = json.loads(text)
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
        if not selector.strip() or len(selector) > MAX_PLUGIN_ID_LENGTH:
            raise AuditError(f"invalid enabled plugin identifier in {path.relative_to(root)}")
    return selectors


def ignored_memory_integrations(
    root: Path,
    anchor: RootAnchor,
    runtime_root: str,
    deadline: float,
) -> list[str]:
    integrations: list[str] = []
    budget = {"paths": 0, "bytes": 0, "pruned": 0}
    for relative_root in (Path(runtime_root), Path("scripts")):
        for candidate, is_symlink in bounded_walk(
            root,
            anchor,
            relative_root,
            deadline,
            "memory integration scan",
            budget,
        ):
            relative = candidate.relative_to(root)
            if is_symlink and any("memory" in part.lower() for part in relative.parts):
                integrations.append(display_path(relative))
            elif "memory" in candidate.name.lower() and "link" in candidate.name.lower():
                integrations.append(display_path(relative))
    return integrations


def content_pattern_matches(
    pattern_id: str,
    pattern: re.Pattern[str],
    path: Path,
    line: str,
    in_code_block: bool = False,
) -> bool:
    matches = list(pattern.finditer(line))
    if not matches:
        return False
    if pattern_id != "claude-cli" or path.suffix.lower() not in PROSE_SUFFIXES:
        return True
    if in_code_block:
        return True
    code_spans = [match.span(2) for match in re.finditer(r"(`+)(.*?)\1", line)]
    for match in matches:
        if any(start <= match.start() and match.end() <= end for start, end in code_spans):
            return True
        prefix = line[: match.start()]
        if re.fullmatch(r"\s*(?:>\s*)*(?:(?:[-+*]|\d+[.)])\s+)?", prefix):
            suffix = line[match.end() :]
            if suffix.strip() or prefix.strip():
                return True
        if match.start() > 0 and line[match.start() - 1] in ";&|":
            return True
    return False


def audit(root: Path, signatures: dict[str, Any]) -> dict[str, Any]:
    if not secure_io_supported():
        raise AuditError(
            "project-adoption requires POSIX descriptor-relative no-follow file I/O"
        )
    deadline = time.monotonic() + AUDIT_TIMEOUT_SECONDS
    with RootAnchor(root) as anchor:
        with SafeGit(root, deadline, anchor) as git:
            return audit_in_context(root, signatures, git, anchor, deadline)


def audit_in_context(
    root: Path,
    signatures: dict[str, Any],
    git: SafeGit,
    anchor: RootAnchor,
    deadline: float,
) -> dict[str, Any]:
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
    agent_text = read_explicit_text(
        root,
        anchor,
        agent_path,
        findings,
        "agents-guidance-symlink",
        "Shared agent guidance",
    )
    agent_link_reported = any(
        finding["id"] == "agents-guidance-symlink" for finding in findings
    )
    if agent_text is None:
        if not agent_link_reported:
            add_finding(
                findings,
                "agents-guidance-missing",
                "warning",
                "guidance",
                "Shared agent guidance is missing.",
                "Draft an agent-neutral AGENTS.md and show it before writing.",
                change_class="safe-scaffolding",
            )
    else:
        inventory["agentGuidance"] = True
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

    reference_text = read_explicit_text(
        root,
        anchor,
        reference_path,
        findings,
        "reference-guidance-symlink",
        "Reference-runtime guidance",
    )
    if reference_text is not None:
        inventory["referenceGuidance"] = True
        imports: list[str] = []
        for number, line in enumerate(reference_text.splitlines(), 1):
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
        metadata, symlink_relative = inspect_relative(anchor, Path(paths[key]))
        if symlink_relative is not None and symlink_relative == Path(paths[key]):
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
        elif symlink_relative is not None:
            add_finding(
                findings,
                f"{finding_id}-ancestor-symlink",
                "warning",
                "scope",
                f"{message} could not be inventoried because an ancestor is a symbolic link.",
                "Inspect the link target explicitly before relying on project-state coverage.",
                [paths[key], symlink_relative.as_posix()],
                "approval-required",
            )
        elif metadata is not None:
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
    configured_selectors: set[str] = set()
    for settings_key, finding_id, label in (
        ("settings", "runtime-settings-symlink", "Runtime settings"),
        ("settings_local", "runtime-local-settings-symlink", "Local runtime settings"),
    ):
        settings_path = root / paths[settings_key]
        settings_text = read_explicit_text(
            root, anchor, settings_path, findings, finding_id, label
        )
        if settings_text is not None:
            configured = enabled_plugins_from_settings(root, settings_path, settings_text)
            configured_selectors.update(configured)
            enabled_state.update(configured)
            settings_evidence.append(paths[settings_key])
    inventory["configuredPlugins"] = sorted(configured_selectors)
    inventory["enabledPlugins"] = sorted(
        selector for selector, enabled in enabled_state.items() if enabled
    )
    configured_workflows = sorted(
        name
        for name in WORKFLOW_PLUGIN_NAMES
        if any(
            selector == name or selector.startswith(f"{name}@")
            for selector in inventory["configuredPlugins"]
        )
    )
    inventory["configuredWorkflowPlugins"] = configured_workflows
    if configured_workflows:
        add_finding(
            findings,
            "workflow-plugin-configuration",
            "info",
            "plugins",
            "Runtime settings configure workflow plugins, including disabled declarations.",
            "Map configured capabilities and preserve enabled or disabled state explicitly.",
            settings_evidence,
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

    candidates, git_ignored_path_count, pruned_directory_count = tracked_files(
        root, git, anchor, deadline
    )
    inventory["gitIgnoredPathCount"] = git_ignored_path_count
    inventory["prunedDirectoryCount"] = pruned_directory_count
    memory_integrations: list[str] = []
    for path in candidates:
        relative = path.relative_to(root)
        if any(part in SKIPPED_PARTS for part in relative.parts):
            continue
        has_memory_name = any("memory" in part.lower() for part in relative.parts)
        is_link_helper = "memory" in path.name.lower() and "link" in path.name.lower()
        _, symlink_relative = inspect_relative(anchor, relative)
        if is_link_helper or (symlink_relative is not None and has_memory_name):
            memory_integrations.append(display_path(relative))
    memory_integrations.extend(
        ignored_memory_integrations(root, anchor, paths["runtime_root"], deadline)
    )
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
    unscanned_count = 0
    policy_excluded_count = 0
    unscanned_evidence: list[str] = []
    scanned_content_bytes = 0
    for candidate_index, path in enumerate(candidates):
        ensure_before_deadline(deadline)
        if content_excluded(path, root):
            policy_excluded_count += 1
            continue
        text, reason = read_candidate_text(root, anchor, path)
        if reason is not None:
            unscanned_count += 1
            if len(unscanned_evidence) < MAX_EVIDENCE_PER_PATTERN:
                unscanned_evidence.append(
                    f"{display_path(path.relative_to(root))}:{reason}"
                )
        if text is None:
            continue
        content_bytes = len(text.encode("utf-8"))
        if scanned_content_bytes + content_bytes > MAX_SCANNED_CONTENT_BYTES:
            remaining = [
                skipped
                for skipped in candidates[candidate_index:]
                if not content_excluded(skipped, root)
            ]
            policy_excluded_count += sum(
                1
                for skipped in candidates[candidate_index:]
                if content_excluded(skipped, root)
            )
            unscanned_count += len(remaining)
            for skipped in remaining:
                if len(unscanned_evidence) >= MAX_EVIDENCE_PER_PATTERN:
                    break
                unscanned_evidence.append(
                    f"{display_path(skipped.relative_to(root))}:scan-budget"
                )
            break
        scanned_content_bytes += content_bytes
        relative = display_path(path.relative_to(root))
        fence_marker: str | None = None
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped_line = line.lstrip()
            fence_match = re.match(r"(`{3,}|~{3,})", stripped_line)
            fence_line = False
            if fence_match is not None:
                marker = fence_match.group(1)
                if fence_marker is None:
                    fence_line = True
                elif (
                    marker[0] == fence_marker[0]
                    and len(marker) >= len(fence_marker)
                    and not stripped_line[fence_match.end() :].strip()
                ):
                    fence_line = True
            scan_as_code = fence_marker is not None and not fence_line
            for pattern_id, _, pattern in compiled:
                evidence = pattern_evidence[pattern_id]
                if (
                    len(evidence) < MAX_EVIDENCE_PER_PATTERN
                    and content_pattern_matches(
                        pattern_id, pattern, path, line, scan_as_code
                    )
                ):
                    evidence.append(f"{relative}:{line_number}")
            for plugin_name, evidence in plugin_evidence.items():
                if (
                    relative not in settings_evidence
                    and len(evidence) < MAX_EVIDENCE_PER_PATTERN
                    and re.search(rf"(?<![A-Za-z0-9_-]){re.escape(plugin_name)}(?![A-Za-z0-9_-])", line)
                ):
                    evidence.append(f"{relative}:{line_number}")
            if fence_line:
                fence_marker = None if fence_marker is not None else marker

    inventory["unscannedFileCount"] = unscanned_count
    inventory["policyExcludedFileCount"] = policy_excluded_count
    inventory["scannedContentBytes"] = scanned_content_bytes
    if unscanned_count:
        add_finding(
            findings,
            "scan-incomplete",
            "warning",
            "scope",
            f"Content scanning skipped {unscanned_count} bounded, binary, unreadable, or linked candidate file(s).",
            "Review the listed paths manually when complete content coverage is required.",
            unscanned_evidence,
            "approval-required",
        )

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

    anchor.verify()
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
    inventory = report["inventory"]
    lines = [
        "Project adoption audit (read-only)",
        f"Root: {report['root']}",
        f"Findings: {report['summary']['warning']} warning(s), {report['summary']['info']} info",
        (
            "Coverage: "
            f"{inventory['scannedContentBytes']} content byte(s) scanned; "
            f"{inventory['unscannedFileCount']} unscanned candidate(s); "
            f"{inventory['policyExcludedFileCount']} policy-excluded candidate(s); "
            f"{inventory['gitIgnoredPathCount']} ignored Git path(s); "
            f"{inventory['prunedDirectoryCount']} pruned directory path(s)"
        ),
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
