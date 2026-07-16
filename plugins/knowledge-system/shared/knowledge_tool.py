#!/usr/bin/env python3
"""Deterministic, read-only query and index checks for project knowledge."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


MAX_FILES = 5_000
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_RESULTS = 10
REQUIRED_FRONTMATTER = ("title", "createdAt", "updatedAt", "pluginVersion", "prime")
DATE_FIELDS = ("createdAt", "updatedAt", "reindexedAt")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
INDEX_PATH_RE = re.compile(r"(?m)^\s*-\s+`([^`\n]+\.md)`(?:\s|$)")
TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
STOP_WORDS = {
    "a", "an", "and", "auf", "aus", "bei", "das", "dem", "den", "der",
    "die", "ein", "eine", "einer", "for", "für", "how", "ich", "im", "in",
    "ist", "mit", "of", "on", "the", "to", "und", "von", "was", "we", "what",
    "wie", "wir", "wissen", "zu",
}


class KnowledgeError(RuntimeError):
    """The knowledge store could not be inspected safely."""


@dataclass(frozen=True)
class KnowledgeFile:
    relative: str
    title: str
    text: str
    frontmatter: dict[str, str]


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    detail: str


def display_path(path: Path) -> str:
    return os.fsencode(path.as_posix()).decode("utf-8", "backslashreplace")


def ensure_plain_directory(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise KnowledgeError(f"missing {label}: {display_path(path)}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise KnowledgeError(f"refusing symlinked {label}: {display_path(path)}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise KnowledgeError(f"{label} is not a directory: {display_path(path)}")


def resolve_store(root_argument: str) -> tuple[Path, Path]:
    root_input = Path(root_argument).expanduser().absolute()
    ensure_plain_directory(root_input, "project root")
    root = root_input.resolve(strict=True)
    claude_dir = root / ".claude"
    knowledge = claude_dir / "knowledge"
    ensure_plain_directory(claude_dir, ".claude directory")
    ensure_plain_directory(knowledge, "knowledge directory")
    if knowledge.resolve(strict=True).parent != claude_dir.resolve(strict=True):
        raise KnowledgeError("knowledge directory escapes the project root")
    return root, knowledge


def read_regular_file(path: Path, size: int) -> str:
    if size > MAX_FILE_BYTES:
        raise KnowledgeError(
            f"knowledge file exceeds {MAX_FILE_BYTES} bytes: {display_path(path)}"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise KnowledgeError(f"not a regular file: {display_path(path)}")
        if metadata.st_size != size or metadata.st_size > MAX_FILE_BYTES:
            raise KnowledgeError(f"knowledge file changed during read: {display_path(path)}")
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
                f"knowledge file exceeds {MAX_FILE_BYTES} bytes: {display_path(path)}"
            )
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeError(f"knowledge file is not UTF-8: {display_path(path)}") from exc
    finally:
        os.close(descriptor)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
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
    root, knowledge = resolve_store(root_argument)
    records: list[KnowledgeFile] = []
    total_bytes = 0
    visited = 0

    for current, directory_names, file_names in os.walk(knowledge, followlinks=False):
        current_path = Path(current)
        directory_names.sort()
        file_names.sort()
        for name in list(directory_names):
            path = current_path / name
            metadata = path.lstat()
            visited += 1
            if visited > MAX_FILES:
                raise KnowledgeError(f"knowledge store exceeds {MAX_FILES} filesystem entries")
            if stat.S_ISLNK(metadata.st_mode):
                raise KnowledgeError(f"refusing symlink in knowledge store: {display_path(path)}")
            if not stat.S_ISDIR(metadata.st_mode):
                raise KnowledgeError(f"unexpected directory entry: {display_path(path)}")
        for name in file_names:
            path = current_path / name
            metadata = path.lstat()
            visited += 1
            if visited > MAX_FILES:
                raise KnowledgeError(f"knowledge store exceeds {MAX_FILES} filesystem entries")
            if stat.S_ISLNK(metadata.st_mode):
                raise KnowledgeError(f"refusing symlink in knowledge store: {display_path(path)}")
            if path.suffix.lower() != ".md":
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise KnowledgeError(f"not a regular Markdown file: {display_path(path)}")
            total_bytes += metadata.st_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise KnowledgeError(
                    f"knowledge store exceeds {MAX_TOTAL_BYTES} readable bytes"
                )
            text = read_regular_file(path, metadata.st_size)
            relative = path.relative_to(knowledge).as_posix()
            frontmatter, body = parse_frontmatter(text)
            records.append(
                KnowledgeFile(relative, title_for(relative, frontmatter, body), text, frontmatter)
            )

    if knowledge.resolve(strict=True) != root.joinpath(".claude/knowledge").resolve(strict=True):
        raise KnowledgeError("knowledge directory changed during inspection")
    return root, knowledge, records


def tokenize(value: str) -> list[str]:
    return [
        token
        for token in (item.casefold() for item in TOKEN_RE.findall(value))
        if len(token) > 1 and token not in STOP_WORDS
    ]


def query_report(root_argument: str, query: str, limit: int) -> dict[str, Any]:
    _, _, records = scan_store(root_argument)
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        raise KnowledgeError("query must contain at least one searchable term")
    query_folded = query.strip().casefold()
    ranked: list[tuple[int, KnowledgeFile, list[str]]] = []
    for record in records:
        if Path(record.relative).name == "_index.md":
            continue
        path_folded = record.relative.casefold()
        title_folded = record.title.casefold()
        text_folded = record.text.casefold()
        matched = [term for term in terms if term in text_folded or term in path_folded]
        if not matched:
            continue
        score = 0
        if query_folded and query_folded in text_folded:
            score += 40
        for term in matched:
            score += 15 if term in title_folded else 0
            score += 10 if term in path_folded else 0
            score += min(text_folded.count(term), 8)
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


def resolve_markdown_target(root: Path, knowledge: Path, source: KnowledgeFile, raw: str) -> tuple[str, Path | None]:
    target = raw.strip().split(maxsplit=1)[0].strip("<>")
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
        for raw_path in INDEX_PATH_RE.findall(index.text):
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
            if not record.frontmatter.get(field):
                findings.append(Finding("missing-frontmatter", record.relative, field))
        for field in DATE_FIELDS:
            value = record.frontmatter.get(field)
            if value and DATE_RE.fullmatch(value) is None:
                findings.append(Finding("invalid-frontmatter", record.relative, f"{field}={value}"))
        prime = record.frontmatter.get("prime")
        if prime and prime.casefold() not in {"true", "false"}:
            findings.append(Finding("invalid-frontmatter", record.relative, f"prime={prime}"))

        for wikilink in WIKILINK_RE.findall(record.text):
            findings.append(Finding("wrong-link-style", record.relative, f"[[{wikilink}]]"))
        for raw_target in MARKDOWN_LINK_RE.findall(record.text):
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
            "frontmatter backfill",
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
