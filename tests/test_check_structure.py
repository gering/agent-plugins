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

    def test_repository_check_is_independent_of_current_directory(self) -> None:
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts/check-structure.py")],
            cwd=self.tempdir.name,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_available_project_adoption_skill_requires_valid_frontmatter(self) -> None:
        skill = self.root / "plugins/project-adoption/skills/adopt-claude-project/SKILL.md"
        skill.write_text("---\n---\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontmatter", result.stderr)

    def test_codex_adoption_adapter_requires_shared_workflow(self) -> None:
        skill = self.root / "plugins/project-adoption/skills/adopt-claude-project/SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "shared/ADOPTION_AUDIT.md", "shared/missing.md"
            ),
            encoding="utf-8",
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Codex adapter must reference", result.stderr)

    def test_available_project_adoption_agent_metadata_requires_interface(self) -> None:
        agent = self.root / (
            "plugins/project-adoption/skills/adopt-claude-project/agents/openai.yaml"
        )
        agent.write_text("interface: {}\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root must be interface", result.stderr)

    def test_unfinished_work_system_cannot_be_advertised(self) -> None:
        relative = ".agents/plugins/marketplace.json"
        marketplace = self.read_json(relative)
        marketplace["plugins"][2]["policy"]["installation"] = "AVAILABLE"
        self.write_json(relative, marketplace)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work-system must use installation policy NOT_AVAILABLE", result.stderr)

    def test_project_adoption_must_be_available(self) -> None:
        relative = ".agents/plugins/marketplace.json"
        marketplace = self.read_json(relative)
        marketplace["plugins"][0]["policy"]["installation"] = "NOT_AVAILABLE"
        self.write_json(relative, marketplace)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("project-adoption must use installation policy AVAILABLE", result.stderr)

    def test_available_project_adoption_requires_runtime_parity_status(self) -> None:
        # NOTE: This test deliberately mutates the parity/README table text
        # to simulate a state where project-adoption is AVAILABLE but the
        # parity status is not yet "partial"/"parity". The strings are
        # intentionally tied to the current table content (see docs/parity.md
        # and README). If the table format or wording changes, update both
        # the mutation and the expected error message.
        parity_path = self.root / "docs/parity.md"
        original_parity = parity_path.read_text(encoding="utf-8")
        parity = original_parity.replace(
            "| project-adoption | New companion capability; no single Claude plugin source | partial | partial |",
            "| project-adoption | New companion capability; no single Claude plugin source | planned | partial |",
        )
        assert parity != original_parity, "parity replace did not change the text"
        parity_path.write_text(parity, encoding="utf-8")
        readme_path = self.root / "README.md"
        original_readme = readme_path.read_text(encoding="utf-8")
        readme = original_readme.replace(
            "| project-adoption | partial | partial |",
            "| project-adoption | planned | partial |",
        )
        assert readme != original_readme, "readme replace did not change the text"
        readme_path.write_text(readme, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs runtime evidence", result.stderr)

    def test_available_project_adoption_requires_behavior_test(self) -> None:
        (self.root / "tests/test_project_adoption.py").unlink()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("available slice is missing required file", result.stderr)

    def test_knowledge_system_requires_shared_helper(self) -> None:
        (self.root / "plugins/knowledge-system/shared/knowledge_tool.py").unlink()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("knowledge-system native slice is missing required file", result.stderr)

    def test_knowledge_skill_requires_valid_frontmatter(self) -> None:
        skill = self.root / "plugins/knowledge-system/skills/query/SKILL.md"
        skill.write_text("---\nname: query\n---\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontmatter", result.stderr)

    def test_knowledge_codex_metadata_mentions_skill(self) -> None:
        metadata = self.root / (
            "plugins/knowledge-system/skills/reindex/agents/openai.yaml"
        )
        metadata.write_text(
            metadata.read_text(encoding="utf-8").replace("$reindex", "$query"),
            encoding="utf-8",
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("default_prompt must mention $reindex", result.stderr)

    def test_knowledge_grok_adapter_requires_shared_workflow(self) -> None:
        skill = self.root / "plugins/knowledge-system/grok/skills/query/SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "shared/KNOWLEDGE_WORKFLOWS.md", "shared/missing.md"
            ),
            encoding="utf-8",
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("native adapter must reference", result.stderr)

    def test_knowledge_helper_must_keep_reindex_check_gate(self) -> None:
        helper = self.root / "plugins/knowledge-system/shared/knowledge_tool.py"
        helper.write_text(
            helper.read_text(encoding="utf-8").replace(
                "reindex currently requires --check", "reindex can write"
            ),
            encoding="utf-8",
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must fail closed without --check", result.stderr)

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

    def test_missing_gitignore_fails(self) -> None:
        (self.root / ".gitignore").unlink()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required file: .gitignore", result.stderr)

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

    def test_compatibility_knowledge_path_is_not_a_claude_executable(self) -> None:
        script = self.root / "plugins/work-system/shared/paths.py"
        script.parent.mkdir(parents=True)
        script.write_text('KNOWLEDGE = ".claude/knowledge"\n', encoding="utf-8")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

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
        original = parity_path.read_text(encoding="utf-8")
        upstream = self.read_json(".agents/upstream/claude-plugins.json")["upstream"]
        parity = original.replace(
            f"| knowledge-system | 1.9.0 at `{upstream['last_reviewed_commit']}` | partial | partial | "
            f"{upstream['last_reviewed_date']} / `{upstream['last_reviewed_commit']}` |",
            f"| knowledge-system | 1.9.0 at `{upstream['last_reviewed_commit']}` | partial | partial | "
            "2026-07-11 / `deadbeefdeadbeefdeadbeefdeadbeefdeadbeef` | "
        )
        self.assertNotEqual(parity, original)
        parity_path.write_text(parity, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("knowledge-system Last sync", result.stderr)

    def test_readme_status_must_match_parity(self) -> None:
        readme_path = self.root / "README.md"
        readme = readme_path.read_text(encoding="utf-8")
        readme = readme.replace(
            "| project-adoption | partial | partial |",
            "| project-adoption | parity | partial |",
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

    def test_mixed_case_windows_claude_executable_fails(self) -> None:
        script = self.root / "plugins/work-system/shared/bad.ps1"
        script.parent.mkdir(parents=True)
        script.write_text("CLAUDE.ExE --resume\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_mixed_case_plain_claude_executable_fails(self) -> None:
        script = self.root / "plugins/work-system/grok/scripts/launch.ps1"
        script.parent.mkdir(parents=True)
        script.write_text("CLAUDE --resume\n", encoding="utf-8")
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
        readme = readme.replace("knowledge-system 1.9.0", "knowledge-system 1.8.1")
        readme = readme.replace("work-system 1.9.0", "work-system 1.8.1")
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

    def test_grok_marketplace_non_string_name_fails_cleanly(self) -> None:
        relative = ".grok-plugin/marketplace.json"
        data = self.read_json(relative)
        # valid + bad non-string name
        data["plugins"] = [
            {"name": "project-adoption", "source": {"source": "local", "path": "./plugins/project-adoption"}},
            {"name": ["bad-list-name"]}
        ]
        self.write_json(relative, data)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("every plugin name must be a non-empty string", result.stderr)

    def test_external_reviewer_code_is_fail_closed(self) -> None:
        script = self.root / "plugins/swarm/reviewers/anthropic/review.sh"
        script.parent.mkdir(parents=True)
        script.write_text("exit 0\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("external reviewer code is fail-closed", result.stderr)

    def test_adoption_signature_schema_rejects_extra_fields(self) -> None:
        relative = "plugins/project-adoption/shared/signatures.json"
        signatures = self.read_json(relative)
        signatures["command"] = "python3"
        self.write_json(relative, signatures)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported top-level fields", result.stderr)

    def test_adoption_signature_schema_rejects_invalid_regex(self) -> None:
        relative = "plugins/project-adoption/shared/signatures.json"
        signatures = self.read_json(relative)
        signatures["content_patterns"][0]["pattern"] = "["
        self.write_json(relative, signatures)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid regex", result.stderr)

    def test_invalid_utf8_runtime_file_fails_closed(self) -> None:
        script = self.root / "plugins/work-system/lib/launch.sh"
        script.parent.mkdir(parents=True)
        script.write_bytes(b"exec claude --resume\n#\xff\n")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unreadable runtime file", result.stderr)

    def test_unlisted_plugin_directory_is_boundary_checked(self) -> None:
        script = self.root / "plugins/work-system/lib/launch.sh"
        script.parent.mkdir(parents=True)
        script.write_text("claude --resume\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_fixture_named_runtime_directory_is_boundary_checked(self) -> None:
        script = self.root / "plugins/work-system/scripts/fixtures/launch.sh"
        script.parent.mkdir(parents=True)
        script.write_text("claude --resume\n", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_root_mcp_manifest_is_boundary_checked(self) -> None:
        relative = "plugins/work-system/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["mcpServers"] = "./.mcp.json"
        self.write_json(relative, manifest)
        (self.root / "plugins/work-system/.mcp.json").write_text(
            '{"command":"claude --resume"}\n', encoding="utf-8"
        )
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden Claude executable", result.stderr)

    def test_inline_mcp_config_is_boundary_checked(self) -> None:
        relative = "plugins/work-system/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["mcpServers"] = {
            "reviewer": {"command": "claude", "args": ["--resume"]}
        }
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inline MCP config contains forbidden Claude executable", result.stderr)

    def test_declared_component_must_exist(self) -> None:
        relative = "plugins/work-system/.codex-plugin/plugin.json"
        manifest = self.read_json(relative)
        manifest["skills"] = "./skills/"
        self.write_json(relative, manifest)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("declared skills directory does not exist", result.stderr)

    def test_claude_prose_is_not_an_executable(self) -> None:
        skill = self.root / "plugins/project-adoption/codex/skills/audit/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "Audit existing Claude Code projects.\nReview Workflow (read-only).\n",
            encoding="utf-8",
        )
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_crlf_mit_license_is_accepted(self) -> None:
        license_path = self.root / "LICENSE"
        license_text = license_path.read_text(encoding="utf-8")
        license_path.write_bytes(license_text.replace("\n", "\r\n").encode("utf-8"))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_swarm_source_version_must_match_upstream_state(self) -> None:
        parity_path = self.root / "docs/parity.md"
        version = self.read_json(
            ".agents/upstream/claude-plugins.json"
        )["plugins"]["swarm"]["source_version"]
        parity = parity_path.read_text(encoding="utf-8").replace(
            f"| swarm | {version} at `", "| swarm | 0.2.0 at `"
        )
        parity_path.write_text(parity, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("swarm source version must match upstream state", result.stderr)

    def test_swarm_last_sync_must_match_upstream_state(self) -> None:
        parity_path = self.root / "docs/parity.md"
        original = parity_path.read_text(encoding="utf-8")
        state = self.read_json(".agents/upstream/claude-plugins.json")
        upstream = state["upstream"]
        version = state["plugins"]["swarm"]["source_version"]
        original_prefix = (
            f"| swarm | {version} at `{upstream['last_reviewed_commit']}` | missing | missing | "
            f"{upstream['last_reviewed_date']} / `{upstream['last_reviewed_commit']}` |"
        )
        stale_prefix = (
            f"| swarm | {version} at `{upstream['last_reviewed_commit']}` | missing | missing | "
            "2026-07-11 / `deadbeefdeadbeefdeadbeefdeadbeefdeadbeef` |"
        )
        parity = original.replace(original_prefix, stale_prefix)
        self.assertNotEqual(parity, original)
        parity_path.write_text(parity, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("swarm Last sync must be", result.stderr)

    def test_readme_must_include_swarm_source_version(self) -> None:
        readme_path = self.root / "README.md"
        version = self.read_json(
            ".agents/upstream/claude-plugins.json"
        )["plugins"]["swarm"]["source_version"]
        readme = readme_path.read_text(encoding="utf-8").replace(
            f", swarm {version}", ""
        )
        readme_path.write_text(readme, encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            f"missing tracked source version swarm {version}", result.stderr
        )


if __name__ == "__main__":
    unittest.main()
