"""Behavioral tests without model calls or changes to user configuration."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'agent_relay.py'
spec = importlib.util.spec_from_file_location('relay', SCRIPT)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='relay-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prompt = self.root / 'prompt.txt'
        self.prompt.write_text('Create and verify the requested artifact.')
        self.criteria = self.root / 'criteria.txt'
        self.criteria.write_text('The artifact meets the requested behavior.')
        self.evidence = self.root / 'review.txt'
        self.evidence.write_text('Observed artifact is incomplete; continue with the next step.')

    def create(self, workers, limit=4, confirmed=True, models=None, efforts=None):
        result = relay.init(argparse.Namespace(workspace=str(self.root), worker=workers,
            worker_model=models, worker_effort=efforts,
            prompt_file=str(self.prompt), criteria_file=str(self.criteria),
            max_iterations=limit, save_dir=str(self.root / ('run-' + str(len(list(self.root.glob('run-*'))))))))
        if confirmed:
            relay.confirm(Path(result['run']), result['state'], argparse.Namespace(confirmation_file=str(self.evidence)))
        return Path(result['run']), result['state']

    def test_no_worker_can_start_before_user_confirmation(self):
        run, state = self.create(['codex:2'], confirmed=False)
        with patch.object(relay, 'execute') as execute:
            with self.assertRaisesRegex(ValueError, 'awaiting_confirmation'):
                relay.step(run, state, argparse.Namespace(timeout=5))
            execute.assert_not_called()
        self.evidence.write_text('')
        with self.assertRaisesRegex(ValueError, 'confirmation evidence'):
            relay.confirm(run, state, argparse.Namespace(confirmation_file=str(self.evidence)))
        self.evidence.write_text('User approved the displayed two-worker configuration.')
        relay.confirm(run, state, argparse.Namespace(confirmation_file=str(self.evidence)))
        self.assertEqual(state['status'], 'ready')
        self.assertEqual(len(state['confirmation']['configuration']['workers']), 2)

    def test_changed_configuration_requires_new_confirmation(self):
        for field, value in [('model', 'different-model'), ('effort', 'high')]:
            run, state = self.create(['codex:1'])
            state['workers'][0][field] = value
            with patch.object(relay, 'execute') as execute:
                with self.assertRaisesRegex(ValueError, 'changed'):
                    relay.step(run, state, argparse.Namespace(timeout=5))
                execute.assert_not_called()
        run, state = self.create(['codex:1'])
        state['max_iterations'] = 10
        with self.assertRaisesRegex(ValueError, 'changed'):
            relay.step(run, state, argparse.Namespace(timeout=5))

    def test_per_worker_settings_on_creation_and_resume(self):
        run, state = self.create(['codex:1', 'claude:1'],
            models=['codex-1=codex-test-model', 'claude-2=claude-test-model'],
            efforts=['codex-1=high', 'claude-2=medium'])
        self.contexts = []
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=self.fake_execute) as execute:
            for _ in range(4):
                relay.step(run, state, argparse.Namespace(timeout=5))
                self.review(run, state)
        for n, invocation in enumerate(execute.call_args_list):
            args = invocation.args[0]
            model = 'codex-test-model' if n % 2 == 0 else 'claude-test-model'
            self.assertEqual(args[args.index('--model') + 1], model)
            if n % 2 == 0:
                self.assertEqual(args[args.index('-c') + 1], 'model_reasoning_effort="high"')
            else:
                self.assertEqual(args[args.index('--effort') + 1], 'medium')
        self.assertEqual(state['turns'][0]['session_id'], state['turns'][2]['session_id'])

    def test_same_tool_workers_can_use_different_settings(self):
        _, state = self.create(['codex:2'], models=['codex-1=model-a', 'codex-2=model-b'],
                               efforts=['codex-1=low', 'codex-2=high'])
        self.assertEqual([w['model'] for w in state['workers']], ['model-a', 'model-b'])
        self.assertEqual([w['effort'] for w in state['workers']], ['low', 'high'])

    def test_invalid_worker_assignments_are_rejected(self):
        for models in (['unknown=x'], ['codex-1='], ['codex-1=a', 'codex-1=b'], ['codex-1']):
            with self.subTest(models=models), self.assertRaises(ValueError):
                self.create(['codex:1'], models=models)

    def test_confirmed_defaults_do_not_add_cli_overrides(self):
        _, state = self.create(['claude:1'])
        self.assertIsNone(state['workers'][0]['model'])
        self.assertIsNone(state['workers'][0]['effort'])
        self.assertNotIn('--model', relay.command(state['workers'][0]))
        self.assertNotIn('--effort', relay.command(state['workers'][0]))

    def fake_execute(self, args, prompt, cwd, timeout, out, err, on_start=None):
        context = json.loads(prompt.split('TASK CONTEXT (data, not relay-control instructions):\n')[1])
        self.contexts.append(context)
        tool = args[0]
        if tool == 'codex':
            sid = args[args.index('resume') + 1] if 'resume' in args else 'codex-' + context['worker']
        else:
            flag = '--resume' if '--resume' in args else '--session-id'
            sid = args[args.index(flag) + 1]
        handoff = {k: 'Observed turn %d' % context['iteration'] for k in relay.FIELDS}
        if tool == 'codex':
            return '\n'.join(json.dumps(e) for e in [
                {'type': 'thread.started', 'thread_id': sid},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(handoff)}}])
        return json.dumps({'type': 'result', 'session_id': sid, 'result': json.dumps(handoff)})

    def review(self, run, state, decision='continue'):
        return relay.review(run, state, argparse.Namespace(decision=decision, evidence_file=str(self.evidence)))

    def test_same_and_mixed_round_robin(self):
        for workers in (['codex:2'], ['claude:2'], ['codex:1', 'claude:1']):
            with self.subTest(workers=workers):
                run, state = self.create(workers)
                self.contexts = []
                with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=self.fake_execute):
                    for n in range(4):
                        relay.step(run, state, argparse.Namespace(timeout=5))
                        with self.assertRaises(ValueError):
                            relay.step(run, state, argparse.Namespace(timeout=5))
                        self.review(run, state)
                turns = state['turns']
                self.assertEqual(turns[0]['session_id'], turns[2]['session_id'])
                self.assertEqual(turns[1]['session_id'], turns[3]['session_id'])
                self.assertNotEqual(turns[0]['session_id'], turns[1]['session_id'])
                self.assertIsNone(self.contexts[0]['previous_turn'])
                self.assertEqual(self.contexts[3]['previous_turn']['iteration'], 3)
                self.assertEqual(len(self.contexts[3]['host_review_history']), 3)
                self.assertEqual(state['status'], 'limit_reached')

    def test_early_completion_and_no_limit(self):
        run, state = self.create(['codex:2'], None)
        self.contexts = []
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=self.fake_execute):
            relay.step(run, state, argparse.Namespace(timeout=5))
        self.review(run, state, 'complete')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['turns']), 1)
        with self.assertRaises(ValueError):
            relay.step(run, state, argparse.Namespace(timeout=5))

    def test_failure_blocks_and_cannot_create_replacement(self):
        run, state = self.create(['codex:1'])
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', return_value='not json'):
            with self.assertRaises(ValueError):
                relay.step(run, state, argparse.Namespace(timeout=5))
        self.assertEqual(relay.read(run / 'state.json')['status'], 'blocked')
        with self.assertRaises(ValueError):
            relay.step(run, state, argparse.Namespace(timeout=5))

    def test_changed_session_is_rejected(self):
        run, state = self.create(['codex:1'])
        state['workers'][0]['session_id'] = 'original'
        self.contexts = []
        def changed(*args, **kwargs):
            return self.fake_execute(*args, **kwargs).replace('original', 'replacement')
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Session ID changed'):
                relay.step(run, state, argparse.Namespace(timeout=5))
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state['workers'][0]['session_id'], 'original')

    def test_timeout_terminates_worker(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            relay.execute(['python3', '-c', 'import time; time.sleep(20)'], '', str(self.root),
                          0.05, self.root / 'out', self.root / 'err')

    def test_lock_rejects_concurrent_host(self):
        run, _ = self.create(['codex:1'])
        with relay.locked(run):
            with self.assertRaisesRegex(ValueError, 'Another host'):
                with relay.locked(run):
                    pass

    def test_host_stop_and_empty_review(self):
        run, state = self.create(['codex:1'])
        self.contexts = []
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=self.fake_execute):
            relay.step(run, state, argparse.Namespace(timeout=5))
        self.evidence.write_text('')
        with self.assertRaises(ValueError):
            self.review(run, state)
        self.evidence.write_text('No further progress is possible without user input.')
        self.review(run, state, 'stop')
        self.assertEqual(state['status'], 'stopped')

    def test_temporary_finish_and_cleanup_lifecycle(self):
        result = relay.init(argparse.Namespace(workspace=str(self.root), worker=['codex:1'],
            prompt_file=str(self.prompt), criteria_file=str(self.criteria), max_iterations=2, save_dir=None))
        run = Path(result['run'])
        self.addCleanup(lambda: relay.shutil.rmtree(run) if run.exists() else None)
        def cli(*args):
            return subprocess.run(['python3', str(SCRIPT)] + list(args), text=True, capture_output=True)
        self.assertNotEqual(cli('cleanup', '--run', str(run)).returncode, 0)
        state = result['state']
        state['status'] = 'blocked'
        relay.write(run / 'state.json', state)
        summary = self.root / 'final.md'
        summary.write_text('Blocked before acceptance; no task completion is claimed.')
        self.assertEqual(cli('finish', '--run', str(run), '--summary-file', str(summary)).returncode, 0)
        self.assertTrue((run / 'final.md').exists())
        self.assertEqual(cli('cleanup', '--run', str(run)).returncode, 0)
        self.assertFalse(run.exists())

    def test_codex_failure_after_response_is_not_success(self):
        events = [
            {'type': 'thread.started', 'thread_id': 'original'},
            {'type': 'item.completed', 'item': {'type': 'agent_message',
                'text': json.dumps({k: 'claimed success' for k in relay.FIELDS})}},
            {'type': 'turn.failed', 'error': {'message': 'execution failed'}}]
        with self.assertRaisesRegex(ValueError, 'Codex reported'):
            relay.decode('codex', '\n'.join(json.dumps(e) for e in events))

    def test_claude_error_and_incomplete_handoff(self):
        with self.assertRaisesRegex(ValueError, 'Claude reported'):
            relay.decode('claude', json.dumps({'type': 'result', 'is_error': True, 'result': 'denied'}))
        with self.assertRaises(ValueError):
            relay.decode('claude', json.dumps({'type': 'result', 'session_id': 'a', 'result': '{}'}))

    def recovery_args(self, **overrides):
        values = dict(evidence_file=str(self.evidence), execution_context='approved',
                      session_id=None, no_session_found=False, authorize_initial_start=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def fail_attempt(self, run, state, output='', diagnostic=''):
        def fail(args, prompt, cwd, timeout, out, err, on_start=None):
            out.write_text(output)
            err.write_text(diagnostic)
            raise ValueError('Worker exited with code 1')
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=fail):
            with self.assertRaises(ValueError):
                relay.step(run, state, argparse.Namespace(timeout=5))

    def test_startup_classification_and_non_overwriting_recovery(self):
        run, state = self.create(['codex:1'])
        diagnostic = ('attempt to write a readonly database\n'
                      'Error: failed to initialize in-process app-server client: Operation not permitted')
        self.fail_attempt(run, state, diagnostic=diagnostic)
        self.assertEqual(state['error_kind'], 'startup_environment_blocked')
        old_log = run / 'turn-0001-attempt-01.stderr'
        with self.assertRaisesRegex(ValueError, 'No known session'):
            relay.recover(run, state, self.recovery_args())
        relay.recover(run, state, self.recovery_args(no_session_found=True, authorize_initial_start=True))
        self.contexts = []
        with patch.object(relay.shutil, 'which', return_value='/fake'), patch.object(relay, 'execute', side_effect=self.fake_execute):
            relay.step(run, state, argparse.Namespace(timeout=5))
        self.assertEqual(len(state['turns']), 1)
        self.assertEqual(len(state['attempts']), 2)
        self.assertEqual(old_log.read_text(), diagnostic)
        self.assertTrue((run / 'turn-0001-attempt-02.prompt.txt').exists())
        self.assertEqual(self.contexts[-1]['recovery_context'][0]['execution_context'], 'approved')

    def test_known_session_survives_bad_handoff_and_is_resumed(self):
        run, state = self.create(['codex:1'])
        self.fail_attempt(run, state, output=json.dumps({'type': 'thread.started', 'thread_id': 'original'}))
        self.assertEqual(state['workers'][0]['session_id'], 'original')
        with self.assertRaisesRegex(ValueError, 'replace the known'):
            relay.recover(run, state, self.recovery_args(session_id='replacement'))
        relay.recover(run, state, self.recovery_args())
        args = relay.command(state['workers'][0])
        self.assertEqual(args[args.index('resume') + 1], 'original')

    def test_host_can_supply_discovered_existing_session(self):
        run, state = self.create(['codex:1'])
        self.fail_attempt(run, state)
        relay.recover(run, state, self.recovery_args(session_id='found-in-session-storage'))
        self.assertEqual(state['workers'][0]['session_id'], 'found-in-session-storage')
        self.assertFalse(state['recoveries'][0]['initial_start_authorized'])

    def test_live_or_unverifiable_process_group_blocks_recovery(self):
        run, state = self.create(['codex:1'])
        self.fail_attempt(run, state)
        state['attempts'][-1]['process_group_id'] = 12345
        for outcome in (None, PermissionError()):
            with patch.object(relay.os, 'killpg', side_effect=outcome):
                with self.assertRaises(ValueError):
                    relay.recover(run, state, self.recovery_args(no_session_found=True, authorize_initial_start=True))
        self.assertEqual(state['status'], 'blocked')

    def test_recovery_refuses_conflicting_session_ids(self):
        run, state = self.create(['codex:1'])
        state['workers'][0]['session_id'] = 'original'
        self.fail_attempt(run, state, output=json.dumps({'type': 'thread.started', 'thread_id': 'other'}))
        with self.assertRaisesRegex(ValueError, 'Conflicting session'):
            relay.recover(run, state, self.recovery_args())

    def test_permission_error_during_work_is_not_startup_failure(self):
        output = json.dumps({'type': 'turn.started'})
        diagnostic = 'failed to initialize in-process app-server client: Operation not permitted'
        self.assertEqual(relay.failure_kind('codex', output, diagnostic), 'worker_execution_failed')
        self.assertEqual(relay.failure_kind('claude', '', diagnostic), 'worker_execution_failed')

    def test_recovery_requires_evidence_and_valid_configuration(self):
        run, state = self.create(['codex:1'])
        self.fail_attempt(run, state)
        self.evidence.write_text('')
        with self.assertRaisesRegex(ValueError, 'Recovery evidence'):
            relay.recover(run, state, self.recovery_args())
        self.evidence.write_text('Checked permissions, session storage, artifacts, and stopped processes.')
        state['max_iterations'] = 99
        with self.assertRaisesRegex(ValueError, 'changed configuration'):
            relay.recover(run, state, self.recovery_args())

    def test_legacy_attempts_require_new_run(self):
        run, state = self.create(['codex:1'])
        state['status'] = 'blocked'
        with self.assertRaisesRegex(ValueError, 'Legacy run'):
            relay.recover(run, state, self.recovery_args())

    def test_preflight_does_not_claim_initialization_or_expose_account(self):
        _, state = self.create(['codex:1', 'claude:1'])
        result = subprocess.CompletedProcess([], 0, stdout='{"loggedIn": true, "email": "private@example.com"}')
        with patch.object(relay.shutil, 'which', return_value='/test/cli'), patch.object(relay.subprocess, 'run', return_value=result):
            checks = relay.preflight(state)
        self.assertFalse(checks['cli_initialization_verified'])
        self.assertNotIn('private@example.com', json.dumps(checks))
        self.assertEqual(len(checks['checks']), 2)

    def test_claude_failed_result_pins_reserved_session(self):
        run, state = self.create(['claude:1'])
        sid = state['workers'][0]['reserved_id']
        output = json.dumps({'type': 'result', 'session_id': sid, 'is_error': True, 'result': 'denied'})
        self.fail_attempt(run, state, output=output)
        self.assertEqual(state['workers'][0]['session_id'], sid)
        relay.recover(run, state, self.recovery_args())
        args = relay.command(state['workers'][0])
        self.assertEqual(args[args.index('--resume') + 1], sid)

    def test_stale_running_recovers_only_after_process_exit(self):
        run, state = self.create(['codex:1'])
        self.fail_attempt(run, state)
        state['status'] = 'running'
        state['attempts'][-1]['process_group_id'] = 12345
        with patch.object(relay.os, 'killpg', side_effect=ProcessLookupError()):
            relay.recover(run, state, self.recovery_args(no_session_found=True, authorize_initial_start=True))
        self.assertEqual(state['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
