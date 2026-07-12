#!/usr/bin/env python3
"""Behavior tests for the read-only project adoption auditor."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
AUDITOR = SOURCE_ROOT / "plugins/project-adoption/shared/audit_project.py"


class ProjectAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "target"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_audit(self, output_format: str = "json") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(AUDITOR), str(self.root), "--format", output_format],
            text=True,
            capture_output=True,
            check=False,
        )

    def report(self) -> dict:
        result = self.run_audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_detects_guidance_plugins_state_and_runtime_assumptions(self) -> None:
        self.write("AGENTS.md", "Grok-Vertretung using work-system and pr-flow.\n")
        self.write("CLAUDE.md", "# Guidance\n@.claude/knowledge/_index.md\n")
        self.write(".claude/knowledge/_index.md", "# Index\n")
        self.write(".claude/rules/usage.md", "# Rules\n")
        self.write(".claude/worktrees/task/.keep", "\n")
        self.write("tasks/example.md", "# Task\n")
        self.write(
            ".claude/settings.json",
            json.dumps(
                {
                    "enabledPlugins": {
                        "example@marketplace": True,
                        "knowledge-system@marketplace": True,
                    }
                }
            ),
        )
        self.write("scripts/launch.sh", "exec claude --resume\n")
        self.write("scripts/helper.sh", 'root="${CLAUDE_PLUGIN_ROOT}"\n')
        self.write("scripts/link-project-memory.sh", "#!/bin/sh\n")

        report = self.report()
        ids = {finding["id"] for finding in report["findings"]}
        self.assertTrue(report["readOnly"])
        self.assertEqual(
            report["inventory"]["enabledPlugins"],
            ["example@marketplace", "knowledge-system@marketplace"],
        )
        self.assertEqual(
            report["inventory"]["referencedWorkflowPlugins"],
            ["knowledge-system", "pr-flow", "work-system"],
        )
        self.assertIn("agents-guidance-runtime-specific", ids)
        self.assertIn("reference-guidance-present", ids)
        self.assertIn("versioned-knowledge-present", ids)
        self.assertIn("runtime-rules-present", ids)
        self.assertIn("legacy-worktrees-present", ids)
        self.assertIn("task-backlog-present", ids)
        self.assertIn("runtime-plugins-enabled", ids)
        self.assertIn("memory-integration-present", ids)
        self.assertIn("workflow-plugin-references", ids)
        self.assertIn("hardcoded-claude-cli", ids)
        self.assertIn("hardcoded-claude-plugin-root", ids)

    def test_missing_agents_guidance_is_safe_scaffolding_candidate(self) -> None:
        report = self.report()
        finding = next(
            item for item in report["findings"] if item["id"] == "agents-guidance-missing"
        )
        self.assertEqual(finding["changeClass"], "safe-scaffolding")

    def test_common_grok_directives_are_runtime_specific(self) -> None:
        for directive in (
            "Use Grok for all tasks.\n",
            "Always run grok before editing.\n",
            "Start Grok sessions here.\n",
        ):
            with self.subTest(directive=directive):
                self.write("AGENTS.md", directive)
                ids = {finding["id"] for finding in self.report()["findings"]}
                self.assertIn("agents-guidance-runtime-specific", ids)

    def test_invalid_settings_are_reported_without_failure(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(".claude/settings.json", "{not-json\n")
        ids = {finding["id"] for finding in self.report()["findings"]}
        self.assertIn("runtime-settings-unreadable", ids)

    def test_secret_files_are_not_content_scanned(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(".env", "RUNNER=claude --resume\n")
        self.write("secrets/runner.txt", "claude --resume\n")
        self.write("private.pem", "claude --resume\n")
        ids = {finding["id"] for finding in self.report()["findings"]}
        self.assertNotIn("hardcoded-claude-cli", ids)

    def test_target_configured_fsmonitor_is_not_executed(self) -> None:
        marker = Path(self.tempdir.name) / "fsmonitor-ran"
        helper = self.root / "fsmonitor.sh"
        helper.write_text(f"#!/bin/sh\nprintf ran > '{marker}'\n", encoding="utf-8")
        helper.chmod(0o755)
        self.git("config", "core.fsmonitor", str(helper))
        result = self.run_audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_symlinked_settings_outside_target_are_not_read(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        external = Path(self.tempdir.name) / "external-settings.json"
        external.write_text(
            json.dumps({"enabledPlugins": {"private-plugin@external": True}}),
            encoding="utf-8",
        )
        settings = self.root / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.symlink_to(external)
        report = self.report()
        self.assertEqual(report["inventory"]["enabledPlugins"], [])
        ids = {finding["id"] for finding in report["findings"]}
        self.assertIn("runtime-settings-symlink", ids)

    def test_settings_below_symlinked_directory_are_not_read(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        external = Path(self.tempdir.name) / "external-runtime"
        external.mkdir()
        (external / "knowledge").mkdir()
        (external / "rules").mkdir()
        (external / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"private-plugin@external": True}}),
            encoding="utf-8",
        )
        (self.root / ".claude").symlink_to(external, target_is_directory=True)
        report = self.report()
        self.assertEqual(report["inventory"]["enabledPlugins"], [])
        self.assertNotIn("knowledge", report["inventory"])
        self.assertNotIn("rules", report["inventory"])
        ids = {finding["id"] for finding in report["findings"]}
        self.assertIn("runtime-settings-symlink", ids)
        self.assertNotIn("versioned-knowledge-present", ids)
        self.assertNotIn("runtime-rules-present", ids)

    def test_memory_detection_ignores_worktree_dependency_symlinks(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        dependency = self.root / ".claude/worktrees/task/node_modules/example"
        dependency.parent.mkdir(parents=True)
        dependency.symlink_to(self.root)
        self.write("scripts/link-project-memory.sh", "#!/bin/sh\n")
        integrations = self.report()["inventory"]["memoryIntegrationPaths"]
        self.assertEqual(integrations, ["scripts/link-project-memory.sh"])

    def test_audit_does_not_change_target_files_or_status(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("CLAUDE.md", "# Existing guidance\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        before_status = self.git("status", "--porcelain")
        before = {
            path.relative_to(self.root): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(self.root).parts
        }

        result = self.run_audit()
        self.assertEqual(result.returncode, 0, result.stderr)

        after_status = self.git("status", "--porcelain")
        after = {
            path.relative_to(self.root): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(self.root).parts
        }
        self.assertEqual(after_status, before_status)
        self.assertEqual(after, before)

    def test_text_output_states_read_only_completion(self) -> None:
        result = self.run_audit("text")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Project adoption audit (read-only)", result.stdout)
        self.assertIn("No files were changed.", result.stdout)

    def test_missing_target_returns_exit_two(self) -> None:
        missing = self.root / "missing"
        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(missing)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("AUDIT_ERROR", result.stderr)


if __name__ == "__main__":
    unittest.main()
