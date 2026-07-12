#!/usr/bin/env python3
"""Behavior tests for the read-only project adoption auditor."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_invalid_settings_fail_closed(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(".claude/settings.json", "{not-json\n")
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("AUDIT_ERROR", result.stderr)

    def test_local_settings_are_inventoried_and_override_project_settings(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            ".claude/settings.json",
            json.dumps({"enabledPlugins": {"disabled@market": True, "base@market": True}}),
        )
        self.write(
            ".claude/settings.local.json",
            json.dumps({"enabledPlugins": {"disabled@market": False, "local@market": True}}),
        )
        self.write(".gitignore", ".claude/settings.local.json\n")
        report = self.report()
        self.assertEqual(report["inventory"]["enabledPlugins"], ["base@market", "local@market"])
        finding = next(item for item in report["findings"] if item["id"] == "runtime-plugins-enabled")
        self.assertEqual(
            finding["evidence"],
            [".claude/settings.json", ".claude/settings.local.json"],
        )

    def test_explicit_inputs_and_plugin_inventory_are_bounded(self) -> None:
        self.write("AGENTS.md", "x" * (256 * 1024 + 1))
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("exceeds", result.stderr)

        (self.root / "AGENTS.md").unlink()
        self.write("AGENTS.md", "Shared rules.\n")
        enabled = {f"plugin-{number}@market": True for number in range(101)}
        self.write(".claude/settings.json", json.dumps({"enabledPlugins": enabled}))
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("enabledPlugins exceeds", result.stderr)

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

    def test_target_configured_clean_filter_is_not_executed(self) -> None:
        marker = Path(self.tempdir.name) / "clean-filter-ran"
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("tracked.txt", "initial\n")
        self.write(".gitattributes", "tracked.txt filter=probe\n")
        self.git("config", "filter.probe.clean", f"sh -c 'touch {marker}; cat'")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        marker.unlink(missing_ok=True)
        self.write("tracked.txt", "changed\n")
        result = self.run_audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_target_git_includes_are_not_opened(self) -> None:
        fifo = Path(self.tempdir.name) / "blocked-config"
        os.mkfifo(fifo)
        self.git("config", "include.path", str(fifo))
        result = self.run_audit()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_target_git_config_cannot_downgrade_repository(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        (self.root / ".git/config").write_text("[broken\n", encoding="utf-8")
        report = self.report()
        self.assertTrue(report["inventory"]["gitRepository"])
        self.assertGreater(report["inventory"]["dirtyPathCount"], 0)

    def test_git_timeout_is_fail_closed(self) -> None:
        spec = importlib.util.spec_from_file_location("audit_project_timeout_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with module.SafeGit(self.root) as git_context:
            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("git", module.GIT_TIMEOUT_SECONDS),
            ):
                with self.assertRaises(module.AuditError):
                    git_context.run("status", "--porcelain")

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

    def test_ignored_memory_symlinks_are_inventoried_without_following(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(".gitignore", ".claude/memory/\n")
        external = Path(self.tempdir.name) / "external-memory"
        external.mkdir()
        link = self.root / ".claude/memory/project-link"
        link.parent.mkdir(parents=True)
        link.symlink_to(external, target_is_directory=True)
        self.assertEqual(
            self.report()["inventory"]["memoryIntegrationPaths"],
            [".claude/memory/project-link"],
        )

    def test_bare_cli_and_cross_shell_plugin_root_forms_are_detected(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            "scripts/launch.ps1",
            "claude\n& claude \"$prompt\"\n$env:CLAUDE_PLUGIN_ROOT\n%CLAUDE_PLUGIN_ROOT%\n",
        )
        ids = {finding["id"] for finding in self.report()["findings"]}
        self.assertIn("hardcoded-claude-cli", ids)
        self.assertIn("hardcoded-claude-plugin-root", ids)

    def test_claude_code_prose_is_not_a_cli_command(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("docs/reference.md", "This project was originally used with Claude Code.\n")
        ids = {finding["id"] for finding in self.report()["findings"]}
        self.assertNotIn("hardcoded-claude-cli", ids)

    def test_unreadable_utf8_candidate_fails_closed(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        path = self.root / "tracked.txt"
        path.write_bytes(b"\xff\xfe")
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot scan tracked.txt as UTF-8", result.stderr)

    def test_non_git_evidence_order_is_deterministic(self) -> None:
        shutil.rmtree(self.root / ".git")
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("z-last.sh", "claude --resume\n")
        self.write("a-first.sh", "claude --resume\n")
        reports = [self.report(), self.report()]
        evidence = [
            next(item for item in report["findings"] if item["id"] == "hardcoded-claude-cli")["evidence"]
            for report in reports
        ]
        self.assertEqual(evidence[0], ["a-first.sh:1", "z-last.sh:1"])
        self.assertEqual(evidence[0], evidence[1])

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
