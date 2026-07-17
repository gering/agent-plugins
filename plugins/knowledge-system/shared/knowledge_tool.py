#!/usr/bin/env python3
"""Deterministic, read-only query and index checks for project knowledge."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import stat
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any


MAX_FILES = 5_000
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_RESULTS = 10
MAX_DEPTH = 64
REQUIRED_FRONTMATTER = (
    "title",
    "createdAt",
    "updatedAt",
    "createdFrom",
    "updatedFrom",
    "reindexedAt",
    "pluginVersion",
    "prime",
)
NON_EMPTY_FRONTMATTER = REQUIRED_FRONTMATTER
DATE_FIELDS = ("createdAt", "updatedAt", "reindexedAt")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
INDEX_ENTRY_RE = re.compile(
    r"(?m)^\s*-\s+`([^`\n]+\.md)`(?:\s*(?:—|-|:)\s*(.*))?$"
)
TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
STOP_WORDS = {
    "a", "about", "an", "and", "auf", "aus", "bei", "bitte", "das", "dem",
    "den", "der", "die", "did", "do", "does", "ein", "eine", "einer", "erkläre",
    "explain", "for", "funktioniert", "für", "here", "hier", "how", "ich", "im",
    "in", "ist", "know", "knows", "mit", "of", "on", "project", "projekt", "show",
    "suche", "tell", "the", "to", "über", "und", "von", "was", "we", "what", "wie",
    "wir", "wissen", "work", "works", "zu",
}


class KnowledgeError(RuntimeError):
    """The knowledge store could not be inspected safely."""


@dataclass(frozen=True)
class KnowledgeFile:
    relative: str
    title: str
    body: str
    frontmatter: dict[str, str]


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    detail: str


def display_path(path: Path) -> str:
    return os.fsencode(path.as_posix()).decode("utf-8", "backslashreplace")


def file_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def secure_io_supported() -> bool:
    return (
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_NONBLOCK")
        and os.open in getattr(os, "supports_dir_fd", set())
        and os.stat in getattr(os, "supports_dir_fd", set())
    )


class StoreAnchor:
    """Bind all knowledge reads to stable directory descriptors."""

    def __init__(self, root_argument: str):
        if not secure_io_supported():
            raise KnowledgeError(
                "secure knowledge inspection requires POSIX descriptor-relative no-follow I/O"
            )
        root_input = Path(root_argument).expanduser().absolute()
        try:
            root_metadata = root_input.lstat()
        except FileNotFoundError as exc:
            raise KnowledgeError(f"missing project root: {display_path(root_input)}") from exc
        if stat.S_ISLNK(root_metadata.st_mode):
            raise KnowledgeError(f"refusing symlinked project root: {display_path(root_input)}")
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise KnowledgeError(f"project root is not a directory: {display_path(root_input)}")

        self.root = root_input.resolve(strict=True)
        self.knowledge = self.root / ".claude/knowledge"
        self.root_descriptor = -1
        self.runtime_descriptor = -1
        self.knowledge_descriptor = -1
        try:
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            self.root_descriptor = os.open(self.root, directory_flags)
            self.root_identity = self._identity(self.root_descriptor)
            self.runtime_descriptor = os.open(
                ".claude", directory_flags, dir_fd=self.root_descriptor
            )
            self.runtime_identity = self._identity(self.runtime_descriptor)
            self.knowledge_descriptor = os.open(
                "knowledge", directory_flags, dir_fd=self.runtime_descriptor
            )
            self.knowledge_identity = self._identity(self.knowledge_descriptor)
            self.verify()
        except FileNotFoundError as exc:
            self.close()
            raise KnowledgeError(
                f"missing knowledge directory: {display_path(self.knowledge)}"
            ) from exc
        except KnowledgeError:
            self.close()
            raise
        except (NotADirectoryError, OSError) as exc:
            self.close()
            raise KnowledgeError(
                f"unsafe knowledge directory: {display_path(self.knowledge)}"
            ) from exc

    @staticmethod
    def _identity(descriptor: int) -> tuple[int, int]:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise KnowledgeError("knowledge anchor is not a directory")
        return metadata.st_dev, metadata.st_ino

    def verify(self) -> None:
        try:
            root_metadata = self.root.lstat()
            runtime_metadata = os.stat(
                ".claude", dir_fd=self.root_descriptor, follow_symlinks=False
            )
            knowledge_metadata = os.stat(
                "knowledge", dir_fd=self.runtime_descriptor, follow_symlinks=False
            )
        except OSError as exc:
            raise KnowledgeError("knowledge store changed during inspection") from exc
        if (
            stat.S_ISLNK(root_metadata.st_mode)
            or (root_metadata.st_dev, root_metadata.st_ino) != self.root_identity
            or not stat.S_ISDIR(runtime_metadata.st_mode)
            or (runtime_metadata.st_dev, runtime_metadata.st_ino) != self.runtime_identity
            or not stat.S_ISDIR(knowledge_metadata.st_mode)
            or (knowledge_metadata.st_dev, knowledge_metadata.st_ino)
            != self.knowledge_identity
        ):
            raise KnowledgeError("knowledge store changed during inspection")

    def close(self) -> None:
        for attribute in (
            "knowledge_descriptor",
            "runtime_descriptor",
            "root_descriptor",
        ):
            descriptor = getattr(self, attribute, -1)
            if descriptor >= 0:
                os.close(descriptor)
                setattr(self, attribute, -1)

    def __enter__(self) -> "StoreAnchor":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def read_regular_file_at(
    directory_descriptor: int,
    name: str,
    shown_path: Path,
    expected: os.stat_result,
) -> str:
    if expected.st_size > MAX_FILE_BYTES:
        raise KnowledgeError(
            f"knowledge file exceeds {MAX_FILE_BYTES} bytes: {display_path(shown_path)}"
        )
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory_descriptor,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise KnowledgeError(f"not a regular file: {display_path(shown_path)}")
        if file_signature(metadata) != file_signature(expected):
            raise KnowledgeError(
                f"knowledge file changed during read: {display_path(shown_path)}"
            )
        chunks: list[bytes] = []
        remaining = MAX_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_FILE_BYTES:
            raise KnowledgeError(
                f"knowledge file exceeds {MAX_FILE_BYTES} bytes: {display_path(shown_path)}"
            )
        if file_signature(os.fstat(descriptor)) != file_signature(metadata):
            raise KnowledgeError(
                f"knowledge file changed during read: {display_path(shown_path)}"
            )
        return payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise KnowledgeError(
            f"knowledge file is not UTF-8: {display_path(shown_path)}"
        ) from exc
    finally:
        os.close(descriptor)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values, text[end + 5 :]


def title_for(relative: str, frontmatter: dict[str, str], body: str) -> str:
    if frontmatter.get("title"):
        return frontmatter["title"]
    heading = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    if heading:
        return heading.group(1).strip()
    return Path(relative).stem.replace("-", " ").replace("_", " ").title()


def scan_store(root_argument: str) -> tuple[Path, Path, list[KnowledgeFile]]:
    records: list[KnowledgeFile] = []
    total_bytes = 0
    visited = 0

    with StoreAnchor(root_argument) as anchor:
        def walk_directory(
            directory_descriptor: int, relative_directory: PurePosixPath, depth: int
        ) -> None:
            nonlocal total_bytes, visited
            if depth > MAX_DEPTH:
                raise KnowledgeError(f"knowledge store exceeds depth {MAX_DEPTH}")
            anchor.verify()
            names = sorted(os.listdir(directory_descriptor), key=os.fsencode)
            for name in names:
                metadata = os.stat(
                    name, dir_fd=directory_descriptor, follow_symlinks=False
                )
                visited += 1
                if visited > MAX_FILES:
                    raise KnowledgeError(
                        f"knowledge store exceeds {MAX_FILES} filesystem entries"
                    )
                relative = relative_directory / name
                shown_path = anchor.knowledge / Path(relative.as_posix())
                if stat.S_ISLNK(metadata.st_mode):
                    raise KnowledgeError(
                        f"refusing symlink in knowledge store: {display_path(shown_path)}"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    child = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_descriptor,
                    )
                    try:
                        opened = os.fstat(child)
                        if (opened.st_dev, opened.st_ino) != (
                            metadata.st_dev,
                            metadata.st_ino,
                        ):
                            raise KnowledgeError(
                                "knowledge directory changed during inspection: "
                                f"{display_path(shown_path)}"
                            )
                        walk_directory(child, relative, depth + 1)
                        current = os.stat(
                            name,
                            dir_fd=directory_descriptor,
                            follow_symlinks=False,
                        )
                        if (
                            not stat.S_ISDIR(current.st_mode)
                            or (current.st_dev, current.st_ino)
                            != (metadata.st_dev, metadata.st_ino)
                        ):
                            raise KnowledgeError(
                                "knowledge directory changed during inspection: "
                                f"{display_path(shown_path)}"
                            )
                    finally:
                        os.close(child)
                    continue
                if Path(name).suffix.lower() != ".md":
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise KnowledgeError(
                        f"not a regular Markdown file: {display_path(shown_path)}"
                    )
                total_bytes += metadata.st_size
                if total_bytes > MAX_TOTAL_BYTES:
                    raise KnowledgeError(
                        f"knowledge store exceeds {MAX_TOTAL_BYTES} readable bytes"
                    )
                text = read_regular_file_at(
                    directory_descriptor, name, shown_path, metadata
                )
                current = os.stat(
                    name, dir_fd=directory_descriptor, follow_symlinks=False
                )
                if (
                    not stat.S_ISREG(current.st_mode)
                    or file_signature(current) != file_signature(metadata)
                ):
                    raise KnowledgeError(
                        "knowledge file changed during inspection: "
                        f"{display_path(shown_path)}"
                    )
                relative_text = relative.as_posix()
                frontmatter, body = parse_frontmatter(text)
                records.append(
                    KnowledgeFile(
                        relative_text,
                        title_for(relative_text, frontmatter, body),
                        body,
                        frontmatter,
                    )
                )

        walk_directory(anchor.knowledge_descriptor, PurePosixPath(), 0)
        anchor.verify()
        root = anchor.root
        knowledge = anchor.knowledge

    return root, knowledge, records


def tokenize(value: str) -> list[str]:
    tokens: list[str] = []
    for item in TOKEN_RE.findall(value):
        folded = item.casefold()
        candidates = [folded]
        if "-" in folded:
            candidates.extend(part for part in folded.split("-") if part)
        tokens.extend(
            token
            for token in candidates
            if len(token) > 1 and token not in STOP_WORDS
        )
    return tokens


def contains_sequence(tokens: list[str], terms: list[str]) -> bool:
    if not terms or len(terms) > len(tokens):
        return False
    width = len(terms)
    return any(
        tokens[index : index + width] == terms
        for index in range(len(tokens) - width + 1)
    )


def iter_index_entries(record: KnowledgeFile):
    index_prose = markdown_prose(record.body, mask_inline=False)
    yield from INDEX_ENTRY_RE.finditer(index_prose)


def query_report(root_argument: str, query: str, limit: int) -> dict[str, Any]:
    _, _, records = scan_store(root_argument)
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        raise KnowledgeError("query must contain at least one searchable term")
    searchable = [
        record for record in records if Path(record.relative).name != "_index.md"
    ]
    index_context: dict[str, list[str]] = {}
    for index in records:
        if Path(index.relative).name != "_index.md":
            continue
        for match in iter_index_entries(index):
            normalized = normalize_index_path(index.relative, match.group(1))
            if normalized is not None:
                index_context.setdefault(normalized, []).append(match.group(2) or "")

    token_sets: dict[str, set[str]] = {}
    token_counts: dict[str, Counter[str]] = {}
    title_tokens: dict[str, set[str]] = {}
    path_tokens: dict[str, set[str]] = {}
    ordered_tokens: dict[str, list[str]] = {}
    for record in searchable:
        title = tokenize(record.title)
        path = tokenize(PurePosixPath(record.relative).with_suffix("").as_posix())
        body_and_index = tokenize(
            record.body + "\n" + "\n".join(index_context.get(record.relative, []))
        )
        combined = title + path + body_and_index
        title_tokens[record.relative] = set(title)
        path_tokens[record.relative] = set(path)
        ordered_tokens[record.relative] = combined
        token_sets[record.relative] = set(combined)
        token_counts[record.relative] = Counter(combined)

    document_frequency = {
        term: sum(
            1
            for record in searchable
            if term in token_sets[record.relative]
        )
        for term in terms
    }
    ranked: list[tuple[int, KnowledgeFile, list[str]]] = []
    for record in searchable:
        matched = [term for term in terms if term in token_sets[record.relative]]
        if not matched:
            continue
        score = 0
        if contains_sequence(ordered_tokens[record.relative], terms):
            score += 80
        for term in matched:
            frequency = max(document_frequency[term], 1)
            rarity = max(1, (len(searchable) * 10) // frequency)
            score += rarity
            score += 30 if term in title_tokens[record.relative] else 0
            score += 20 if term in path_tokens[record.relative] else 0
            score += min(token_counts[record.relative][term], 3)
        score += 10 * (len(matched) - 1)
        ranked.append((score, record, matched))
    ranked.sort(key=lambda item: (-item[0], item[1].relative))
    matches = [
        {
            "path": f".claude/knowledge/{record.relative}",
            "title": record.title,
            "score": score,
            "matched_terms": matched,
        }
        for score, record, matched in ranked[:limit]
    ]
    return {
        "schema_version": 1,
        "command": "query",
        "query": query,
        "scope": ".claude/knowledge/",
        "files_scanned": len(records),
        "matches": matches,
    }


def normalize_index_path(index_relative: str, referenced: str) -> str | None:
    candidate = referenced.strip()
    if candidate.startswith(".claude/knowledge/"):
        candidate = candidate.removeprefix(".claude/knowledge/")
    elif candidate.startswith("knowledge/"):
        candidate = candidate.removeprefix("knowledge/")
    elif not candidate.startswith("/"):
        base = PurePosixPath(index_relative).parent
        candidate = (base / candidate).as_posix()
    else:
        return None
    normalized = PurePosixPath(candidate)
    if normalized.is_absolute() or ".." in normalized.parts:
        return None
    return normalized.as_posix()


def is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    while index > backslashes and text[index - backslashes - 1] == "\\":
        backslashes += 1
    return backslashes % 2 == 1


def mask_inline_code(line: str) -> str:
    masked = list(line)
    index = 0
    while index < len(line):
        if line[index] != "`" or is_escaped(line, index):
            index += 1
            continue
        run_end = index
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        marker = line[index:run_end]
        closing = line.find(marker, run_end)
        if closing < 0:
            index = run_end
            continue
        for offset in range(index, closing + len(marker)):
            if masked[offset] not in "\r\n":
                masked[offset] = " "
        index = closing + len(marker)
    return "".join(masked)


def markdown_prose(text: str, *, mask_inline: bool = True) -> str:
    """Mask Markdown code blocks and optionally inline code, preserving offsets."""
    output: list[str] = []
    fence_character = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)", line)
        if fence_character:
            marker = fence.group(1) if fence else ""
            remainder = fence.group(2) if fence else ""
            if (
                marker.startswith(fence_character)
                and len(marker) >= fence_length
                and not remainder.strip(" \t")
            ):
                fence_character = ""
                fence_length = 0
            output.append("\n" if line.endswith("\n") else "")
            continue
        if fence:
            marker = fence.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            output.append("\n" if line.endswith("\n") else "")
            continue
        if line.startswith("    ") or line.startswith("\t"):
            output.append("\n" if line.endswith("\n") else "")
            continue
        output.append(mask_inline_code(line) if mask_inline else line)
    return "".join(output)


def iter_markdown_link_targets(text: str):
    """Yield raw destinations from prose Markdown links with balanced parens."""
    index = 0
    while index < len(text):
        if (
            text[index] != "["
            or is_escaped(text, index)
            or (index > 0 and text[index - 1] == "!")
            or (index + 1 < len(text) and text[index + 1] == "[")
        ):
            index += 1
            continue
        bracket_depth = 1
        cursor = index + 1
        while cursor < len(text) and bracket_depth:
            if not is_escaped(text, cursor):
                if text[cursor] == "[":
                    bracket_depth += 1
                elif text[cursor] == "]":
                    bracket_depth -= 1
            cursor += 1
        if bracket_depth or cursor >= len(text) or text[cursor] != "(":
            index += 1
            continue
        destination_start = cursor + 1
        cursor = destination_start
        parenthesis_depth = 1
        in_angle = False
        while cursor < len(text) and parenthesis_depth:
            character = text[cursor]
            if not is_escaped(text, cursor):
                if character == "<" and cursor == destination_start:
                    in_angle = True
                elif character == ">" and in_angle:
                    in_angle = False
                elif not in_angle and character == "(":
                    parenthesis_depth += 1
                elif not in_angle and character == ")":
                    parenthesis_depth -= 1
            cursor += 1
        if parenthesis_depth == 0:
            yield text[destination_start : cursor - 1]
            index = cursor
        else:
            index += 1


def parse_markdown_destination(raw: str) -> str | None:
    candidate = raw.strip()
    if not candidate:
        return None
    if candidate.startswith("<"):
        closing = candidate.find(">", 1)
        if closing < 0:
            return None
        target = candidate[1:closing]
    else:
        cursor = 0
        depth = 0
        while cursor < len(candidate):
            character = candidate[cursor]
            if is_escaped(candidate, cursor):
                cursor += 1
            elif character == "(":
                depth += 1
            elif character == ")" and depth:
                depth -= 1
            elif character.isspace() and depth == 0:
                break
            cursor += 1
        target = candidate[:cursor]
    return re.sub(r"\\(.)", r"\1", target)


def resolve_markdown_target(
    root: Path, knowledge: Path, source: KnowledgeFile, raw: str
) -> tuple[str, Path | None]:
    target = parse_markdown_destination(raw)
    if target is None:
        return "skip", None
    target = urllib.parse.unquote(target).split("#", 1)[0].split("?", 1)[0]
    if not target or target.startswith("#"):
        return "skip", None
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme or target.startswith("//"):
        return "skip", None
    if target.startswith("/"):
        candidate = root / target.lstrip("/")
    else:
        candidate = knowledge / Path(source.relative).parent / target
    try:
        normalized = candidate.resolve(strict=False)
        normalized.relative_to(root)
    except (OSError, ValueError):
        return "unsafe", candidate
    return "local", normalized


def reindex_report(root_argument: str) -> dict[str, Any]:
    root, knowledge, records = scan_store(root_argument)
    by_relative = {record.relative: record for record in records}
    content = [record for record in records if Path(record.relative).name != "_index.md"]
    indexes = [record for record in records if Path(record.relative).name == "_index.md"]
    findings: list[Finding] = []

    root_index = by_relative.get("_index.md")
    if root_index is None:
        findings.append(Finding("missing-index", ".claude/knowledge/_index.md", "root index is required"))

    indexed_paths: set[str] = set()
    for index in indexes:
        for entry in iter_index_entries(index):
            raw_path = entry.group(1)
            normalized = normalize_index_path(index.relative, raw_path)
            if normalized is None:
                findings.append(Finding("unsafe-index-path", index.relative, raw_path))
                continue
            indexed_paths.add(normalized)
            if normalized not in by_relative or Path(normalized).name == "_index.md":
                findings.append(Finding("stale-index-entry", index.relative, raw_path))

    for record in content:
        if record.relative not in indexed_paths:
            findings.append(Finding("missing-index-entry", record.relative, "not referenced by any _index.md"))
        for field in REQUIRED_FRONTMATTER:
            if field not in record.frontmatter:
                findings.append(Finding("missing-frontmatter", record.relative, field))
        for field in NON_EMPTY_FRONTMATTER:
            if field in record.frontmatter and not record.frontmatter[field]:
                findings.append(Finding("invalid-frontmatter", record.relative, field))
        for field in DATE_FIELDS:
            value = record.frontmatter.get(field)
            if value:
                try:
                    valid_date = DATE_RE.fullmatch(value) is not None
                    if valid_date:
                        date.fromisoformat(value)
                except ValueError:
                    valid_date = False
                if not valid_date:
                    findings.append(
                        Finding("invalid-frontmatter", record.relative, f"{field}={value}")
                    )
        prime = record.frontmatter.get("prime")
        if prime and prime.casefold() not in {"true", "false"}:
            findings.append(Finding("invalid-frontmatter", record.relative, f"prime={prime}"))

        prose = markdown_prose(record.body)
        for wikilink in WIKILINK_RE.finditer(prose):
            if not is_escaped(prose, wikilink.start()):
                findings.append(
                    Finding(
                        "wrong-link-style",
                        record.relative,
                        wikilink.group(0),
                    )
                )
        for raw_target in iter_markdown_link_targets(prose):
            kind, target = resolve_markdown_target(root, knowledge, record, raw_target)
            if kind == "skip":
                continue
            if kind == "unsafe":
                findings.append(Finding("unsafe-link", record.relative, raw_target))
                continue
            assert target is not None
            if not target.is_file():
                findings.append(Finding("dead-reference", record.relative, raw_target))

    findings.sort(key=lambda item: (item.kind, item.path, item.detail))
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    return {
        "schema_version": 1,
        "command": "reindex-check",
        "mode": "read-only",
        "scope": ".claude/knowledge/",
        "files_processed": len(records),
        "content_files": len(content),
        "index_files": len(indexes),
        "finding_counts": counts,
        "findings": [asdict(item) for item in findings],
        "deferred_semantic_checks": [
            "cross-link proposals",
            "duplicate detection",
            "staleness analysis",
            "frontmatter writes",
            "index writes",
        ],
    }


def render_text(report: dict[str, Any]) -> str:
    if report["command"] == "query":
        lines = [
            f"Knowledge query: {report['query']}",
            f"Scope: {report['scope']} ({report['files_scanned']} Markdown files scanned)",
        ]
        matches = report["matches"]
        if not matches:
            lines.append("No matching documented knowledge found.")
        else:
            lines.append("Matches:")
            for index, match in enumerate(matches, 1):
                lines.append(
                    f"{index}. {match['path']} — {match['title']} "
                    f"(score {match['score']}; terms: {', '.join(match['matched_terms'])})"
                )
        return "\n".join(lines)

    findings = report["findings"]
    lines = [
        "Knowledge reindex check (read-only)",
        f"Scope: {report['scope']}",
        f"Processed: {report['content_files']} content files, {report['index_files']} indexes",
    ]
    if not findings:
        lines.append("Result: deterministic checks clean.")
    else:
        lines.append(f"Findings: {len(findings)}")
        for finding in findings:
            lines.append(f"- [{finding['kind']}] {finding['path']}: {finding['detail']}")
    lines.append("Deferred in this slice: " + ", ".join(report["deferred_semantic_checks"]) + ".")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    query_parser = subparsers.add_parser("query", help="rank matching knowledge files")
    query_parser.add_argument("query")
    query_parser.add_argument("--root", default=".", help="project root (default: current directory)")
    query_parser.add_argument("--limit", type=int, default=3)
    query_parser.add_argument("--format", choices=("text", "json"), default="text")

    reindex_parser = subparsers.add_parser("reindex", help="check knowledge index consistency")
    reindex_parser.add_argument("--check", action="store_true", help="required read-only mode")
    reindex_parser.add_argument("--root", default=".", help="project root (default: current directory)")
    reindex_parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "query":
            if not 1 <= args.limit <= MAX_RESULTS:
                raise KnowledgeError(f"--limit must be between 1 and {MAX_RESULTS}")
            report = query_report(args.root, args.query, args.limit)
            exit_code = 0
        else:
            if not args.check:
                raise KnowledgeError("reindex currently requires --check; write mode is not available")
            report = reindex_report(args.root)
            exit_code = 1 if report["findings"] else 0
    except (KnowledgeError, OSError) as exc:
        print(f"knowledge-system: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
