#!/usr/bin/env python3
"""Regression tests for Phase 1 structure invariants."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ("project-adoption", "knowledge-system", "work-system", "pr-flow")


class StructureCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "repo"
        shutil.copytree(
            SOURCE_ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/check-structure.py"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def read_json(self, relative: str) -> dict:
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def write_json(self, relative: str, data: dict) -> None:
        (self.root / relative).write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def set_all_manifest_versions(self, version: str) -> None:
        for plugin in PLUGINS:
            for runtime in ("codex", "grok"):
                relative = f"plugins/{plugin}/.{runtime}-plugin/plugin.json"
                manifest = self.read_json(relative)
                manifest["version"] = version
                self.write_json(relative, manifest)

    def test_repository_baseline_passes(self) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_available_unfinished_plugin_fails(self) -> None:
        relative = ".agents/plugins/marketplace.json"
        marketplace = self.read_json(relative)
        marketplace["plugins"][0]["policy"]["installation"] = "AVAILABLE"
        self.write_json(relative, marketplace)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must use installation policy NOT_AVAILABLE", result.stderr)

    def test_duplicate_marketplace_name_fails(self) -> None:
        relative = ".agents/plugins/marketplace.json"
        marketplace = self.read_json(relative)
        marketplace["plugins"].append(dict(marketplace["plugins"][0]))
        self.write_json(relative, marketplace)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate plugin names", result.stderr)

    def test_upstream_commit_must_match_docs(self) -> None:
        relative = ".agents/upstream/claude-plugins.json"
        state = self.read_json(relative)
        state["upstream"]["last_reviewed_commit"] = "a" * 40
        self.write_json(relative, state)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing reviewed upstream commit", result.stderr)

    def test_valid_prerelease_and_build_semver_passes(self) -> None:
        self.set_all_manifest_versions("1.2.3-rc.1+build.45")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_numeric_prerelease_with_leading_zero_fails(self) -> None:
        self.set_all_manifest_versions("1.2.3-01")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version must be strict semver", result.stderr)

    def test_missing_mit_license_fails(self) -> None:
        (self.root / "LICENSE").unlink()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required file: LICENSE", result.stderr)

    def test_claude_session_command_in_native_adapter_fails(self) -> None:
        skill = self.root / "plugins/project-adoption/codex/skills/audit/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Run claude -r to continue.\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude session command", result.stderr)


if __name__ == "__main__":
    unittest.main()
