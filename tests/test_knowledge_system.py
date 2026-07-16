from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "plugins/knowledge-system/shared/knowledge_tool.py"


class KnowledgeSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.knowledge = self.root / ".claude/knowledge"
        (self.knowledge / "architecture").mkdir(parents=True)
        self.write(
            "_index.md",
            "# Knowledge Index\n\n## Architecture\n\n"
            "- `architecture/auth.md` — Authentication flow\n",
        )
        self.write(
            "architecture/auth.md",
            """---
title: Authentication flow
createdAt: 2026-07-01
updatedAt: 2026-07-02
pluginVersion: 1.9.0
prime: true
---

# Authentication

Request authentication validates a session token before routing.
""",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.knowledge / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def test_query_ranks_matching_file_without_emitting_contents(self) -> None:
        result = self.run_tool(
            "query", "how does session authentication work", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["matches"][0]["path"], ".claude/knowledge/architecture/auth.md")
        self.assertNotIn("validates a session token", result.stdout)

    def test_query_with_no_match_reports_documentation_gap(self) -> None:
        result = self.run_tool("query", "quantum-flux-capacitor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No matching documented knowledge found", result.stdout)

    def test_query_rejects_empty_search_terms(self) -> None:
        result = self.run_tool("query", "the and wie")
        self.assertEqual(result.returncode, 2)
        self.assertIn("searchable term", result.stderr)

    def test_query_rejects_out_of_range_limit(self) -> None:
        result = self.run_tool("query", "auth", "--limit", "11")
        self.assertEqual(result.returncode, 2)
        self.assertIn("between 1 and 10", result.stderr)

    def test_missing_knowledge_store_fails_closed(self) -> None:
        empty = Path(self.temporary.name) / "empty"
        empty.mkdir()
        result = self.run_tool("query", "auth", "--root", str(empty))
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing .claude directory", result.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_knowledge_file_fails_closed(self) -> None:
        target = self.root / "outside.md"
        target.write_text("secret", encoding="utf-8")
        (self.knowledge / "leak.md").symlink_to(target)
        result = self.run_tool("query", "secret")
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing symlink", result.stderr)
        self.assertNotIn("secret", result.stdout)

    def test_invalid_utf8_fails_closed(self) -> None:
        (self.knowledge / "bad.md").write_bytes(b"# bad\n\xff")
        result = self.run_tool("query", "bad")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not UTF-8", result.stderr)

    def test_reindex_clean_fixture_is_deterministic_and_read_only(self) -> None:
        before = self.snapshot()
        first = self.run_tool("reindex", "--check", "--format", "json")
        second = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout)["findings"], [])
        self.assertEqual(before, self.snapshot())

    def test_reindex_requires_explicit_check_mode(self) -> None:
        before = self.snapshot()
        result = self.run_tool("reindex")
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --check", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_reindex_reports_missing_and_stale_index_entries(self) -> None:
        self.write(
            "_index.md",
            "# Knowledge Index\n\n- `architecture/missing.md` — gone\n",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        kinds = [finding["kind"] for finding in json.loads(result.stdout)["findings"]]
        self.assertIn("missing-index-entry", kinds)
        self.assertIn("stale-index-entry", kinds)

    def test_reindex_reports_frontmatter_and_link_findings(self) -> None:
        self.write(
            "architecture/auth.md",
            "# Authentication\n\n[missing](missing.md) [[wrong-link]]\n",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        kinds = {finding["kind"] for finding in payload["findings"]}
        self.assertEqual(
            {"dead-reference", "missing-frontmatter", "wrong-link-style"}, kinds
        )

    def test_reindex_rejects_link_escaping_project_root(self) -> None:
        auth = (self.knowledge / "architecture/auth.md").read_text(encoding="utf-8")
        self.write("architecture/auth.md", auth + "\n[outside](../../../../outside.md)\n")
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        findings = json.loads(result.stdout)["findings"]
        self.assertTrue(any(item["kind"] == "unsafe-link" for item in findings))


if __name__ == "__main__":
    unittest.main()
