---
name: workflow-monitor
description: Run a monitored four-stage Codex workflow with native subagents, evidence checks, independent review, and bounded revision. Use when the user asks for a parallel scan, review, synthesis, and independent acceptance workflow.
---

# Workflow Monitor

Use native subagent tools for the work. The plugin records progress and observes lifecycle events; it does not dispatch agents or decide whether a report is sound. Preserve the user's scope and Git authorization. Never treat Hook observations as proof of task return or content acceptance.

## Start and monitor

Use the installed plugin's `scripts/workflow.py` with `python3`; it loads its packaged code without the source checkout or `uv`. In commands below, substitute the actual absolute installed `PLUGIN_ROOT` and an absolute database path in a new run directory under the system temporary directory. Pass paths as command arguments, not through a shell export. Obtain the **current parent** session ID from the actual host context (`CODEX_SESSION_ID` when present); verify it belongs to this task. Do not infer it from the working directory or use `CODEX_THREAD_ID` as a substitute. Resolve the host-provided `PLUGIN_DATA` from the trusted SessionStart handoff using the same session ID. If the handoff is missing or stale, stop registration and report the block; a fresh Codex session may be required after plugin trust.

```text
python3 <PLUGIN_ROOT>/scripts/workflow.py workflow plugin-data --session-id <PARENT_SESSION_ID>
python3 <PLUGIN_ROOT>/scripts/workflow.py workflow --db <DB> start --session-id <PARENT_SESSION_ID> --plugin-data <PLUGIN_DATA>
python3 <PLUGIN_ROOT>/scripts/workflow.py workflow --db <DB> serve <RUN_ID> --plugin-data <PLUGIN_DATA>
python3 <PLUGIN_ROOT>/scripts/workflow.py workflow --db <DB> url <RUN_ID>
```

`plugin-data` prints the verified absolute path as a JSON string. Use that path in subsequent commands; do not guess it from the plugin cache, working directory, or user configuration.

`start` prints the run ID. Keep `serve` running in a background terminal/session and wait for `url` to print a healthy `http://127.0.0.1:<port>` address. Open that address once in the Codex **in-app browser** at workflow start. If no browser control is available, state the missing live UI check; the workflow may continue, but do not claim browser acceptance. Reuse the same DB and run ID for every command. `status <RUN_ID>` reads persisted state, including after a server restart; it does not resume agents. If the server stops, launch `serve` again, check `url`, and inspect actual agent/task state before continuing.

## Execute and record

Choose scan dimensions from the request and available evidence. Set parallel count to the smaller of useful independent dimensions and current native-agent capacity. Queue work that would interfere, such as performance measurements. For each task, create it **before** dispatch, then make an attempt. Commands below share the prefix `python3 <PLUGIN_ROOT>/scripts/workflow.py workflow --db <DB>`:

```text
task <RUN_ID> <STAGE> <NAME>              # prints TASK_ID
attempt <TASK_ID>                         # prints ATTEMPT_ID
bind <ATTEMPT_ID> <ACTUAL_AGENT_ID> [--turn-id <ACTUAL_TURN_ID>]
returned <ATTEMPT_ID>
interrupt <ATTEMPT_ID>
submit <TASK_ID> <ABSOLUTE_REPORT_FILE>   # prints VERSION
accept <TASK_ID> <VERSION>
advance <RUN_ID>                          # prints next stage
status <RUN_ID>
```

Bind the agent ID returned by the actual native dispatch. Supply a turn ID only if reliably available; never invent one. Explicitly mark `returned` after inspecting the actual agent result, even if a Hook stop was observed. If an attempt was interrupted before returning, use `interrupt <ATTEMPT_ID>`; it remains unreturned and cannot supply a report. Then create a new `attempt` before continuing or redispatching, even when reusing the same agent. Bind its real new turn ID when available. Do not let a late stop from an older turn stand in for the new return. Write each report to its own stable file in the run directory and leave accepted files unchanged. A changed or missing report invalidates acceptance. Check each report's evidence and scope before `accept`; a nonempty file alone is insufficient. If a returned report needs correction, use `rework <TASK_ID>`, then `attempt` and dispatch again.

Advance only after all current-stage tasks have returned, submitted a report, and passed content acceptance. The four stages are:

1. `scan`: parallel, independently scoped evidence collection. Each report records findings, source locations, uncertainty, and checks performed.
2. `review`: recheck the scan reports against original evidence, resolve contradictions, and document gaps. Do not merely summarize their claims.
3. `synthesis`: combine accepted evidence into a concrete recommendation or deliverable, with unresolved limits.
4. `independent_review`: use a **fresh, uninvolved context**. Give it the scope, artifacts, and original evidence needed to judge the latest synthesis. Ask for an explicit GO or specific changes; the main agent makes the final acceptance decision.

## Revision and stopping

Set a finite revision budget before dispatch (default: two requested synthesis revisions unless the user specifies another bound). Keep the synthesis task ID. On a substantive NO-GO, mark the independent review returned, submit its report, and run `revision <REVIEW_TASK_ID> <SYNTHESIS_TASK_ID> <REVIEW_VERSION>`; this preserves the review and old synthesis while returning to `synthesis`. Start a new synthesis attempt, submit a new report file/version, accept only after checking it, advance, then create a **new** independent-review task in fresh context. Repeat within budget. Do not accept a NO-GO review as GO, and do not call `finish` when the budget is exhausted. Report the run as blocked with the latest review findings, version history, and required next decision. If a review is GO, inspect its evidence, accept its version, then finish.

```text
finish <RUN_ID> --plugin-data <PLUGIN_DATA>
close <RUN_ID>
export <RUN_ID> <TASK_ID> <VERSION> <ABSOLUTE_OUTPUT_FILE>
```

`finish` unregisters the active run; `close` stops only its local monitor server. Neither deletes the database or report files. Keep the run directory as temporary state (normally 24 hours for review/export) and remove it only with separately authorized cleanup. At the end, compare `status` and the monitor with the accepted reports, explain the final decision and checks, and distinguish source tests, Hook delivery, installed-plugin behavior, desktop browser display, and report-content acceptance. Never claim real Hook or desktop acceptance from simulated events.
