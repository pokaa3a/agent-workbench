"""Regression checks for defects found in the relay review of the original skill."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from _support import PROJECT_KNOWLEDGE, run_command, run_json

sys.path.insert(0, str(PROJECT_KNOWLEDGE.parent))
from yaml_subset import YamlSubsetError, loads  # noqa: E402


PROJECT_YAML = """version: 1
facets:
  domain:
    description: "Technical area"
    values: ["identity", "storage"]
context:
  always_load: ["README.md", ".ai/project.yaml"]
  deterministic:
    include_history: false
    max_relationship_depth: 2
  semantic:
    enabled: {semantic}
    command: {command}
  budget:
    max_sources: {max_sources}
    max_chars: {max_chars}
"""


def write(root: Path, ref: str, text: str) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_fixture(root: Path, max_sources: int = 12, max_chars: int = 40000, semantic: str | None = None) -> None:
    command = json.dumps([sys.executable, "semantic.py"]) if semantic else "[]"
    write(root, ".ai/project.yaml", PROJECT_YAML.format(
        semantic="true" if semantic else "false", command=command,
        max_sources=max_sources, max_chars=max_chars,
    ))
    write(root, "README.md", "# Atlas\nGoal: ship reliable sign-in for the partner API.\n")
    write(root, "docs/auth.md", "# Authentication\nAccess tokens are JWTs that expire after 15 minutes.\n")
    write(root, ".ai/knowledge/KNOW-auth.yaml", """id: KNOW-auth
title: Authentication
summary: Current JWT constraints.
facets:
  domain: [identity]
applies_to: ["src/auth/**"]
topics: [authentication, jwt]
source: ["docs/auth.md"]
supersedes: [OLD-auth]
last_verified: "2026-11-01"
""")
    write(root, ".ai/knowledge/KNOW-storage.md", """---
id: KNOW-storage
title: Storage engine
summary: Database configuration.
facets:
  domain: [storage]
topics: [database]
---
Transactions use SERIALIZABLE isolation by default.
""")
    write(root, ".ai/knowledge/KNOW-grid.md", """---
id: KNOW-grid
title: Grid layout
summary: Dashboard grid component.
---
Twelve columns.
""")
    write(root, ".ai/history/OLD-auth.md", """---
id: OLD-auth
title: Cookie sessions
summary: Superseded cookie session policy.
superseded_by: [KNOW-auth]
---
Cookie sessions lasted one day.
""")
    write(root, ".ai/inbox/CAND-free.md", """---
id: CAND-free
title: Disable expiry
summary: Unreviewed idea.
---
Disable token expiry.
""")
    write(root, "tasks/T-001.md", """---
id: T-001
status: active
---
# Migrate sessions

## Progress
Token issuer complete; logout revocation pending.

## Related knowledge
- KNOW-auth
""")
    write(root, "tasks/T-000.md", "---\nid: T-000\nstatus: done\n---\n# Bootstrap\n")


def refs(result: dict, layer: str | None = None) -> list[str]:
    layers = [layer] if layer else list(result["layers"])
    return [item["ref"] for name in layers for item in result["layers"].get(name, [])]


class RegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "atlas"
        build_fixture(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def query(self, *args: str) -> dict:
        return run_json(PROJECT_KNOWLEDGE, "query", "--project-root", self.root, *args)

    def test_overview_lists_goals_open_tasks_and_catalog(self) -> None:
        overview = run_json(PROJECT_KNOWLEDGE, "overview", "--project-root", self.root)
        self.assertEqual(["README.md", ".ai/project.yaml"], [item["ref"] for item in overview["read_first"]])
        self.assertEqual(["T-001"], [task["id"] for task in overview["tasks"]["listed"]])
        self.assertEqual("Migrate sessions", overview["tasks"]["listed"][0]["title"])
        self.assertEqual(1, overview["tasks"]["closed_hidden"])
        self.assertIn("KNOW-auth", [item["id"] for item in overview["knowledge"]["listed"]])
        self.assertEqual(1, overview["knowledge"]["history_records"])
        self.assertEqual(1, overview["knowledge"]["inbox_candidates"])
        self.assertEqual({"domain": ["identity", "storage"]}, overview["facets"])

    def test_task_query_returns_task_progress_and_english_links(self) -> None:
        result = self.query("--task", "T-001")
        self.assertEqual(["tasks/T-001.md"], refs(result, "tasks"))
        self.assertIn("logout revocation pending", (self.root / "tasks/T-001.md").read_text(encoding="utf-8"))
        self.assertIn(".ai/knowledge/KNOW-auth.yaml", refs(result))
        self.assertIn("docs/auth.md", refs(result))

    def test_legacy_chinese_task_heading_still_supported(self) -> None:
        write(self.root, "tasks/T-002.md", "---\nid: T-002\nstatus: active\n---\n# Legacy\n\n## 相關知識\n- KNOW-storage\n")
        self.assertIn(".ai/knowledge/KNOW-storage.md", refs(self.query("--task", "T-002")))

    def test_history_hidden_by_default_even_through_supersedes(self) -> None:
        result = self.query("--topic", "authentication")
        self.assertNotIn(".ai/history/OLD-auth.md", refs(result))
        self.assertIn(".ai/history/OLD-auth.md", [item["ref"] for item in result["excluded"]])
        self.assertTrue(any("--include-history" in note for note in result["unresolved"]))
        with_history = self.query("--topic", "authentication", "--include-history")
        self.assertIn(".ai/history/OLD-auth.md", refs(with_history))

    def test_inbox_never_returned_via_path_alias(self) -> None:
        text = (self.root / ".ai/knowledge/KNOW-grid.md").read_text(encoding="utf-8")
        (self.root / ".ai/knowledge/KNOW-grid.md").write_text(text.replace("summary:", "related: [\"./.ai/../.ai/inbox/CAND-free.md\"]\nsummary:"), encoding="utf-8")
        result = self.query("--query", "grid layout")
        self.assertNotIn(".ai/inbox/CAND-free.md", refs(result))
        self.assertIn(".ai/inbox/CAND-free.md", [item["ref"] for item in result["excluded"]])

    def test_validate_rejects_canonical_link_to_inbox(self) -> None:
        write(self.root, ".ai/knowledge/KNOW-bad.md", "---\nid: KNOW-bad\nrelated: [CAND-free]\n---\nx\n")
        failed = run_command(PROJECT_KNOWLEDGE, "validate", "--project-root", self.root, expect=2)
        self.assertIn("inbox", failed.stderr)

    def test_semantic_results_obey_bucket_rules_and_run_only_as_fallback(self) -> None:
        build_fixture(self.root, semantic="yes")
        write(self.root, "semantic.py", "import json, pathlib, sys\npathlib.Path('semantic-called').write_text('1')\n"
              "print(json.dumps([{'ref': '.ai/inbox/CAND-free.md', 'reason': 'x'}, {'ref': 'OLD-auth', 'reason': 'y'}, {'ref': 'KNOW-storage', 'reason': 'z'}]))\n")
        self.query("--topic", "authentication")
        self.assertFalse((self.root / "semantic-called").exists(), "semantic ran although structured layers matched")
        result = self.query("--query", "zzz unmatched wording")
        self.assertTrue((self.root / "semantic-called").exists())
        self.assertEqual([".ai/knowledge/KNOW-storage.md"], refs(result, "semantic"))
        excluded = {item["ref"] for item in result["excluded"]}
        self.assertIn(".ai/inbox/CAND-free.md", excluded)
        self.assertIn(".ai/history/OLD-auth.md", excluded)

    def test_budget_counts_characters_and_reports_mandatory_overflow(self) -> None:
        write(self.root, "README.md", "# 專案\n" + "目標" * 200 + "\n")
        build_fixture_budget = PROJECT_YAML.format(semantic="false", command="[]", max_sources=1, max_chars=1000)
        write(self.root, ".ai/project.yaml", build_fixture_budget)
        result = self.query("--topic", "authentication")
        readme = result["layers"]["always_loaded"][0]
        self.assertEqual(len((self.root / "README.md").read_text(encoding="utf-8")), readme["chars"])
        self.assertEqual("characters", result["budget"]["unit"])
        self.assertTrue(any("exceed max_sources" in note for note in result["unresolved"]))
        self.assertTrue(result["budget"]["omitted"])

    def test_metadata_stub_does_not_starve_its_source(self) -> None:
        write(self.root, ".ai/project.yaml", PROJECT_YAML.format(semantic="false", command="[]", max_sources=3, max_chars=40000))
        result = self.query("--topic", "authentication")
        stub = [item for item in result["layers"]["deterministic"] if item["ref"] == ".ai/knowledge/KNOW-auth.yaml"][0]
        self.assertFalse(stub["read"])
        self.assertEqual("Current JWT constraints.", stub["summary"])
        self.assertIn("docs/auth.md", refs(result, "explicit_relationships"))
        self.assertLessEqual(result["budget"]["selected_sources"], 3)

    def test_word_boundary_and_no_match_diagnostics(self) -> None:
        result = self.query("--query", "id")
        self.assertNotIn(".ai/knowledge/KNOW-grid.md", refs(result, "deterministic"))
        self.assertTrue(any("No knowledge source matched" in note for note in result["unresolved"]))

    def test_lexical_fallback_finds_body_terms_and_cjk(self) -> None:
        result = self.query("--query", "serializable")
        self.assertIn(".ai/knowledge/KNOW-storage.md", refs(result, "lexical"))
        hit = result["layers"]["lexical"][0]
        self.assertTrue(hit["lines"] and "SERIALIZABLE" in hit["snippets"][0])
        write(self.root, ".ai/knowledge/KNOW-zh.md", "---\nid: KNOW-zh\ntitle: 部署\n---\n部署流程使用藍綠切換。\n")
        search = run_json(PROJECT_KNOWLEDGE, "search", "--project-root", self.root, "--query", "藍綠部署")
        self.assertIn(".ai/knowledge/KNOW-zh.md", [hit["ref"] for hit in search["hits"]])

    def test_query_is_read_only_and_sees_edits_immediately(self) -> None:
        self.query("--topic", "authentication")
        self.assertFalse((self.root / ".ai/index").exists())
        write(self.root, ".ai/knowledge/KNOW-new.md", "---\nid: KNOW-new\ntitle: Rate limits\ntopics: [ratelimit]\n---\n100 rps.\n")
        self.assertIn(".ai/knowledge/KNOW-new.md", refs(self.query("--topic", "ratelimit")))

    def test_last_verified_is_surfaced(self) -> None:
        result = self.query("--topic", "authentication")
        stub = [item for item in result["layers"]["deterministic"] if item["id"] == "KNOW-auth"][0]
        self.assertEqual("2026-11-01", stub["last_verified"])


class ParserTest(unittest.TestCase):
    def test_list_of_map_shorthand_is_rejected(self) -> None:
        with self.assertRaises(YamlSubsetError):
            loads("items:\n  - name: x\n")

    def test_apostrophe_in_plain_scalar_allows_trailing_comment(self) -> None:
        self.assertEqual({"note": "don't panic"}, loads("note: don't panic # comment\n"))

    def test_quoted_colon_and_hash_preserved(self) -> None:
        self.assertEqual({"a": "x: #y"}, loads('a: "x: #y"\n'))

    def test_block_scalars_and_duplicates_rejected(self) -> None:
        for text in ("a: |\n  x\n", "a: 1\na: 2\n"):
            with self.assertRaises(YamlSubsetError):
                loads(text)


if __name__ == "__main__":
    unittest.main()
