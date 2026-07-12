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
        self.assertIn("baseline commit must equal upstream state", result.stderr)

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
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_plain_claude_launch_in_native_adapter_fails(self) -> None:
        script = self.root / "plugins/work-system/grok/scripts/launch.sh"
        script.parent.mkdir(parents=True)
        script.write_text("exec claude\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_unbraced_plugin_root_in_shared_helper_fails(self) -> None:
        script = self.root / "plugins/work-system/shared/launch.sh"
        script.parent.mkdir(parents=True)
        script.write_text('cd "$CLAUDE_PLUGIN_ROOT"\n', encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude plugin root", result.stderr)

    def test_null_json_root_fails(self) -> None:
        (self.root / ".agents/upstream/claude-plugins.json").write_text(
            "null\n", encoding="utf-8"
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root must be an object", result.stderr)

    def test_invalid_utf8_json_fails_without_traceback(self) -> None:
        (self.root / ".agents/plugins/marketplace.json").write_bytes(b"\xff")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_codex_interface_fails(self) -> None:
        relative = "plugins/project-adoption/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        del manifest["interface"]
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interface must be an object", result.stderr)

    def test_unknown_codex_manifest_field_fails(self) -> None:
        relative = "plugins/project-adoption/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["unknown"] = True
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported Codex manifest field", result.stderr)

    def test_stale_parity_last_sync_fails(self) -> None:
        parity_path = self.root / "docs/parity.md"
        parity = parity_path.read_text(encoding="utf-8")
        parity = parity.replace(
            "2026-07-12 / `f443fbb24fbcc06853de666a3737fbebe3064f1f` | "
            "Native memories",
            "2026-07-11 / `deadbeefdeadbeefdeadbeefdeadbeefdeadbeef` | "
            "Native memories",
        )
        parity_path.write_text(parity, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("knowledge-system Last sync", result.stderr)

    def test_readme_status_must_match_parity(self) -> None:
        readme_path = self.root / "README.md"
        readme = readme_path.read_text(encoding="utf-8")
        readme = readme.replace(
            "| project-adoption | planned | planned |",
            "| project-adoption | partial | planned |",
        )
        readme_path.write_text(readme, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("statuses must match docs/parity.md", result.stderr)

    def test_license_text_is_checked_when_upstream_is_invalid(self) -> None:
        (self.root / ".agents/upstream/claude-plugins.json").write_text(
            "null\n", encoding="utf-8"
        )
        (self.root / "LICENSE").write_text("PROPRIETARY\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content must match the repository MIT license template", result.stderr)

    def test_allow_marker_cannot_hide_execution(self) -> None:
        script = self.root / "plugins/work-system/shared/bad.sh"
        script.parent.mkdir(parents=True)
        script.write_text(
            "Detect then exec claude  # agent-plugins: allow-claude-reference\n",
            encoding="utf-8",
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_punctuation_adjacent_claude_command_fails(self) -> None:
        script = self.root / "plugins/work-system/shared/bad.sh"
        script.parent.mkdir(parents=True)
        script.write_text("claude|tee output\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_path_qualified_claude_command_fails(self) -> None:
        script = self.root / "plugins/work-system/shared/bad.sh"
        script.parent.mkdir(parents=True)
        script.write_text('exec "/usr/local/bin/claude"\n', encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_windows_claude_executable_fails(self) -> None:
        script = self.root / "plugins/work-system/shared/bad.ps1"
        script.parent.mkdir(parents=True)
        script.write_text("claude.exe --resume\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_unicode_semver_digit_fails(self) -> None:
        self.set_all_manifest_versions("1١.2.3")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version must be strict semver", result.stderr)

    def test_empty_default_prompt_fails(self) -> None:
        relative = "plugins/project-adoption/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["interface"]["defaultPrompt"] = None
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interface.defaultPrompt must be non-empty", result.stderr)

    def test_invalid_optional_codex_path_fails(self) -> None:
        relative = "plugins/project-adoption/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["skills"] = 123
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("skills must equal", result.stderr)

    def test_missing_codex_marketplace_interface_fails(self) -> None:
        relative = ".agents/plugins/marketplace.json"
        marketplace = self.read_json(relative)
        del marketplace["interface"]
        self.write_json(relative, marketplace)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interface must be an object", result.stderr)

    def test_duplicate_readme_status_row_fails(self) -> None:
        readme_path = self.root / "README.md"
        readme = readme_path.read_text(encoding="utf-8")
        readme += "\n| project-adoption | planned | planned |\n"
        readme_path.write_text(readme, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate plugin status row", result.stderr)

    def test_readme_versions_are_associated_with_plugins(self) -> None:
        readme_path = self.root / "README.md"
        readme = readme_path.read_text(encoding="utf-8")
        readme = readme.replace("knowledge-system 1.8.2", "knowledge-system 1.6.0")
        readme = readme.replace("work-system 1.6.0", "work-system 1.8.2")
        readme_path.write_text(readme, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing tracked source version", result.stderr)

    def test_non_object_upstream_fails_without_traceback(self) -> None:
        relative = ".agents/upstream/claude-plugins.json"
        state = self.read_json(relative)
        state["upstream"] = []
        self.write_json(relative, state)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstream object is required", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_utf8_docs_fail_without_traceback(self) -> None:
        (self.root / "docs/parity.md").write_bytes(b"\xff")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid text in docs/parity.md", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_dot_plugin_helper_is_boundary_checked(self) -> None:
        script = self.root / "plugins/work-system/.codex-plugin/helpers/bad.sh"
        script.parent.mkdir(parents=True)
        script.write_text("claude --resume\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_unknown_grok_manifest_field_fails(self) -> None:
        relative = "plugins/project-adoption/.grok-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["unknown"] = True
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported Grok manifest field", result.stderr)

    def test_external_reviewer_code_is_fail_closed(self) -> None:
        script = self.root / "plugins/swarm/reviewers/anthropic/review.sh"
        script.parent.mkdir(parents=True)
        script.write_text("exit 0\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("external reviewer code is fail-closed", result.stderr)


if __name__ == "__main__":
    unittest.main()
