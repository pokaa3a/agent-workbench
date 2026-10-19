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

## Automated behavior checks

Twenty-seven tests passed, covering all three configurations, session reuse, previous-handoff and review propagation, rejection of advancing before host review, iteration exhaustion, early acceptance without a configured limit, explicit host stopping, empty-review rejection, changed-session rejection, malformed responses, tool-reported errors, process timeout, concurrent-host locking, temporary-run finalization and cleanup, mandatory pre-run confirmation, confirmation invalidation after configuration changes, per-worker model/effort routing on both creation and resume, distinct settings for same-tool workers, and invalid worker assignments.

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
