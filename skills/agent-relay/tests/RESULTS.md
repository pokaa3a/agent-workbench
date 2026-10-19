# Agent Relay validation

Validated on October 18, 2026 with Python 3.9.6, Codex CLI 0.162.1, and Claude Code 2.1.296. All implementation, protocol, and test files are written in English.

## Real CLI relay tests

The original implementation was validated with the three cases below before the confirmation/model-setting update. Each case used a separate temporary Git workspace and two worker sessions, excluding the host. The host test driver dispatched four sequential iterations and checked the actual shared `ledger.txt` after every turn. It accepted completion only after checking all four entries.

| Configuration | Iterations | Result |
| --- | --- | --- |
| Codex + Codex | 4 | Passed |
| Claude + Claude | 4 | Passed |
| Codex + Claude | 4 | Passed |

In every case, the two session IDs were distinct, iteration 3 reused iteration 1's ID, and iteration 4 reused iteration 2's ID. Every worker returned a valid handoff, and all earlier ledger entries survived subsequent turns. Inspection of the handoffs confirmed that returning workers assessed the current artifact against the preceding handoff and host feedback.

Run artifacts, including controller state, prompts, CLI logs, handoffs, host reviews, and final summaries, remain at these local temporary locations:

- Codex: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-codex-8mc7jhcl`
- Claude: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-claude-loodu3xm`
- Mixed: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-mixed-e8k_bs_r`

Temporary storage may be removed by the operating system. The paths above are evidence locations for this run, not required runtime configuration.

## Model and confirmation update

A further four-turn mixed-tool live test passed with explicit worker settings: `codex-1` used `gpt-6.1-sol` with `low` effort, and `claude-2` used the `sonnet` model alias with `low` effort. Both worker IDs were reused on their second turns, all handoffs parsed, and the host checked the actual ledger after every turn. The run passed through `awaiting_confirmation` and the explicit `confirm` command before dispatch.

Artifacts: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-mixed-ypvjborl`.

This smoke test verifies that the installed CLIs accept the explicit settings during creation and resume; it does not measure how much reasoning effort the model internally performs. A model alias resolves according to the tool/provider and is not a pinned model version. The confirmation gate stores evidence supplied by the host; conversational approval remains the host's responsibility and was not independently authenticated by the controller.

## Startup-environment recovery update

A new isolated Codex test reproduced the actual nested-sandbox initialization failure without changing the original failed user run. Preflight reported successful CLI help/login checks while correctly leaving initialization unverified. The first attempt failed with `startup_environment_blocked`, zero committed turns, and no observed session ID.

Before recovery, the host checked the stopped process group, the unique workspace for partial artifacts, and tool-managed thread registrations for an existing session. No session was found. Through the normal outer-host execution approval mechanism, the host explicitly authorized an initial start, recovered the same iteration, and completed two real worker turns using one fixed session ID. Three distinct attempt records remained: failed initialization, successful first turn, and resumed second turn. Original failure logs survived unchanged.

Artifacts: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-recovery-_94rdtlt`.

Inspection of the tool-managed session state confirmed that the worker retained a restricted filesystem policy permitting writes to its workspace and a restricted network policy. The test initially expected the legacy policy label `workspace-write`; the installed CLI stores its expanded equivalent as `managed`, so the final check inspected the actual access rules rather than relying on that label. The saved `sandbox-verification.json` contains the resolved policy. Outer execution approval did not grant the worker unrestricted access.

A further four-turn mixed Codex/Claude regression test passed with explicit model/effort settings, stable session IDs, host artifact checks, and the new per-attempt logs. Artifacts: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-mixed-3ycf92p6`.

Additional automated tests cover initialization-error classification, non-overwriting retries, known and discovered session preservation, conflicting-ID rejection, process-group checks, stale-running recovery, required evidence, configuration integrity, legacy-run refusal, preflight privacy, and Claude failed-result session preservation. Recovery evidence is supplied by the host; the controller cannot independently authenticate approval, inspect every possible external session store, or grant outer execution permissions.

## Human-readable output layout update

Thirty automated tests passed after moving all controller state, locks, prompts, CLI logs, structured handoffs, attempt metadata, and archived summaries into `RUN/.workspace/relay/`. New tests verify exactly one `iterations/iteration-N.md` per iteration, in-place host-review updates, one public report across failed and recovered attempts, hidden scratch paths, and refusal to silently modify legacy layouts.

A four-turn mixed Codex/Claude live test passed with the new layout. The output root contained only `iterations/`, `.workspace/`, and the host's final `final.md`. The iteration directory contained exactly `iteration-1.md` through `iteration-4.md`, each with substantive handoff sections and host review. Both workers placed their requested supporting notes under `.workspace/workers/WORKER_NAME/support.txt`. Session reuse and the shared task artifact were also checked after each turn.

Artifacts: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-mixed-2pq_mz25/workspace/relay-output`.

Public reports are rendered by the controller, so retries and host review do not create duplicate public files. Placement of arbitrary worker-created task and supporting files is governed by the worker instructions and host review, not a new OS sandbox boundary. Existing user runs and their historical output were left unchanged; this layout requires a new run.

## Task-dependent final deliverables

The controller no longer exports `final.md`. `finish --run RUN` records closure without requiring a summary file or producing a public deliverable. An optional `--summary-file` stores a private closure note in internal state only. Task requirements determine final output files, formats, and destinations; an answer in the host conversation can be sufficient.

Thirty-two automated tests passed. New checks verify closure without a summary or public file, optional private summary storage, and preservation of a task-requested `final.md` during recovery. Historical live runs above retain the outputs generated by the versions tested at that time. No additional model calls were needed for this deterministic finalization change.

## Three-stage critical handoff protocol

The worker protocol and public reports now use three stages: assessment of the previous iteration, proposal and execution plan, and results and handoff. A required `progress` field records what was advanced, corrected, overturned, confirmed, or left unchanged. Assessment may be empty on the first iteration; later iterations require a nonempty assessment. Other handoff fields require nonempty text. Historical handoffs lacking progress remain renderable with an explicit missing-record notice.

Thirty-six automated tests passed. New coverage checks both CLI response formats, first-turn versus later-turn assessment requirements, required progress and execution fields, the three-stage report, and preservation of evidence, unresolved disagreement, and next actions in the following worker's context.

A four-turn mixed Codex/Claude live test passed with `--challenge`. After the first host review, the test driver changed the ledger's correct first entry to `1 wrong-worker`, contradicting both the prior handoff and the host's earlier observation. The second worker inspected the actual file, identified the discrepancy, repaired the entry, and distinguished possible causes from established facts. Its handoff retained the unresolved cause and recommended that the next worker inspect the actual file. Later turns rechecked the corrected artifact and completed the ledger. Both original session IDs were reused and only the four expected iteration reports were public.

Artifacts: `/private/var/folders/l0/5jbws6fs5ln337kpn0_1jszm0000gn/T/relay-live-mixed-162inee1/workspace/relay-output`.

The second worker also disclosed that its first command appended a line before it had completed inspection, then described the subsequent correction. This test demonstrates discrepancy detection, repair, and an honest handoff in one small scenario; it does not establish strict internal planning order or elimination of reasoning bias. The controller validates response fields and renders reports; the host evaluates the substance and evidence.

## Prior iteration report delivery

The controller now embeds the complete UTF-8 contents and absolute paths of every completed prior `iterations/iteration-N.md`, including host review, into each subsequent worker prompt in iteration order. This applies to new and resumed sessions. The protocol requires workers to read these reports before planning or editing, identify them in their assessment, and address prior unresolved issues and next actions. Host acceptance checks the substance of that assessment.

Thirty-nine automated tests passed. New coverage checks all three worker configurations across four turns, exact full-report delivery including Unicode host-review items absent from task deliverables, saved prompt contents, rejection of missing/empty/invalid-UTF-8 reports before CLI dispatch without consuming an attempt, and recovery that includes completed reports while excluding the current incomplete report. These tests mock the CLI and verify context delivery and dispatch behavior; they do not establish a model's actual comprehension. No additional live model calls were made for this update.

## Automated behavior checks

Thirty-nine tests passed, covering all three configurations, session reuse, complete prior-report delivery, previous-handoff and review propagation, rejection of advancing before host review, iteration exhaustion, early acceptance without a configured limit, explicit host stopping, empty-review rejection, changed-session rejection, malformed responses, tool-reported errors, process timeout, concurrent-host locking, temporary-run finalization and cleanup, mandatory pre-run confirmation, confirmation invalidation after configuration changes, per-worker model/effort routing on both creation and resume, distinct settings for same-tool workers, and invalid worker assignments.

The bundled skill validator also passed. PyYAML was installed only into a temporary validation environment; the relay itself uses Python's standard library.

Commands from the repository root:

```sh
python3 -m unittest discover -s skills/agent-relay/tests -v
python3 skills/agent-relay/tests/live_smoke.py codex --approve-test
python3 skills/agent-relay/tests/live_smoke.py claude --approve-test
python3 skills/agent-relay/tests/live_smoke.py mixed --approve-test
```

The updated live driver requires explicit `--approve-test` authorization for its known four-turn test configuration and records that caller authorization through the controller confirmation gate. Optional `--codex-model`, `--claude-model`, `--codex-effort`, and `--claude-effort` flags exercise explicit settings. This test-driver authorization is distinct from the conversational confirmation required when a host uses the skill.

Live smoke tests use installed tools and existing accounts, consume model usage, and retain their test artifacts in a printed temporary directory.

## Corrections and limits

Initial sandbox checks could not access existing CLI session storage and Claude authentication. Running the authorized tests through the environment's ordinary approval mechanism resolved access without changing account configuration or bypassing the worker tools' permission controls.

Validation strengthened error handling so a Codex failure event cannot be mistaken for a successful handoff even if a response preceded it. Missing or malformed handoffs and changed session IDs block further dispatch. There is no automatic replacement session or retry after ambiguous partial execution.

These are small artifact-editing smoke tests with deterministic host acceptance checks. They establish actual CLI interoperability and conversation reuse, not the quality of debate on complex tasks, automatic skill discovery in both products, or every possible host environment. Early completion and cleanup were verified in automated behavior tests rather than additional model calls. Unexpected controller termination can leave a stale `running` state; the explicit `recover` operation requires host inspection and refuses recovery while the recorded process group still exists. Legacy failed runs without attempt metadata require a new run. Context compaction remains tool-controlled.

No global skill installation, existing symlink, or `ai-config` file was changed.
