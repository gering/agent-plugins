#!/usr/bin/env python3
"""Behavior tests for the read-only project adoption auditor."""

from __future__ import annotations

import importlib.util
import errno
import json
import os
import resource
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
        report = self.report()
        ids = {finding["id"] for finding in report["findings"]}
        self.assertNotIn("hardcoded-claude-cli", ids)
        self.assertEqual(report["inventory"]["unscannedFileCount"], 0)
        self.assertEqual(report["inventory"]["policyExcludedFileCount"], 3)

    def test_git_ignored_paths_are_reported_in_coverage(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(".gitignore", "ignored/\n")
        self.write("ignored/launch.sh", "claude --resume\n")
        report = self.report()
        self.assertEqual(report["inventory"]["gitIgnoredPathCount"], 1)
        ids = {finding["id"] for finding in report["findings"]}
        self.assertNotIn("hardcoded-claude-cli", ids)

    def test_non_git_pruned_directories_are_reported_in_coverage(self) -> None:
        shutil.rmtree(self.root / ".git")
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("secrets/launch.sh", "claude --resume\n")
        report = self.report()
        self.assertEqual(report["inventory"]["prunedDirectoryCount"], 1)

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

    def test_arbitrary_git_indirection_is_rejected(self) -> None:
        private = Path(self.tempdir.name) / "private"
        subprocess.run(["git", "init", "-q", "-b", "main", str(private)], check=True)
        shutil.rmtree(self.root / ".git")
        (self.root / ".git").write_text(f"gitdir: {private / '.git'}\n", encoding="utf-8")
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not bound to the audit target", result.stderr)

    def test_real_linked_worktree_is_accepted(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        linked = Path(self.tempdir.name) / "linked"
        self.git("worktree", "add", "-q", "-b", "linked", str(linked))
        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(linked), "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["inventory"]["gitRepository"])

    def test_separate_git_directory_fails_with_clear_limit(self) -> None:
        shutil.rmtree(self.root / ".git")
        metadata = Path(self.tempdir.name) / "separate-metadata"
        result = subprocess.run(
            ["git", "init", "-q", "--separate-git-dir", str(metadata), str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("AGENTS.md", "Shared rules.\n")
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("--separate-git-dir layouts are unsupported", result.stderr)

    def test_submodule_git_indirection_is_accepted(self) -> None:
        source = Path(self.tempdir.name) / "submodule-source"
        subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
        (source / "AGENTS.md").write_text("Shared rules.\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(source), "commit", "-q", "-m", "fixture"], check=True)
        self.write("AGENTS.md", "Parent rules.\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "parent")
        result = subprocess.run(
            ["git", "-c", "protocol.file.allow=always", "-C", str(self.root),
             "submodule", "add", "-q", str(source), "module"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(self.root / "module"), "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["inventory"]["gitRepository"])

    def test_git_timeout_is_fail_closed(self) -> None:
        spec = importlib.util.spec_from_file_location("audit_project_timeout_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with module.SafeGit(self.root) as git_context:
            git_context.deadline = module.time.monotonic() - 1
            with self.assertRaises(module.AuditError):
                git_context.run("status", "--porcelain")

    def test_fifo_git_head_fails_closed_without_blocking(self) -> None:
        head = self.root / ".git/HEAD"
        head.unlink()
        os.mkfifo(head)
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Git HEAD is not a regular file", result.stderr)

    def test_fifo_git_index_fails_closed_without_blocking(self) -> None:
        index = self.root / ".git/index"
        index.unlink(missing_ok=True)
        os.mkfifo(index)
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Git index is not a regular file", result.stderr)

    def test_fifo_candidate_is_reported_without_blocking(self) -> None:
        shutil.rmtree(self.root / ".git")
        self.write("AGENTS.md", "Shared rules.\n")
        fifo = self.root / "named-pipe"
        os.mkfifo(fifo)
        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(self.root), "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        finding = next(item for item in report["findings"] if item["id"] == "scan-incomplete")
        self.assertIn("named-pipe:non-regular", finding["evidence"])

    def test_explicit_fifo_fails_closed_without_blocking(self) -> None:
        fifo = self.root / "AGENTS.md"
        os.mkfifo(fifo)
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit input is not a regular file", result.stderr)

    def test_candidate_count_is_bounded(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("one.txt", "one\n")
        self.write("two.txt", "two\n")
        spec = importlib.util.spec_from_file_location("audit_project_bound_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module, "MAX_SCAN_PATHS", 2):
            with self.assertRaises(module.AuditError):
                module.audit(self.root, module.load_signatures())

    def test_directory_swap_to_symlink_fails_closed(self) -> None:
        shutil.rmtree(self.root / ".git")
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("nested/file.txt", "safe\n")
        external = Path(self.tempdir.name) / "external-tree"
        external.mkdir()
        (external / "private.txt").write_text("private\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("audit_project_swap_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = module.open_relative_directory

        def swap_before_open(anchor, relative):
            if relative == Path("nested") and (self.root / "nested").is_dir():
                shutil.rmtree(self.root / "nested")
                (self.root / "nested").symlink_to(external, target_is_directory=True)
            return original(anchor, relative)

        with module.RootAnchor(self.root) as anchor:
            with mock.patch.object(module, "open_relative_directory", side_effect=swap_before_open):
                with self.assertRaisesRegex(module.AuditError, "changed during inspection"):
                    module.bounded_walk(
                        self.root,
                        anchor,
                        Path(),
                        module.time.monotonic() + 5,
                        "test scan",
                    )

    def test_root_replacement_is_detected_by_anchor(self) -> None:
        spec = importlib.util.spec_from_file_location("audit_project_anchor_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = self.root.with_name("target-original")
        external = Path(self.tempdir.name) / "external-root"
        external.mkdir()
        with module.RootAnchor(self.root) as anchor:
            self.root.rename(original)
            self.root.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(module.AuditError, "target changed"):
                anchor.verify()
        self.root.unlink()
        original.rename(self.root)

    def test_git_directory_replacement_is_detected(self) -> None:
        spec = importlib.util.spec_from_file_location("audit_project_git_swap_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        external = Path(self.tempdir.name) / "external-git"
        subprocess.run(["git", "init", "-q", "-b", "main", str(external)], check=True)
        original = self.root / ".git-original"
        with module.SafeGit(self.root) as git_context:
            (self.root / ".git").rename(original)
            (self.root / ".git").symlink_to(external / ".git", target_is_directory=True)
            with self.assertRaisesRegex(module.AuditError, "metadata changed"):
                git_context.run("status", "--porcelain")
        (self.root / ".git").unlink()
        original.rename(self.root / ".git")

    def test_target_git_executable_is_not_resolved_from_relative_path(self) -> None:
        marker = Path(self.tempdir.name) / "target-git-ran"
        fake_git = self.root / "git"
        fake_git.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 23\n", encoding="utf-8")
        fake_git.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f".:{environment.get('PATH', os.defpath)}"
        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(self.root), "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_deep_candidate_does_not_exhaust_file_descriptors(self) -> None:
        shutil.rmtree(self.root / ".git")
        relative = Path(*(["deep"] * 80)) / "probe.txt"
        self.write(relative.as_posix(), "safe\n")

        def lower_fd_limit() -> None:
            _, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, hard))

        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(self.root), "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
            preexec_fn=lower_fd_limit,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_total_content_budget_produces_scan_incomplete_finding(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("one.txt", "one\n")
        spec = importlib.util.spec_from_file_location("audit_project_content_bound_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module, "MAX_SCANNED_CONTENT_BYTES", 1):
            report = module.audit(self.root, module.load_signatures())
        finding = next(item for item in report["findings"] if item["id"] == "scan-incomplete")
        self.assertTrue(any(item.endswith(":scan-budget") for item in finding["evidence"]))

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

    def test_symlinked_agent_guidance_is_not_read_or_called_missing(self) -> None:
        external = Path(self.tempdir.name) / "external-agents.md"
        external.write_text("Use Grok for all tasks.\n", encoding="utf-8")
        (self.root / "AGENTS.md").symlink_to(external)
        report = self.report()
        ids = {finding["id"] for finding in report["findings"]}
        self.assertIn("agents-guidance-symlink", ids)
        self.assertNotIn("agents-guidance-missing", ids)
        self.assertNotIn("agents-guidance-runtime-specific", ids)

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
        self.assertIn("versioned-knowledge-present-ancestor-symlink", ids)
        self.assertIn("runtime-rules-present-ancestor-symlink", ids)

    def test_settings_below_regular_file_fail_closed(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(".claude", "not a directory\n")
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read explicit input .claude/settings.json", result.stderr)

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

    def test_cli_with_file_descriptor_redirection_is_detected(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("scripts/launch.sh", "claude 2>errors.log\nclaude 1>>audit.log\n")
        finding = next(
            item for item in self.report()["findings"] if item["id"] == "hardcoded-claude-cli"
        )
        self.assertEqual(
            finding["evidence"], ["scripts/launch.sh:1", "scripts/launch.sh:2"]
        )

    def test_claude_code_prose_is_not_a_cli_command(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            "docs/reference.md",
            "This project was originally used with Claude Code.\nClaude\nAsk Claude \"$question\" for advice.\n",
        )
        ids = {finding["id"] for finding in self.report()["findings"]}
        self.assertNotIn("hardcoded-claude-cli", ids)

    def test_markdown_commands_are_detected_in_fences_lists_and_code_spans(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            "docs/commands.md",
            "```sh\nclaude\n```\n- claude --resume\nRun `claude --continue` now.\n",
        )
        finding = next(
            item for item in self.report()["findings"] if item["id"] == "hardcoded-claude-cli"
        )
        self.assertEqual(
            finding["evidence"],
            ["docs/commands.md:2", "docs/commands.md:4", "docs/commands.md:5"],
        )

    def test_fence_with_trailing_text_does_not_close_code_block(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            "docs/commands.md",
            "```sh\n```not-a-closing-fence\nclaude\n```\n",
        )
        finding = next(
            item for item in self.report()["findings"] if item["id"] == "hardcoded-claude-cli"
        )
        self.assertEqual(finding["evidence"], ["docs/commands.md:3"])

    def test_unreadable_utf8_candidate_is_reported_as_scan_incomplete(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        path = self.root / "tracked.txt"
        path.write_bytes(b"\xff\xfe")
        report = self.report()
        finding = next(item for item in report["findings"] if item["id"] == "scan-incomplete")
        self.assertEqual(report["inventory"]["unscannedFileCount"], 1)
        self.assertEqual(finding["evidence"], ["tracked.txt:non-utf8"])

    def test_large_candidate_is_reported_without_aborting(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("generated.js", "x" * (256 * 1024 + 1))
        report = self.report()
        self.assertEqual(report["inventory"]["unscannedFileCount"], 1)
        finding = next(item for item in report["findings"] if item["id"] == "scan-incomplete")
        self.assertEqual(finding["evidence"], ["generated.js:oversize"])

    def test_tracked_content_below_symlinked_parent_is_not_read(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write("linked/secret.txt", "safe\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        shutil.rmtree(self.root / "linked")
        external = Path(self.tempdir.name) / "external-linked"
        external.mkdir()
        (external / "secret.txt").write_text("exec claude --resume\n", encoding="utf-8")
        (self.root / "linked").symlink_to(external, target_is_directory=True)
        report = self.report()
        ids = {finding["id"] for finding in report["findings"]}
        self.assertNotIn("hardcoded-claude-cli", ids)
        finding = next(item for item in report["findings"] if item["id"] == "scan-incomplete")
        self.assertIn("linked/secret.txt:symlink", finding["evidence"])

    def test_disabled_workflow_plugin_declarations_remain_in_inventory(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            ".claude/settings.local.json",
            json.dumps({"enabledPlugins": {"knowledge-system@market": False}}),
        )
        report = self.report()
        self.assertEqual(report["inventory"]["enabledPlugins"], [])
        self.assertEqual(
            report["inventory"]["configuredPlugins"], ["knowledge-system@market"]
        )
        self.assertEqual(
            report["inventory"]["configuredWorkflowPlugins"], ["knowledge-system"]
        )
        self.assertEqual(report["inventory"]["referencedWorkflowPlugins"], [])
        ids = {finding["id"] for finding in report["findings"]}
        self.assertIn("workflow-plugin-configuration", ids)
        self.assertNotIn("workflow-plugin-references", ids)

    def test_disabled_tracked_workflow_setting_is_not_a_content_reference(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            ".claude/settings.json",
            json.dumps({"enabledPlugins": {"knowledge-system@market": False}}),
        )
        report = self.report()
        self.assertEqual(report["inventory"]["configuredWorkflowPlugins"], ["knowledge-system"])
        self.assertEqual(report["inventory"]["referencedWorkflowPlugins"], [])

    def test_whitespace_only_plugin_identifier_is_rejected(self) -> None:
        self.write("AGENTS.md", "Shared rules.\n")
        self.write(
            ".claude/settings.json",
            json.dumps({"enabledPlugins": {"   ": True}}),
        )
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid enabled plugin identifier", result.stderr)

    def test_unsupported_platform_fails_with_explicit_requirement(self) -> None:
        spec = importlib.util.spec_from_file_location("audit_project_platform_test", AUDITOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module, "secure_io_supported", return_value=False):
            with self.assertRaisesRegex(module.AuditError, "requires POSIX"):
                module.audit(self.root, module.load_signatures())

    def test_sha256_repository_is_audited_when_supported(self) -> None:
        shutil.rmtree(self.root / ".git")
        result = subprocess.run(
            ["git", "init", "--object-format=sha256", "-q", "-b", "main", str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest("installed Git does not support SHA-256 repositories")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.write("AGENTS.md", "Shared rules.\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        report = self.report()
        self.assertTrue(report["inventory"]["gitRepository"])
        self.assertEqual(report["inventory"]["dirtyPathCount"], 0)

    def test_unicode_unborn_branch_is_audited(self) -> None:
        shutil.rmtree(self.root / ".git")
        result = subprocess.run(
            ["git", "init", "-q", "-b", "ünïcode", str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("AGENTS.md", "Shared rules.\n")
        report = self.report()
        self.assertTrue(report["inventory"]["gitRepository"])

    def test_non_utf8_git_path_is_scanned_with_escaped_evidence(self) -> None:
        raw_path = os.fsencode(self.root) + b"/bad-\xff.sh"
        try:
            descriptor = os.open(raw_path, os.O_WRONLY | os.O_CREAT, 0o600)
        except OSError as exc:
            if exc.errno in {errno.EILSEQ, errno.EPERM}:
                self.skipTest("filesystem or sandbox rejects non-UTF-8 path bytes")
            raise
        try:
            os.write(descriptor, b"claude --resume\n")
        finally:
            os.close(descriptor)
        result = self.run_audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        finding = next(
            item for item in report["findings"] if item["id"] == "hardcoded-claude-cli"
        )
        self.assertIn("bad-\\xff.sh:1", finding["evidence"])

    def test_reftable_repository_is_audited_when_supported(self) -> None:
        shutil.rmtree(self.root / ".git")
        result = subprocess.run(
            ["git", "init", "--ref-format=reftable", "-q", "-b", "main", str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest("installed Git does not support reftable repositories")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.write("AGENTS.md", "Shared rules.\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        report = self.report()
        self.assertTrue(report["inventory"]["gitRepository"])
        self.assertEqual(report["inventory"]["dirtyPathCount"], 0)

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
        self.assertIn("Coverage:", result.stdout)
        self.assertIn("unscanned candidate(s)", result.stdout)
        self.assertIn("policy-excluded candidate(s)", result.stdout)
        self.assertIn("ignored Git path(s)", result.stdout)
        self.assertIn("pruned directory path(s)", result.stdout)
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
