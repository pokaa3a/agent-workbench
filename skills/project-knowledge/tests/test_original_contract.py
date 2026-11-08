from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _support import PROJECT_KNOWLEDGE, run_command, run_json


class ProjectKnowledgeTest(unittest.TestCase):
    def test_validate_index_and_layered_query(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "consumer"
            (root / ".ai/knowledge").mkdir(parents=True)
            (root / ".ai/history").mkdir()
            (root / ".ai/inbox").mkdir()
            (root / "docs").mkdir()
            (root / "README.md").write_text("# Example service\n", encoding="utf-8")
            (root / ".ai/project.yaml").write_text(
                """version: 1
facets:
  domain:
    description: "Business or technical area"
    values: ["identity", "delivery"]
context:
  always_load: ["README.md", ".ai/project.yaml"]
  deterministic:
    include_history: false
    max_relationship_depth: 2
  semantic:
    enabled: false
    command: []
  budget:
    max_sources: 8
    max_chars: 20000
""",
                encoding="utf-8",
            )
            (root / "docs/authentication.md").write_text(
                "# Authentication\n\nJWT is used for API access.\n",
                encoding="utf-8",
            )
            (root / ".ai/knowledge/authentication.md").write_text(
                """---
id: KNOW-authentication
title: Authentication behavior
summary: Current JWT entry points and constraints.
facets:
  domain: [identity]
applies_to: ["src/auth/**"]
topics: [authentication, jwt]
related: []
source: ["docs/authentication.md"]
last_verified: "2026-08-25"
---

The human-facing explanation is maintained in the linked source.
""",
                encoding="utf-8",
            )

            validation = run_command(
                PROJECT_KNOWLEDGE,
                "validate",
                "--project-root",
                root,
            )
            self.assertIn("(1 records)", validation.stdout)

            index = run_command(
                PROJECT_KNOWLEDGE,
                "index",
                "--project-root",
                root,
            )
            self.assertEqual(
                (root / ".ai/index/records.json").resolve(),
                Path(index.stdout.strip()).resolve(),
            )

            query = run_json(
                PROJECT_KNOWLEDGE,
                "query",
                "--project-root",
                root,
                "--query",
                "Explain JWT authentication",
                "--facet",
                "domain=identity",
                "--path",
                "src/auth/login.py",
            )
            self.assertEqual(
                ["README.md", ".ai/project.yaml"],
                [item["ref"] for item in query["layers"]["always_loaded"]],
            )
            self.assertIn(
                ".ai/knowledge/authentication.md",
                [item["ref"] for item in query["layers"]["deterministic"]],
            )
            self.assertIn(
                "docs/authentication.md",
                [item["ref"] for item in query["layers"]["explicit_relationships"]],
            )
            self.assertLessEqual(
                query["budget"]["selected_sources"],
                query["budget"]["max_sources"],
            )


if __name__ == "__main__":
    unittest.main()
