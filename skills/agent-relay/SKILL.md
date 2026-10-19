---
name: agent-relay
description: Coordinate fixed Codex or Claude sessions that take turns assessing prior work and advancing a shared goal, with host review between iterations. Supports same-tool and mixed-tool relays.
---

# Agent Relay

Act as the host of a sequential relay. Workers perform task work; you objectively schedule, inspect evidence, decide acceptance, and summarize. Do not modify task deliverables yourself. The host is additional to the requested worker count.

## Prepare the run

Before starting any workers, assess whether the conversation supplies the task goal, working directory, each worker's tool (Codex or Claude), worker counts and order, maximum iterations, record retention and destination, and each worker's model and effort. Gather missing choices together, or propose clearly labeled values for the user to approve. Do not interpret an omitted retention choice as permission to discard records. An omitted model or effort may be proposed as “use the tool's configured default”; an omitted maximum may be proposed as “no fixed maximum; stop on completion, stagnation, or a blocker.” These are choices requiring confirmation, not silent assumptions.

Use the user's tool selection; do not silently substitute a different tool, model, or effort. If retention is requested without a destination, propose a new run directory under the target project's `relay-output/`. Use temporary storage only when that choice is confirmed. Do not change global skill symlinks or tool settings.

Derive observable completion criteria from the prompt before starting. Ask if essential ambiguity prevents acceptance. One iteration means one worker turn, not a full cycle. The maximum excludes host reviews. When the user confirms no fixed maximum, use the criteria to stop; do not invent an iteration limit. Stop and explain if repeated turns make no meaningful progress or a blocker requires user action.

Locate `scripts/agent_relay.py` relative to this skill directory; call it with Python 3.9+. Run `preflight --run RUN` after initialization to check each requested CLI's help and authentication status without a model call. It deliberately reports `cli_initialization_verified: false`: these checks cannot establish database, socket, network, or nested-sandbox access. Review each model/effort option against the installed tool's capabilities. Authentication output may contain personal information; summarize only availability.

Determine the outer host execution context before dispatch. Python and the CLI it launches inherit the restrictions placed on the host's shell command. An inner `workspace-write` flag cannot grant access denied by the outer sandbox, and `start_new_session=True` only creates an OS process group. If the controller requires access outside the host sandbox to initialize the local CLI, use the host's normal execution approval mechanism for the controller invocation. In a Codex host with an execution tool exposing `sandbox_permissions`, this means an authorized `require_escalated` tool call, not a shell flag or a change to the worker command. Do not assume a Claude host is unsandboxed; check its current execution permissions as well. Keep the worker's own sandbox and permission flags. Do not use bypass flags or `sudo` to solve this issue.

After resolving the proposed choices, write the task and criteria to UTF-8 files inside a hidden setup directory such as `PROJECT/.workspace/agent-relay-setup/`, then initialize. This prepares records only; it does not launch workers. Example (replace the paths):

```sh
python3 /path/to/agent-relay/scripts/agent_relay.py init \
  --workspace /path/to/project \
  --worker codex:1 --worker claude:1 \
  --prompt-file /path/to/project/.workspace/agent-relay-setup/prompt.txt \
  --criteria-file /path/to/project/.workspace/agent-relay-setup/criteria.txt \
  --max-iterations 10 \
  --save-dir /path/to/project/relay-output/run-unique
```

Use `--worker codex:2` or `--worker claude:2` for a same-tool relay. Repeated worker options preserve their order. Names use the tool and the one-based position in the full roster: the example creates `codex-1` and `claude-2`.

Assign settings by name with repeated `--worker-model WORKER_NAME=MODEL_ID` and `--worker-effort WORKER_NAME=EFFORT` options on `init`. For example, `--worker-effort codex-1=high --worker-effort claude-2=medium` selects different effort levels. Workers using the same tool can also have different settings. Omitted settings are stored as null and mean the tool's configured default, not a particular model or effort. Check the installed CLI's supported options and selected model's effort support; do not assume the same levels work in both tools. Explicit settings are passed on both creation and resume. An unsupported selection must be reported; do not silently fall back.

Omit `--save-dir` for the proposed temporary-storage choice, and omit `--max-iterations` for no fixed maximum. `init` returns an absolute run path and `awaiting_confirmation`. Do not create extra worker sessions through other mechanisms.

## Confirm before execution

Present the complete proposed configuration to the user: goal and acceptance criteria, workspace, ordered worker roster with each name/tool/model/effort, counts excluding the host, iteration ceiling or explicit no-ceiling choice, and retention choice with the actual absolute records directory. Label tool defaults explicitly; do not claim their concrete values are known unless verified. Include CLI/authentication availability, the proposed outer execution context, and any unresolved initialization or compatibility limitations. Ask for explicit confirmation of this configuration, even if the original request provided every field. Wait for the user's reply; do not launch a worker while waiting. If the user changes a choice, prepare the revised configuration and obtain confirmation for that version. Configuration confirmation and execution-tool approval are separate requirements; neither substitutes for the other.

Only after the user confirms, save their approval and its conversation context to a UTF-8 file under `RUN/.workspace/host/` (create that directory as needed), then run:

```sh
python3 /path/to/agent-relay/scripts/agent_relay.py confirm \
  --run /absolute/run/path --confirmation-file /absolute/run/path/.workspace/host/user-confirmation.txt
```

Never manufacture approval from silence, a general task request, or your own proposed plan. The controller records the approval evidence and a configuration fingerprint, then changes status to `ready`. It rejects unconfirmed or changed configurations before launching a CLI. This is a workflow gate implemented by a trusted host; the program cannot independently authenticate the author of the supplied approval text. Previously created runs without confirmation cannot advance under this version. Prepare a new run rather than bypassing the gate.

## Output layout

The output directory is for human readers. The only default public file for each iteration is `iterations/iteration-N.md` (one-based, without zero padding). The controller renders it from the worker's structured response and updates the same file with host review. It follows three stages: assessment of the previous iteration, proposal and execution plan, then results and handoff. The results section covers actual work, progress relative to the previous iteration, verification, unresolved issues, and next actions. Host review follows these worker sections. Failed or recovered attempts update this same report rather than adding more public files.

```text
RUN/
  iterations/
    iteration-1.md
    iteration-2.md
  .workspace/
    relay/                       State, locks, CLI logs, internal handoffs, retry metadata
    host/                        Approval, review, recovery, and final-summary inputs
    workers/WORKER_NAME/          Optional worker supporting files
```

Task deliverables follow the formats and destinations required by the task. Both host and workers keep operational records and supporting work in hidden working directories. Workers use the supplied `scratch_directory`, or another authorized hidden directory such as `.workspace` or `.worktree`, and identify useful supporting files in their handoffs. The controller consumes the worker's JSON response internally to produce the iteration report.

During each review, check that task deliverables, iteration reports, and working files are in their respective destinations. Have the worker correct misplaced files before continuing. This layout applies to new runs; existing runs retain their original files.

## Host one turn at a time

1. After user confirmation, invoke `step --run RUN`. It creates the selected worker's session on its first turn and resumes that exact ID afterward, passing that worker's configured model and effort each time. CLI processes exit between turns; conversation identities persist. All workers use the same workspace, sequentially. For every later iteration, the controller embeds all completed `iterations/iteration-N.md` files, including host reviews, as ordered `prior_iteration_reports` with absolute paths and full content. Missing, unreadable, or empty reports prevent dispatch; do not substitute the current deliverable or silently omit a report. Read [the worker protocol](references/worker-protocol.md) when evaluating adherence or changing worker behavior.
2. Read the returned handoff and inspect the actual deliverables and verification evidence. On iteration 2 onward, check that `assessment` identifies the prior reports read and responds to the preceding report's unresolved issues and next actions, including still-relevant items from earlier reports. A claim to have read only the current deliverable does not satisfy this check; request correction in host feedback rather than accept completion. Check whether the worker evaluated prior conclusions against evidence, justified its plan against the original goal, and accounted for progress, setbacks, and unfinished work. Preserve unresolved substantive disagreements for the next worker to investigate. Agreement supported by evidence is valid; a different opinion or an edit is not required for its own sake. Workers' claims are not sufficient for acceptance. You may perform read-only inspection and checks that do not alter task deliverables. Preserve substantive user clarifications in host feedback; a clarification that changes the goal or invalidates the agreed criteria requires stopping and starting a newly configured run.
3. Write an English host review under `RUN/.workspace/host/`, then invoke `review --run RUN --decision continue|complete|stop --evidence-file FILE`. Explain which criteria are met or unmet and give actionable feedback. Use `complete` only when the goal is met, even if iterations remain. Use `stop` for stagnation or an external blocker. A `continue` decision at the iteration ceiling produces `limit_reached`; it does not certify completion.
4. Only a `ready` status permits another step. Continue in the configured order. An execution or malformed-output failure blocks the run without automatic retries, because partial work or a session may already exist. Inspect logs and report the blocker; never silently replace a session. Follow the recovery procedure below before redispatching a failed or interrupted turn.

`status --run RUN` returns configuration, turns, and host reviews. Each turn has a timeout (default 900 seconds, override via `step --timeout SECONDS`); a timeout terminates its process group and blocks the run. A turn cannot advance until the host records a review. The program enforces order and gates; the host evaluates evidence.

## Recover a failed or interrupted attempt

Each invocation has separate `turn-NNNN-attempt-NN` prompt, stdout, stderr, and metadata files inside `RUN/.workspace/relay/`. A failed attempt does not consume an iteration or advance the roster. Internal handoffs and reviews retain `turn-NNNN.json` there. The public `iterations/iteration-N.md` is updated in place across retries and host review; do not create separate public attempt reports. Never overwrite failure logs or manually edit `.workspace/relay/state.json` to enable a retry.

Use `status` to inspect `error_kind` and the latest attempt. `startup_environment_blocked` means Codex reported the recognized initialization/permission failure before any start event; it is evidence of an execution-environment problem, not proof that no session exists. A similar error after work starts remains a general execution failure. The host must:

1. Verify the recorded process group and any related processes have stopped. Do not kill unrelated processes or dispatch duplicate work. The controller refuses recovery when the recorded process group still exists or its existence cannot be checked. A stale `running` status may be recovered only after this inspection.
2. Inspect actual task artifacts and CLI logs, then check tool-managed session records for a session belonging to this attempt. Missing stdout is insufficient evidence of nonexistence. Record partial work and tell the returning worker how to account for it without repeating completed actions.
3. For an outer-sandbox initialization failure, obtain normal execution-tool approval for the next controller step or use an already authorized execution context with the necessary access. If approval is unavailable or rejected, stop and report the blocker. The Python controller never escalates itself.
4. Write an English recovery evidence file under `RUN/.workspace/host/` describing process, artifact, session, and permission checks. Run `recover --run RUN --evidence-file FILE --execution-context approved|terminal|sandboxed`. The context is a host attestation, not a mechanism that grants permissions. The next `step` must actually be invoked through that authorized context.

When a session ID is known, recovery preserves it and the next attempt resumes it. If logs did not expose an ID but the host finds an existing session in tool-managed records, pass its ID with `--session-id ID`; this must be the original session, not a replacement. If no session is found after checking, explicitly add both `--no-session-found --authorize-initial-start`. Conflicting IDs are refused. Known sessions cannot be treated as new initial starts.

`recover` records the evidence and returns the same iteration to `ready`; it does not start a worker. The next attempt receives the recovery evidence in its task context. Any previous private closure note is preserved in the internal recovery history. Task deliverables remain at their authorized destinations during recovery. If work was already completed despite a missing handoff, assess whether resuming can safely produce the missing handoff; stop for manual investigation when the result is ambiguous. Legacy runs without attempt metadata, or with state files at the output root, require a new run; retain them unchanged as diagnostic evidence.

## Deliver and retain

Deliver the results in the formats and destinations required by the task, and report the outcome, verification, remaining issues, and stopping reason to the user. Distinguish successful completion from iteration exhaustion, a host stop, and execution failure.

Call `finish --run RUN` to record closure in internal state. An optional `--summary-file FILE` stores a private closure note; prepare that input under `RUN/.workspace/host/`.

For a temporary run, call `cleanup --run RUN` only after delivering the summary or copying the information needed for the user-facing response out of the run directory. If cleanup fails, disclose the remaining path. Persistent runs retain readable iteration reports and any task-requested deliverables; prompts, CLI logs, structured handoffs, reviews, closure notes, and session mappings remain inside `.workspace/`. A failed or interrupted temporary run retains diagnostics until summarized and cleaned; it is not automatically erased. Relay cleanup never deletes tool-managed conversation history or task deliverables.

## Implementation boundaries

The Python controller uses installed CLI tools and their existing accounts; no separate model API integration is required. Codex starts in `workspace-write`; Claude uses `acceptEdits` with unattended permission prompts denied. Existing tool settings and sandbox restrictions still apply. Blocked operations must be reported. Workers are instructed to stay within the task workspace; this instruction is not a replacement for OS isolation. Session IDs are pinned and checked, but context compaction is controlled by each tool. Separate sessions provide separate histories, not a guarantee of independent reasoning.

This directory is shared skill source for Codex and Claude. Installation into either tool is separate from creating or testing the skill. Do not change the user's current `ai-config` installation unless requested.
