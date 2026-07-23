from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "plugins/knowledge-system/shared/knowledge_tool.py"
SPEC = importlib.util.spec_from_file_location("knowledge_tool_tests", TOOL)
assert SPEC is not None and SPEC.loader is not None
KNOWLEDGE_TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = KNOWLEDGE_TOOL
SPEC.loader.exec_module(KNOWLEDGE_TOOL)


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
createdFrom: "PR #1"
updatedFrom: "PR #2"
reindexedAt: 2026-07-03
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

    def test_query_uses_index_description_to_route_to_content(self) -> None:
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Sprocket gateway behavior\n",
        )
        result = self.run_tool("query", "sprocket", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["matches"][0]["path"],
            ".claude/knowledge/architecture/auth.md",
        )

    def test_query_prioritizes_unique_topic_over_generic_question_words(self) -> None:
        entries = ["architecture/auth.md", "frobnicator.md"]
        for index in range(3):
            relative = f"generic-{index}.md"
            entries.append(relative)
            self.write(
                relative,
                self.document(f"Generic {index}", "work " * 20),
            )
        self.write("frobnicator.md", self.document("Frobnicator", "frobnicator"))
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            + "".join(f"- `{entry}` — entry\n" for entry in entries),
        )
        result = self.run_tool(
            "query", "how does frobnicator work here", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["matches"][0]["path"], ".claude/knowledge/frobnicator.md")

    def test_query_uses_tokens_and_excludes_frontmatter(self) -> None:
        self.write(
            "background.md",
            self.document("Background jobs", "Ongoing background processing."),
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "- `background.md` — Background jobs\n",
        )
        for query in ("Go", "plugin version"):
            with self.subTest(query=query):
                result = self.run_tool("query", query, "--format", "json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["matches"], [])

    def test_query_excludes_block_code_but_keeps_inline_identifiers(self) -> None:
        self.write(
            "examples.md",
            self.document(
                "Examples",
                """Visible prose.
```sh
fencedneedle --help
```
    indentedneedle --help
Use `inlineneedle` when configuring the feature.
""",
            ),
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "- `examples.md` — Examples\n",
        )
        for query in ("fencedneedle", "indentedneedle"):
            with self.subTest(query=query):
                result = self.run_tool("query", query, "--format", "json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["matches"], [])
        inline = self.run_tool("query", "inlineneedle", "--format", "json")
        self.assertEqual(inline.returncode, 0, inline.stderr)
        self.assertEqual(
            json.loads(inline.stdout)["matches"][0]["path"],
            ".claude/knowledge/examples.md",
        )

    def test_query_normalizes_technical_tokens(self) -> None:
        self.write(
            "identifiers.md",
            self.document("Identifiers", "request_id is shared by C++, C#, and R."),
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "- `identifiers.md` — Technical identifiers\n",
        )
        for query in ("request id", "C++", "C#", "R"):
            with self.subTest(query=query):
                result = self.run_tool("query", query, "--format", "json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout)["matches"][0]["path"],
                    ".claude/knowledge/identifiers.md",
                )

    def test_query_normalizes_compound_terms_in_both_directions(self) -> None:
        self.write(
            "identifiers.md",
            self.document("Identifiers", "The request id is propagated."),
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "- `identifiers.md` — Technical identifiers\n",
        )
        for query in ("request_id", "request-id"):
            with self.subTest(query=query):
                result = self.run_tool("query", query, "--format", "json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout)["matches"][0]["path"],
                    ".claude/knowledge/identifiers.md",
                )

    def test_query_accepts_leading_dash_terms_after_separator(self) -> None:
        self.write(
            "flags.md",
            self.document("Command flags", "Use --dry-run or --help for previews."),
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "- `flags.md` — Command flags\n",
        )
        for query in ("--dry-run", "--help"):
            with self.subTest(query=query):
                result = self.run_tool(
                    "query", "--format", "json", "--", query
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout)["matches"][0]["path"],
                    ".claude/knowledge/flags.md",
                )

    def test_query_excludes_quoted_code_comments_and_fenced_fallback_title(
        self,
    ) -> None:
        self.write(
            "quoted.md",
            """> ```markdown
> # fencedtitleneedle
> quotedcodeneedle
> ```
<!-- hiddencommentneedle -->
Visible prose.
""",
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "- `quoted.md` — Visible prose\n",
        )
        for query in (
            "fencedtitleneedle",
            "quotedcodeneedle",
            "hiddencommentneedle",
        ):
            with self.subTest(query=query):
                result = self.run_tool("query", query, "--format", "json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["matches"], [])

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
        self.assertIn("missing knowledge directory", result.stderr)

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

    def test_crlf_frontmatter_is_valid(self) -> None:
        path = self.knowledge / "architecture/auth.md"
        path.write_bytes(path.read_text(encoding="utf-8").replace("\n", "\r\n").encode())
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_bom_and_inline_frontmatter_comments_are_valid(self) -> None:
        path = self.knowledge / "architecture/auth.md"
        content = path.read_text(encoding="utf-8")
        content = content.replace(
            "title: Authentication flow",
            'title: "Authentication flow" # display title',
        )
        content = content.replace(
            "createdAt: 2026-07-01",
            "createdAt: 2026-07-01 # initial date",
        )
        content = content.replace("prime: true", "prime: true # indexed")
        path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

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

    def test_reindex_reports_missing_provenance_metadata(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        lines = auth_path.read_text(encoding="utf-8").splitlines()
        omitted = {"createdFrom", "updatedFrom", "reindexedAt"}
        auth_path.write_text(
            "\n".join(
                line for line in lines if line.partition(":")[0] not in omitted
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        missing = {
            item["detail"]
            for item in json.loads(result.stdout)["findings"]
            if item["kind"] == "missing-frontmatter"
        }
        self.assertEqual(missing, omitted)

    def test_reindex_allows_empty_origins_but_rejects_empty_reindex_date(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        content = auth_path.read_text(encoding="utf-8")
        for field in ("createdFrom", "updatedFrom", "reindexedAt"):
            content = re.sub(rf"(?m)^{field}:.*$", f"{field}:", content)
        auth_path.write_text(content, encoding="utf-8")
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        invalid = {
            item["detail"]
            for item in json.loads(result.stdout)["findings"]
            if item["kind"] == "invalid-frontmatter"
        }
        self.assertEqual(invalid, {"reindexedAt"})

    def test_reindex_rejects_link_escaping_project_root(self) -> None:
        auth = (self.knowledge / "architecture/auth.md").read_text(encoding="utf-8")
        self.write("architecture/auth.md", auth + "\n[outside](../../../../outside.md)\n")
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        findings = json.loads(result.stdout)["findings"]
        self.assertTrue(any(item["kind"] == "unsafe-link" for item in findings))

    def test_reindex_handles_markdown_examples_spaces_and_parentheses(self) -> None:
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "file with space.md").write_text("# Space\n", encoding="utf-8")
        (docs / "guide_(v2).md").write_text("# Parentheses\n", encoding="utf-8")
        auth_path = self.knowledge / "architecture/auth.md"
        auth = auth_path.read_text(encoding="utf-8")
        auth += """
\[escaped\](missing.md)
`[inline](missing.md)`
```markdown
[fenced](missing.md)
```not-a-closing-fence
[still-fenced](missing.md)
```
    [indented](missing.md)
[space](<../../../docs/file with space.md>)
[parentheses](../../../docs/guide_(v2).md)
"""
        auth_path.write_text(auth, encoding="utf-8")
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_reindex_ignores_index_entries_in_code_blocks(self) -> None:
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n\n"
            "```markdown\n"
            "- `example-only.md` — not an index entry\n"
            "```\n\n"
            "    - `indented-example.md` — also not an index entry\n",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])
        query = self.run_tool("query", "example-only", "--format", "json")
        self.assertEqual(query.returncode, 0, query.stderr)
        self.assertEqual(json.loads(query.stdout)["matches"], [])

    def test_reindex_keeps_adjacent_descriptionless_index_entries(self) -> None:
        self.write("second.md", self.document("Second", "Second body."))
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md`\n"
            "- `second.md`\n",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_reindex_accepts_uppercase_suffix_and_trailing_index_whitespace(
        self,
    ) -> None:
        source = self.knowledge / "architecture/auth.md"
        target = source.with_name("AUTH.MD")
        source.rename(target)
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/AUTH.MD`  \n",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_reindex_checks_links_in_list_continuations(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8")
            + "\n- Related:\n    [nested](missing.md)\n",
            encoding="utf-8",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(
            any(
                finding["kind"] == "dead-reference"
                and finding["detail"] == "missing.md"
                for finding in json.loads(result.stdout)["findings"]
            )
        )

    def test_reindex_preserves_percent_encoded_filename_delimiters(self) -> None:
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "name#part.md").write_text("# Hash\n", encoding="utf-8")
        (docs / "question?part.md").write_text("# Question\n", encoding="utf-8")
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8")
            + "\n[hash](../../../docs/name%23part.md)\n"
            + "[question](../../../docs/question%3Fpart.md)\n"
            + r"[escaped hash](../../../docs/name\#part.md)" + "\n"
            + r"[escaped question](../../../docs/question\?part.md)" + "\n",
            encoding="utf-8",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_reindex_checks_reference_style_links(self) -> None:
        docs = self.root / "docs"
        docs.mkdir()
        guide = docs / "guide.md"
        guide.write_text("# Guide\n", encoding="utf-8")
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8")
            + "\nRead [the guide][guide].\n"
            + '[guide]: ../../../docs/guide.md "Guide title"\n',
            encoding="utf-8",
        )
        clean = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(clean.returncode, 0, clean.stderr)
        guide.unlink()
        broken = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(broken.returncode, 1, broken.stderr)
        self.assertTrue(
            any(
                item["kind"] == "dead-reference"
                and item["detail"] == "../../../docs/guide.md"
                for item in json.loads(broken.stdout)["findings"]
            )
        )

    def test_reindex_ignores_quoted_code_and_html_comments(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8")
            + """
> ```markdown
> [quoted fence](missing-fence.md)
> ```
>     [quoted indent](missing-indent.md)
<!-- [comment](missing-comment.md) -->
""",
            encoding="utf-8",
        )
        self.write(
            "_index.md",
            "# Knowledge Index\n\n"
            "- `architecture/auth.md` — Authentication flow\n"
            "<!--\n"
            "- `missing-comment.md` — disabled\n"
            "-->\n",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_reindex_bounds_retained_findings_but_counts_all(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8")
            + "".join(f"\n[missing {index}](missing-{index}.md)" for index in range(10)),
            encoding="utf-8",
        )
        with mock.patch.object(KNOWLEDGE_TOOL, "MAX_RETAINED_FINDINGS", 3):
            report = KNOWLEDGE_TOOL.reindex_report(str(self.root))
        self.assertEqual(report["finding_total"], 10)
        self.assertEqual(report["finding_counts"], {"dead-reference": 10})
        self.assertEqual(report["findings_retained"], 3)
        self.assertEqual(report["findings_truncated"], 7)
        self.assertEqual(len(report["findings"]), 3)

    def test_reindex_audits_body_but_not_frontmatter_links(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        content = auth_path.read_text(encoding="utf-8").replace(
            "title: Authentication flow",
            'title: "[metadata](missing.md) ![[metadata-embed]]"',
        )
        auth_path.write_text(content, encoding="utf-8")
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_reindex_reports_embedded_wikilinks(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8") + "\n![[memory-note]]\n",
            encoding="utf-8",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(
            any(
                finding["kind"] == "wrong-link-style"
                and finding["detail"] == "![[memory-note]]"
                for finding in json.loads(result.stdout)["findings"]
            )
        )

    def test_reindex_rejects_impossible_calendar_date(self) -> None:
        auth_path = self.knowledge / "architecture/auth.md"
        auth_path.write_text(
            auth_path.read_text(encoding="utf-8").replace(
                "updatedAt: 2026-07-02", "updatedAt: 2026-99-99"
            ),
            encoding="utf-8",
        )
        result = self.run_tool("reindex", "--check", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        findings = json.loads(result.stdout)["findings"]
        self.assertTrue(
            any(
                item["kind"] == "invalid-frontmatter"
                and item["detail"] == "updatedAt=2026-99-99"
                for item in findings
            )
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_directory_swap_during_scan_fails_closed(self) -> None:
        section = self.knowledge / "section"
        section.mkdir()
        original_text = self.document("Inside", "needle")
        external_text = self.document("Escape", "needle")
        self.assertEqual(len(original_text.encode()), len(external_text.encode()))
        (section / "doc.md").write_text(original_text, encoding="utf-8")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "doc.md").write_text(external_text, encoding="utf-8")

        original_reader = KNOWLEDGE_TOOL.read_regular_file_at
        swapped = False

        def swap_then_read(directory_descriptor, name, shown_path, expected):
            nonlocal swapped
            if name == "doc.md" and not swapped:
                swapped = True
                section.rename(section.with_name("section-old"))
                section.symlink_to(outside, target_is_directory=True)
            return original_reader(directory_descriptor, name, shown_path, expected)

        with mock.patch.object(
            KNOWLEDGE_TOOL, "read_regular_file_at", side_effect=swap_then_read
        ):
            with self.assertRaisesRegex(
                KNOWLEDGE_TOOL.KnowledgeError, "changed during inspection"
            ):
                KNOWLEDGE_TOOL.query_report(str(self.root), "needle", 3)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_project_root_swap_before_resolution_fails_closed(self) -> None:
        outside_temporary = tempfile.TemporaryDirectory()
        outside = Path(outside_temporary.name)
        outside_knowledge = outside / ".claude/knowledge"
        outside_knowledge.mkdir(parents=True)
        (outside_knowledge / "_index.md").write_text(
            "# Knowledge Index\n\n- `secret.md` — secret\n",
            encoding="utf-8",
        )
        (outside_knowledge / "secret.md").write_text(
            self.document("Secret", "outside secret"),
            encoding="utf-8",
        )
        original_resolve = KNOWLEDGE_TOOL.Path.resolve
        backup = self.root.with_name(self.root.name + "-checked")
        swapped = False

        def swap_then_resolve(path, *args, **kwargs):
            nonlocal swapped
            if Path(path) == self.root and not swapped:
                swapped = True
                self.root.rename(backup)
                self.root.symlink_to(outside, target_is_directory=True)
            return original_resolve(path, *args, **kwargs)

        try:
            with mock.patch.object(
                KNOWLEDGE_TOOL.Path,
                "resolve",
                autospec=True,
                side_effect=swap_then_resolve,
            ):
                with self.assertRaisesRegex(
                    KNOWLEDGE_TOOL.KnowledgeError, "project root changed"
                ):
                    KNOWLEDGE_TOOL.query_report(str(self.root), "secret", 3)
        finally:
            if self.root.is_symlink():
                self.root.unlink()
            if backup.exists():
                backup.rename(self.root)
            outside_temporary.cleanup()

    def test_file_aba_swap_during_scan_fails_closed(self) -> None:
        victim = self.knowledge / "architecture/auth.md"
        backup = self.knowledge / "architecture/auth.backup"
        outside = self.root / "outside.md"
        original = victim.read_text(encoding="utf-8")
        replacement = original.replace("Authentication flow", "Intrusion attempt!!")
        replacement = replacement.replace("session token", "secret token ")
        self.assertEqual(len(original.encode()), len(replacement.encode()))
        outside.write_text(replacement, encoding="utf-8")

        original_reader = KNOWLEDGE_TOOL.read_regular_file_at
        swapped = False

        def swap_then_read(directory_descriptor, name, shown_path, expected):
            nonlocal swapped
            if name == "auth.md" and not swapped:
                swapped = True
                victim.rename(backup)
                outside.rename(victim)
                try:
                    return original_reader(
                        directory_descriptor, name, shown_path, expected
                    )
                finally:
                    victim.rename(outside)
                    backup.rename(victim)
            return original_reader(directory_descriptor, name, shown_path, expected)

        with mock.patch.object(
            KNOWLEDGE_TOOL, "read_regular_file_at", side_effect=swap_then_read
        ):
            with self.assertRaisesRegex(
                KNOWLEDGE_TOOL.KnowledgeError, "changed during read"
            ):
                KNOWLEDGE_TOOL.query_report(str(self.root), "secret", 3)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs unavailable")
    def test_reader_opens_raced_fifo_nonblocking_and_fails_closed(self) -> None:
        source = self.knowledge / "architecture/auth.md"
        expected = source.stat()
        fifo = self.root / "replacement.fifo"
        os.mkfifo(fifo)
        real_open = os.open

        def open_fifo(name, flags, *, dir_fd=None):
            self.assertTrue(flags & os.O_NONBLOCK)
            return real_open(fifo, flags)

        with mock.patch.object(KNOWLEDGE_TOOL.os, "open", side_effect=open_fifo):
            with self.assertRaisesRegex(
                KNOWLEDGE_TOOL.KnowledgeError, "not a regular file"
            ):
                KNOWLEDGE_TOOL.read_regular_file_at(
                    -1, "auth.md", source, expected
                )

    def test_in_place_change_during_read_fails_closed(self) -> None:
        source = self.knowledge / "architecture/auth.md"
        original = source.read_text(encoding="utf-8")
        replacement = original.replace("session token", "secret token ")
        self.assertEqual(len(original.encode()), len(replacement.encode()))
        expected = source.stat()
        parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
        real_read = os.read
        changed = False

        def change_then_read(descriptor, size):
            nonlocal changed
            if not changed:
                changed = True
                source.write_text(replacement, encoding="utf-8")
            return real_read(descriptor, size)

        try:
            with mock.patch.object(
                KNOWLEDGE_TOOL.os, "read", side_effect=change_then_read
            ):
                with self.assertRaisesRegex(
                    KNOWLEDGE_TOOL.KnowledgeError, "changed during read"
                ):
                    KNOWLEDGE_TOOL.read_regular_file_at(
                        parent, "auth.md", source, expected
                    )
        finally:
            os.close(parent)
            source.write_text(original, encoding="utf-8")

    def test_directory_addition_during_scan_fails_closed(self) -> None:
        original_reader = KNOWLEDGE_TOOL.read_regular_file_at
        added = False

        def add_then_read(directory_descriptor, name, shown_path, expected):
            nonlocal added
            if name == "auth.md" and not added:
                added = True
                self.write("late.md", self.document("Late", "secret"))
            return original_reader(directory_descriptor, name, shown_path, expected)

        with mock.patch.object(
            KNOWLEDGE_TOOL, "read_regular_file_at", side_effect=add_then_read
        ):
            with self.assertRaisesRegex(
                KNOWLEDGE_TOOL.KnowledgeError, "directory changed"
            ):
                KNOWLEDGE_TOOL.query_report(str(self.root), "auth", 3)

    def test_directory_enumeration_stops_at_entry_bound(self) -> None:
        class FakeEntry:
            def __init__(self, name):
                self.name = name

        class BoundedScandir:
            def __init__(self, testcase):
                self.testcase = testcase
                self.count = 0

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def __iter__(self):
                return self

            def __next__(self):
                self.count += 1
                self.testcase.assertLessEqual(self.count, 3)
                return FakeEntry(f"entry-{self.count}")

        scanner = BoundedScandir(self)
        with (
            mock.patch.object(KNOWLEDGE_TOOL, "MAX_FILES", 2),
            mock.patch.object(
                KNOWLEDGE_TOOL, "secure_io_supported", return_value=True
            ),
            mock.patch.object(KNOWLEDGE_TOOL.os, "scandir", return_value=scanner),
        ):
            with self.assertRaisesRegex(
                KNOWLEDGE_TOOL.KnowledgeError, "exceeds 2 filesystem entries"
            ):
                KNOWLEDGE_TOOL.query_report(str(self.root), "auth", 3)
        self.assertEqual(scanner.count, 3)

    def test_malformed_link_scan_has_linear_escape_checks(self) -> None:
        text = "[x" * 2_000
        original_is_escaped = KNOWLEDGE_TOOL.is_escaped
        calls = 0

        def counted_is_escaped(value, index):
            nonlocal calls
            calls += 1
            return original_is_escaped(value, index)

        with mock.patch.object(
            KNOWLEDGE_TOOL, "is_escaped", side_effect=counted_is_escaped
        ):
            self.assertEqual(
                list(KNOWLEDGE_TOOL.iter_markdown_link_targets(text)),
                [],
            )
        self.assertLess(calls, len(text) * 3)

    def test_unsupported_secure_io_fails_closed(self) -> None:
        with mock.patch.object(
            KNOWLEDGE_TOOL, "secure_io_supported", return_value=False
        ):
            with self.assertRaisesRegex(
                KNOWLEDGE_TOOL.KnowledgeError, "requires POSIX"
            ):
                KNOWLEDGE_TOOL.query_report(str(self.root), "auth", 3)

    @staticmethod
    def document(title: str, body: str) -> str:
        return f"""---
title: {title}
createdAt: 2026-07-01
updatedAt: 2026-07-02
createdFrom: "PR #1"
updatedFrom: "PR #2"
reindexedAt: 2026-07-03
pluginVersion: 1.9.0
prime: false
---

{body}
"""


if __name__ == "__main__":
    unittest.main()
