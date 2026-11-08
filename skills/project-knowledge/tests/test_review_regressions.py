"""Behavioral regressions found during the independent implementation review."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import PROJECT_KNOWLEDGE, run_command, run_json
from test_regressions import build_fixture, refs, write


class ReviewRegressionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'atlas'
        build_fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, command, *args):
        return run_json(PROJECT_KNOWLEDGE, command, '--project-root', self.root, *args)

    def test_policy_cannot_override_area_rules_in_any_command(self):
        policy = self.root / '.ai/project.yaml'
        original = policy.read_text()
        (self.root / 'candidate-alias.md').symlink_to('.ai/inbox/CAND-free.md')
        for target in ('.ai/inbox/CAND-free.md', './.ai/../.ai/history/OLD-auth.md',
                       'candidate-alias.md', 'tasks/T-001.md', '.ai/index/cache.json'):
            with self.subTest(target=target):
                policy.write_text(original.replace('"README.md"', json.dumps(target)))
                for command in ('query', 'overview', 'search', 'validate'):
                    args = ['--query', 'authentication'] if command in ('query', 'search') else []
                    result = run_command(PROJECT_KNOWLEDGE, command, '--project-root', self.root, *args, expect=2)
                    self.assertIn('always_load cannot contain', result.stderr)
        policy.write_text(original)
        self.assertIn('tasks/T-001.md', refs(self.call('query', '--task', 'T-001')))

    def test_duplicate_tasks_are_errors_not_last_file_wins(self):
        write(self.root, 'tasks/other.md', '---\nid: T-001\nstatus: done\n---\n# Incorrect task\n')
        for command in ('overview', 'query', 'validate'):
            result = run_command(PROJECT_KNOWLEDGE, command, '--project-root', self.root, expect=2)
            self.assertIn('Duplicate task ID T-001', result.stderr)

    def test_task_warnings_do_not_hide_valid_task(self):
        write(self.root, 'tasks/broken.md', '---\nid: |\n  broken\n---\n')
        task = self.root / 'tasks/T-001.md'
        task.write_text(task.read_text() + '- MISSING-record\n')
        result = self.call('query', '--task', 'T-001')
        self.assertIn('tasks/T-001.md', refs(result))
        self.assertTrue(any('Cannot parse task' in s for s in result['unresolved']))
        self.assertTrue(any('MISSING-record' in s for s in result['unresolved']))

    def test_search_tasks_require_explicit_id(self):
        self.assertFalse(self.call('search', '--query', 'revocation')['hits'])
        result = self.call('search', '--query', 'revocation', '--task', 'T-001')
        self.assertEqual(['tasks/T-001.md'], [h['ref'] for h in result['hits']])

    def test_semantic_pointer_returns_source_and_handles_nonfinite_score(self):
        build_fixture(self.root, semantic='yes')
        write(self.root, 'semantic.py', "import json\nprint(json.dumps([{'ref':'KNOW-auth','reason':'paraphrase','score':float('nan')}]))\n")
        result = self.call('query', '--query', 'unmatchedzzz')
        self.assertIn('docs/auth.md', refs(result, 'semantic'))
        self.assertNotIn('.ai/history/OLD-auth.md', refs(result))
        self.assertTrue(any('non-finite' in s for s in result['unresolved']))
        self.assertFalse(result['layers']['semantic'][0]['read'])

    def test_partial_match_can_be_extended_with_search(self):
        result = self.call('query', '--query', 'authentication serializable')
        self.assertNotIn('.ai/knowledge/KNOW-storage.md', refs(result))
        expanded = self.call('query', '--query', 'authentication serializable', '--search')
        self.assertIn('.ai/knowledge/KNOW-storage.md', refs(expanded, 'lexical'))


if __name__ == '__main__':
    unittest.main()
