#!/usr/bin/env python3
"""Regression tests for the read-only upstream drift audit."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class UpstreamCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        base = Path(self.tempdir.name)
        self.root = base / "agent-plugins"
        self.upstream = base / "claude-plugins"
        shutil.copytree(
            SOURCE_ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        self.upstream.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        (self.upstream / "README.md").write_text("test\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "initial")
        self.git("remote", "add", "origin", "git@github.com:gering/claude-plugins.git")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.current = self.git("rev-parse", "HEAD")
        self.update_state(self.current, self.current)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.upstream), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        return result.stdout.strip()

    def update_state(self, reviewed: str, observed: str) -> None:
        path = self.root / ".agents/upstream/claude-plugins.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["upstream"]["last_reviewed_commit"] = reviewed
        state["upstream"]["latest_observed_commit"] = observed
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def run_check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/check-upstream.py"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_matching_remote_and_main_pass(self) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UPSTREAM_CURRENT", result.stdout)

    def test_origin_mismatch_fails(self) -> None:
        self.git("remote", "set-url", "origin", "https://example.invalid/not-upstream.git")
        result = self.run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("origin mismatch", result.stderr)

    def test_stale_observation_is_nonzero(self) -> None:
        self.update_state(self.current, "a" * 40)
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("UPSTREAM_OBSERVATION_STALE", result.stdout)

    def test_origin_main_wins_over_detached_head(self) -> None:
        first = self.current
        (self.upstream / "README.md").write_text("new\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "new")
        latest = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", latest)
        self.git("checkout", "-q", "--detach", first)
        self.update_state(first, latest)
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"main_commit={latest}", result.stdout)
        self.assertIn(f"checkout_head={first}", result.stdout)


if __name__ == "__main__":
    unittest.main()
