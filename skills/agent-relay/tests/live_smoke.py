#!/usr/bin/env python3
"""Opt-in real CLI smoke test. Uses existing accounts and may incur model usage.

Run one case with: python3 live_smoke.py mixed --approve-test
Artifacts stay in the printed temporary directory for inspection.
"""
import json
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

CONTROLLER = Path(__file__).resolve().parents[1] / 'scripts' / 'agent_relay.py'


def call(*args):
    result = subprocess.run([sys.executable, str(CONTROLLER)] + list(args), text=True,
                            capture_output=True, timeout=650)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=('codex', 'claude', 'mixed'))
    parser.add_argument('--codex-model')
    parser.add_argument('--claude-model')
    parser.add_argument('--codex-effort')
    parser.add_argument('--claude-effort')
    parser.add_argument('--approve-test', action='store_true', required=True,
                        help='Explicitly authorize this four-turn test with the supplied settings')
    options = parser.parse_args()
    case = options.case
    workers = {'codex': ['codex:2'], 'claude': ['claude:2'], 'mixed': ['codex:1', 'claude:1']}[case]
    root = Path(tempfile.mkdtemp(prefix='relay-live-' + case + '-')).resolve()
    print(json.dumps({'case': case, 'artifacts': str(root)}), flush=True)
    workspace = root / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init', '-q', str(workspace)], check=True)
    private = root / '.workspace'
    private.mkdir()
    prompt = private / 'prompt.txt'
    prompt.write_text('Build ledger.txt in the workspace over four relay turns. During EACH turn, '
        'read the current ledger if it exists, assess its correctness, and append EXACTLY ONE line '
        'formatted ITERATION WORKER using your assigned integer iteration and worker name from '
        'the relay task context. Preserve all previous lines. Do not add a header or extra text. '
        'Do not write future iterations. Use file tools to make the actual change. '
        'Verify the file after editing. Write a short supporting note in scratch_directory/support.txt. '
        'Keep all optional working files in that hidden directory. This is a small test; do not browse or delegate.')
    criteria = private / 'criteria.txt'
    criteria.write_text('After four turns ledger.txt contains exactly four ordered lines, '
                        'each matching that turn number and its assigned worker. '
                        'On each turn only one line is appended and all earlier lines are preserved.')
    args = ['init', '--workspace', str(workspace), '--prompt-file', str(prompt),
            '--criteria-file', str(criteria), '--max-iterations', '4', '--save-dir', str(workspace / 'relay-output')]
    for worker in workers:
        args += ['--worker', worker]
    names = {'codex': ['codex-1', 'codex-2'], 'claude': ['claude-1', 'claude-2'],
             'mixed': ['codex-1', 'claude-2']}[case]
    for name in names:
        tool = name.split('-')[0]
        for field in ('model', 'effort'):
            value = getattr(options, tool + '_' + field)
            if value:
                args += ['--worker-' + field, name + '=' + value]
    created = call(*args)
    run = created['run']
    approval = private / 'confirmation.txt'
    approval.write_text('The caller explicitly authorized this isolated four-turn live smoke test '
                        'with --approve-test and these configuration arguments: ' + json.dumps(args))
    call('confirm', '--run', run, '--confirmation-file', str(approval))
    expected = []
    for n in range(4):
        state = call('step', '--run', run, '--timeout', '600')
        turn = state['turns'][-1]
        expected.append('%d %s' % (n + 1, turn['worker']))
        actual = (workspace / 'ledger.txt').read_text().splitlines()
        if actual != expected:
            raise AssertionError('Artifact mismatch: %r != %r' % (actual, expected))
        evidence = private / ('review-%d.txt' % (n + 1))
        evidence.write_text('Host read ledger.txt and verified exact ordered content: %r. '
                            'All previous entries were preserved. %s' %
                            (actual, 'Four-turn goal is met.' if n == 3 else 'Continue with one new line.'))
        state = call('review', '--run', run, '--decision', 'complete' if n == 3 else 'continue',
                     '--evidence-file', str(evidence))
        print(json.dumps({'case': case, 'iteration': n + 1, 'worker': turn['worker'],
                          'session_id': turn['session_id'], 'status': state['status']}), flush=True)
    reports = Path(run) / 'iterations'
    assert sorted(p.name for p in reports.iterdir()) == ['iteration-%d.md' % n for n in range(1, 5)]
    for n in range(1, 5):
        report = (reports / ('iteration-%d.md' % n)).read_text()
        assert '## Assessment' in report and '## Host review' in report
    assert {p.name for p in Path(run).iterdir()} == {'.workspace', 'iterations'}
    for worker in state['workers']:
        assert (Path(run) / '.workspace' / 'workers' / worker['name'] / 'support.txt').is_file()
    turns = state['turns']
    assert turns[0]['session_id'] == turns[2]['session_id']
    assert turns[1]['session_id'] == turns[3]['session_id']
    assert turns[0]['session_id'] != turns[1]['session_id']
    assert state['status'] == 'completed'
    summary = private / 'summary.md'
    summary.write_text('Passed %s relay: four real worker turns, two distinct session IDs reused '
                       'on turns three and four, handoffs parsed, artifact checked by the host '
                       'after every turn, and host accepted the final result.\n' % case)
    call('finish', '--run', run, '--summary-file', str(summary))
    assert {p.name for p in Path(run).iterdir()} == {'.workspace', 'iterations'}
    print(json.dumps({'case': case, 'passed': True, 'artifacts': str(root)}), flush=True)


if __name__ == '__main__':
    main()
