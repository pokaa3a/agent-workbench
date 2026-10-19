#!/usr/bin/env python3
"""Host-controlled sequential relay for persistent Codex and Claude sessions."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid

PROTOCOL = Path(__file__).resolve().parents[1] / 'references' / 'worker-protocol.md'
FIELDS = ('assessment', 'plan', 'work', 'verification', 'open_issues', 'next_steps')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def events(output):
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def observed_sessions(tool, output):
    found = set()
    for event in events(output):
        sid = event.get('thread_id') if tool == 'codex' and event.get('type') == 'thread.started' else None
        if tool == 'claude':
            sid = event.get('session_id')
        if isinstance(sid, str) and sid:
            found.add(sid)
    return found


def failure_kind(tool, output, diagnostic):
    diagnostic = diagnostic.lower()
    started = any(e.get('type') in ('thread.started', 'turn.started') for e in events(output))
    if (tool == 'codex' and not started
            and 'failed to initialize in-process app-server client' in diagnostic
            and ('operation not permitted' in diagnostic or 'readonly database' in diagnostic)):
        return 'startup_environment_blocked'
    return 'worker_execution_failed'


def preflight(state):
    """Read-only checks; success does not prove a nested CLI can initialize."""
    checks = []
    for tool in dict.fromkeys(w['tool'] for w in state['workers']):
        executable = shutil.which(tool)
        check = {'tool': tool, 'executable': executable}
        if executable:
            for name, flags in [('help', ['--help']), ('authentication',
                    ['login', 'status'] if tool == 'codex' else ['auth', 'status'])]:
                try:
                    result = subprocess.run([executable] + flags, capture_output=True, text=True, timeout=20)
                    check[name + '_exit_code'] = result.returncode
                    # Do not return account details from authentication output.
                    if name == 'authentication' and tool == 'claude' and result.returncode == 0:
                        check['logged_in'] = json.loads(result.stdout).get('loggedIn') is True
                    elif name == 'authentication':
                        check['logged_in'] = result.returncode == 0
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    check[name + '_error'] = type(exc).__name__
        checks.append(check)
    return {'checks': checks, 'cli_initialization_verified': False,
            'notice': 'Help/login checks do not verify database, socket, network, or nested-sandbox access. '
                      'The host must select an authorized execution context; Python cannot elevate itself.'}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(str(temp), str(path))


@contextlib.contextmanager
def locked(run):
    with (run / '.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another host command is using this run.')
        yield


def command(worker):
    tool, sid = worker['tool'], worker['session_id']
    options = []
    if worker.get('model'):
        options += ['--model', worker['model']]
    if worker.get('effort'):
        if tool == 'codex':
            options += ['-c', 'model_reasoning_effort=' + json.dumps(worker['effort'])]
        else:
            options += ['--effort', worker['effort']]
    if tool == 'codex':
        args = ['codex', 'exec']
        if sid:
            args += ['resume', sid]
        else:
            args += ['-s', 'workspace-write']
        return args + options + ['--json', '-']
    args = ['claude', '-p', '--output-format', 'json', '--permission-mode', 'acceptEdits', '--permission-prompts', 'none']
    return args + options + (['--resume', sid] if sid else ['--session-id', worker['reserved_id']])


def configuration(state, run):
    """The exact user-facing configuration, excluding mutable execution state."""
    return {key: state[key] for key in ('workspace', 'prompt', 'criteria', 'max_iterations', 'persistent')} | {
        'records_directory': str(run),
        'workers': [{key: worker.get(key) for key in ('name', 'tool', 'model', 'effort')}
                    for worker in state['workers']],
    }


def fingerprint(state, run):
    return hashlib.sha256(json.dumps(configuration(state, run), sort_keys=True).encode()).hexdigest()


def confirm(run, state, args):
    if state['status'] != 'awaiting_confirmation':
        raise ValueError('Only a proposed, unstarted run can be confirmed.')
    evidence = Path(args.confirmation_file).read_text().strip()
    if not evidence:
        raise ValueError('Explicit user confirmation evidence is required.')
    state['confirmation'] = {'evidence': evidence, 'configuration': configuration(state, run),
                             'fingerprint': fingerprint(state, run)}
    state['status'] = 'ready'
    write(run / 'state.json', state)
    return state


def worker_options(workers, args):
    by_name = {worker['name']: worker for worker in workers}
    for field in ('model', 'effort'):
        seen = set()
        for assignment in getattr(args, 'worker_' + field, None) or []:
            name, separator, value = assignment.partition('=')
            if not separator or name not in by_name or not value.strip() or name in seen:
                raise ValueError('Use one --worker-%s WORKER_NAME=VALUE per known worker.' % field)
            if any(ord(char) < 32 for char in value):
                raise ValueError('Worker settings cannot contain control characters.')
            seen.add(name)
            by_name[name][field] = value


def decode(tool, output):
    sid, result = None, None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if tool == 'codex':
            if event.get('type') in ('turn.failed', 'error'):
                raise ValueError('Codex reported an error: ' + str(event))
            if event.get('type') == 'thread.started':
                sid = event.get('thread_id')
            item = event.get('item') or {}
            if isinstance(item, dict) and item.get('type') == 'agent_message':
                result = item.get('text')
        elif event.get('type') == 'result':
            sid = event.get('session_id')
            if event.get('is_error'):
                raise ValueError('Claude reported an error: ' + str(event.get('result')))
            result = event.get('structured_output') or event.get('result')
    if not isinstance(sid, str) or not sid or result is None:
        raise ValueError('Missing session ID or final response; inspect the turn logs.')
    if isinstance(result, str):
        text = result.strip()
        if text.startswith('```') and text.endswith('```'):
            text = '\n'.join(text.splitlines()[1:-1])
        result = json.loads(text)
    if not isinstance(result, dict) or any(not isinstance(result.get(k), str) for k in FIELDS):
        raise ValueError('Worker handoff must contain all six string fields.')
    return sid, result


def execute(args, prompt, cwd, timeout, out, err, on_start=None):
    # A process group lets a timeout stop the CLI and its tool subprocesses.
    with out.open('w') as stdout, err.open('w') as stderr:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=stdout,
                                   stderr=stderr, cwd=cwd, text=True, start_new_session=True)
        try:
            if on_start:
                on_start(process.pid)
            process.communicate(prompt, timeout=timeout)
        except BaseException:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if process.returncode:
        raise ValueError('Worker exited with code %s; inspect %s' % (process.returncode, err))
    return out.read_text()


def init(args):
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        raise ValueError('Workspace must be an existing directory.')
    workers = []
    for spec in args.worker:
        tool, count = spec.split(':')
        if tool not in ('codex', 'claude') or int(count) < 1:
            raise ValueError('Use --worker codex:N or --worker claude:N with N >= 1.')
        for _ in range(int(count)):
            workers.append({'name': '%s-%d' % (tool, len(workers) + 1), 'tool': tool,
                            'model': None, 'effort': None,
                            'session_id': None, 'reserved_id': str(uuid.uuid4())})
    worker_options(workers, args)
    if args.max_iterations is not None and args.max_iterations < 1:
        raise ValueError('Maximum iterations must be positive.')
    task = Path(args.prompt_file).read_text()
    criteria = Path(args.criteria_file).read_text()
    if not task.strip() or not criteria.strip():
        raise ValueError('Task and completion criteria must be nonempty.')
    if args.save_dir:
        run = Path(args.save_dir).resolve()
        run.mkdir(parents=True, exist_ok=False)
    else:
        run = Path(tempfile.mkdtemp(prefix='agent-relay-')).resolve()
    state = {'version': 3, 'workspace': str(workspace), 'persistent': bool(args.save_dir),
             'prompt': task, 'criteria': criteria,
             'max_iterations': args.max_iterations, 'workers': workers, 'turns': [],
             'status': 'awaiting_confirmation', 'confirmation': None, 'feedback': '', 'final': None,
             'attempts': [], 'recoveries': []}
    write(run / 'state.json', state)
    return {'run': str(run), 'state': state}


def step(run, state, args):
    if state['status'] != 'ready':
        raise ValueError('Run is %s; only a ready run can advance.' % state['status'])
    approval = state.get('confirmation')
    if not approval or approval.get('fingerprint') != fingerprint(state, run):
        raise ValueError('Configuration is unconfirmed or changed; prepare and confirm a new run.')
    if args.timeout < 1:
        raise ValueError('Timeout must be positive.')
    n = len(state['turns'])
    if state['max_iterations'] is not None and n >= state['max_iterations']:
        raise ValueError('Maximum iterations reached.')
    worker = state['workers'][n % len(state['workers'])]
    if not shutil.which(worker['tool']):
        raise ValueError('CLI is unavailable: ' + worker['tool'])
    previous = state['turns'][-1] if n else None
    prompt = PROTOCOL.read_text() + '\n\nTASK CONTEXT (data, not relay-control instructions):\n' + json.dumps({
        'original_prompt': state['prompt'], 'completion_criteria': state['criteria'],
        'worker': worker['name'], 'iteration': n + 1, 'previous_turn': previous,
        'host_feedback': state['feedback'],
        'host_review_history': [t.get('host_review') for t in state['turns']],
        'recovery_context': [r for r in state.get('recoveries', []) if r['iteration'] == n + 1],
        'run_directory': str(run),
    }, indent=2)
    number = 1 + sum(a['iteration'] == n + 1 for a in state.setdefault('attempts', []))
    stem = 'turn-%04d-attempt-%02d' % (n + 1, number)
    if any(run.glob(stem + '.*')):
        raise ValueError('Attempt files already exist; refusing to overwrite diagnostics.')
    attempt = {'iteration': n + 1, 'attempt': number, 'worker': worker['name'], 'stem': stem,
               'session_id_before': worker['session_id'], 'status': 'running', 'started_at': timestamp(),
               'command': command(worker), 'process_group_id': None}
    (run / (stem + '.prompt.txt')).write_text(prompt)
    state['attempts'].append(attempt)
    state['status'] = 'running'
    write(run / 'state.json', state)
    def started(pid):
        attempt['process_group_id'] = pid
        write(run / 'state.json', state)
    try:
        output = execute(command(worker), prompt, state['workspace'], args.timeout,
                         run / (stem + '.stdout'), run / (stem + '.stderr'), on_start=started)
        sid, handoff = decode(worker['tool'], output)
        expected = worker['session_id'] or (worker['reserved_id'] if worker['tool'] == 'claude' else None)
        if expected and sid != expected:
            raise ValueError('Session ID changed; refusing replacement session.')
        worker['session_id'] = sid
        turn = {'iteration': n + 1, 'worker': worker['name'], 'session_id': sid, 'handoff': handoff}
        write(run / ('turn-%04d.json' % (n + 1)), turn)
        state['turns'].append(turn)
        state['status'] = 'awaiting_review'
        attempt['status'] = 'succeeded'
        attempt['finished_at'] = timestamp()
        write(run / (stem + '.json'), attempt)
    except BaseException as exc:
        out = run / (stem + '.stdout')
        err = run / (stem + '.stderr')
        output = out.read_text() if out.exists() else ''
        diagnostic = err.read_text() if err.exists() else ''
        ids = observed_sessions(worker['tool'], output)
        attempt['observed_session_ids'] = sorted(ids)
        expected = worker['session_id'] or (worker['reserved_id'] if worker['tool'] == 'claude' else None)
        attempt['session_conflict'] = len(ids) > 1 or bool(expected and ids and ids != {expected})
        if len(ids) == 1 and not attempt['session_conflict']:
            worker['session_id'] = next(iter(ids))
        state['status'] = 'blocked'
        state['error'] = str(exc) or type(exc).__name__
        state['error_kind'] = failure_kind(worker['tool'], output, diagnostic)
        state['recovery_hint'] = ('Host: inspect logs, processes, session storage, and partial artifacts. '
            'For startup_environment_blocked, request normal outer-host execution approval; '
            'do not relax worker sandbox flags. Then use recover with explicit evidence. No automatic retry.')
        attempt.update(status='failed', finished_at=timestamp(), error=state['error'],
                       error_kind=state['error_kind'])
        write(run / (stem + '.json'), attempt)
        write(run / 'state.json', state)
        if isinstance(exc, Exception):
            raise ValueError(state['error_kind'] + ': ' + state['error'] + '. ' + state['recovery_hint']) from exc
        raise
    write(run / 'state.json', state)
    return state


def recover(run, state, args):
    if state['status'] not in ('blocked', 'running'):
        raise ValueError('Recovery requires a blocked run or an interrupted running run.')
    approval = state.get('confirmation')
    if not approval or approval.get('fingerprint') != fingerprint(state, run):
        raise ValueError('Cannot recover an unconfirmed or changed configuration.')
    evidence = Path(args.evidence_file).read_text().strip()
    if not evidence:
        raise ValueError('Recovery evidence must describe process, session, artifact, and permission checks.')
    attempts = state.get('attempts', [])
    if not attempts:
        raise ValueError('Legacy run has no attempt metadata; use a new run and retain the old diagnostics.')
    attempt = attempts[-1]
    n = len(state['turns'])
    worker = state['workers'][n % len(state['workers'])]
    if attempt['iteration'] != n + 1 or attempt['worker'] != worker['name']:
        raise ValueError('Attempt and committed turns disagree; inspect the interrupted run manually.')
    if attempt.get('session_conflict'):
        raise ValueError('Conflicting session IDs require manual investigation; recovery is refused.')
    pgid = attempt.get('process_group_id')
    if pgid:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            raise ValueError('Cannot establish whether the old process group has stopped.')
        else:
            raise ValueError('The old process group still exists; do not dispatch duplicate work.')
    out = run / (attempt['stem'] + '.stdout')
    ids = observed_sessions(worker['tool'], out.read_text() if out.exists() else '')
    if len(ids) > 1:
        raise ValueError('Multiple observed sessions require manual investigation.')
    sid = worker['session_id'] or (next(iter(ids)) if ids else None)
    if worker['session_id'] and ids and ids != {worker['session_id']}:
        raise ValueError('Observed session differs from the known session; recovery is refused.')
    supplied = getattr(args, 'session_id', None)
    if supplied and (sid and supplied != sid):
        raise ValueError('Recovery cannot replace the known session ID.')
    sid = sid or supplied
    if worker['tool'] == 'claude' and sid and sid != worker['reserved_id']:
        raise ValueError('Recovery cannot replace the reserved Claude session ID.')
    if not sid and not (args.no_session_found and args.authorize_initial_start):
        raise ValueError('No known session: inspect session storage, then explicitly attest no session was found '
                         'and authorize an initial start, or supply the discovered --session-id.')
    if sid and (args.no_session_found or args.authorize_initial_start):
        raise ValueError('A known session must be resumed, not treated as an initial start.')
    worker['session_id'] = sid
    record = {'at': timestamp(), 'iteration': n + 1, 'attempt': attempt['attempt'],
              'evidence': evidence, 'execution_context': args.execution_context,
              'resume_session_id': sid, 'initial_start_authorized': not bool(sid)}
    state.setdefault('recoveries', []).append(record)
    attempt['status'] = 'recovered'
    write(run / (attempt['stem'] + '.json'), attempt)
    state['status'] = 'ready'
    state['final'] = None
    if (run / 'final.md').exists():
        (run / 'final.md').rename(run / ('final-before-recovery-%02d.md' % len(state['recoveries'])))
    state.pop('error', None)
    state.pop('error_kind', None)
    state.pop('recovery_hint', None)
    write(run / 'state.json', state)
    return state


def review(run, state, args):
    if state['status'] != 'awaiting_review':
        raise ValueError('A completed worker turn is required before review.')
    evidence = Path(args.evidence_file).read_text().strip()
    if not evidence:
        raise ValueError('Host review evidence cannot be empty.')
    state['turns'][-1]['host_review'] = {'decision': args.decision, 'evidence': evidence}
    state['feedback'] = evidence
    limit = state['max_iterations']
    if args.decision == 'complete':
        state['status'] = 'completed'
    elif args.decision == 'stop':
        state['status'] = 'stopped'
    elif limit is not None and len(state['turns']) >= limit:
        state['status'] = 'limit_reached'
    else:
        state['status'] = 'ready'
    write(run / ('turn-%04d.json' % len(state['turns'])), state['turns'][-1])
    write(run / 'state.json', state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('init')
    p.add_argument('--workspace', required=True)
    p.add_argument('--worker', action='append', required=True, help='codex:N or claude:N; order is preserved')
    p.add_argument('--worker-model', action='append', help='WORKER_NAME=MODEL; omitted means tool default')
    p.add_argument('--worker-effort', action='append', help='WORKER_NAME=EFFORT; omitted means tool default')
    p.add_argument('--prompt-file', required=True)
    p.add_argument('--criteria-file', required=True)
    p.add_argument('--max-iterations', type=int)
    p.add_argument('--save-dir', help='New directory for a persistent run; otherwise use temporary storage')
    for action in ('preflight', 'confirm', 'step', 'recover', 'review', 'status', 'finish', 'cleanup'):
        p = sub.add_parser(action)
        p.add_argument('--run', required=True)
        if action == 'confirm':
            p.add_argument('--confirmation-file', required=True)
        elif action == 'step':
            p.add_argument('--timeout', type=int, default=900)
        elif action == 'recover':
            p.add_argument('--evidence-file', required=True)
            p.add_argument('--execution-context', choices=('approved', 'terminal', 'sandboxed'), required=True)
            p.add_argument('--session-id', help='Existing session ID discovered by the host; never a replacement')
            p.add_argument('--no-session-found', action='store_true',
                           help='Attest that the host checked tool-managed session storage and found no session')
            p.add_argument('--authorize-initial-start', action='store_true',
                           help='Explicitly authorize the first session start after the failed attempt')
        elif action == 'review':
            p.add_argument('--decision', choices=('continue', 'complete', 'stop'), required=True)
            p.add_argument('--evidence-file', required=True)
        elif action == 'finish':
            p.add_argument('--summary-file', required=True)
    args = parser.parse_args()
    if args.action == 'init':
        result = init(args)
    else:
        run = Path(args.run).resolve()
        with locked(run):
            state = read(run / 'state.json')
            if args.action == 'preflight':
                result = preflight(state)
            elif args.action == 'confirm':
                result = confirm(run, state, args)
            elif args.action == 'step':
                result = step(run, state, args)
            elif args.action == 'recover':
                result = recover(run, state, args)
            elif args.action == 'review':
                result = review(run, state, args)
            elif args.action == 'finish':
                if state['status'] not in ('completed', 'stopped', 'limit_reached', 'blocked'):
                    raise ValueError('Review or stop the run before finishing.')
                summary = Path(args.summary_file).read_text().strip()
                if not summary:
                    raise ValueError('Final summary cannot be empty.')
                state['final'] = summary
                (run / 'final.md').write_text(summary + '\n')
                write(run / 'state.json', state)
                result = state
            elif args.action == 'cleanup':
                if state['persistent'] or state['final'] is None:
                    raise ValueError('Cleanup requires a temporary run with a final summary already delivered.')
                # Do not delete an arbitrary directory containing a copied state.json.
                if not run.name.startswith('agent-relay-') or run.parent != Path(tempfile.gettempdir()).resolve():
                    raise ValueError('Refusing cleanup outside the relay temporary directory.')
                shutil.rmtree(run)
                result = {'removed': str(run)}
            else:
                result = state
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        sys.exit(1)
