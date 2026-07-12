#!/usr/bin/env python3
"""Read-only drift audit for the configured Claude reference checkout."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".agents/upstream/claude-plugins.json"


def git(upstream: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(upstream), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def normalize_repository(value: str) -> str:
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", 1)
        return f"{host.lower()}/{path.removesuffix('.git').strip('/')}"
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https", "ssh"} and parsed.hostname:
        path = parsed.path.removesuffix(".git").strip("/")
        return f"{parsed.hostname.lower()}/{path}"
    return value.removesuffix(".git").strip("/").lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, help="Claude repository checkout")
    args = parser.parse_args()

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        configured = state["upstream"]
        reviewed = configured["last_reviewed_commit"]
        observed = configured["latest_observed_commit"]
        upstream = args.upstream or (ROOT / configured["local_path_hint"])
        upstream = upstream.expanduser().resolve()
        configured_repository = normalize_repository(configured["repository"])
        origin_repository = normalize_repository(git(upstream, "remote", "get-url", "origin"))
        if origin_repository != configured_repository:
            raise RuntimeError(
                f"origin mismatch: expected {configured_repository}, got {origin_repository}"
            )
        checkout_head = git(upstream, "rev-parse", "HEAD")
        main_ref = None
        current = None
        for candidate in ("refs/remotes/origin/main", "refs/heads/main"):
            try:
                current = git(upstream, "rev-parse", "--verify", candidate)
                main_ref = candidate
                break
            except RuntimeError:
                continue
        if current is None or main_ref is None:
            raise RuntimeError("neither origin/main nor local main is available")
        dirty = git(upstream, "status", "--short")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, RuntimeError) as exc:
        print(f"UPSTREAM_ERROR {exc}", file=sys.stderr)
        return 2

    print(f"upstream={upstream}")
    print(f"last_reviewed={reviewed}")
    print(f"latest_observed={observed}")
    print(f"main_ref={main_ref}")
    print(f"main_commit={current}")
    print(f"checkout_head={checkout_head}")
    print(f"dirty={'yes' if dirty else 'no'}")
    if dirty:
        print("dirty_paths:")
        print(dirty)
    stale_observation = current != observed
    if stale_observation:
        print("UPSTREAM_OBSERVATION_STALE")
    if current != reviewed:
        print("UPSTREAM_DRIFT review required")
        return 1
    if stale_observation:
        return 1
    print("UPSTREAM_CURRENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
