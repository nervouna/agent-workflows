# Session Stats

Session Stats shows a read-only snapshot of a local Codex conversation inside the
Codex App. Python handles collection, deduplication, calculations and HTML rendering.
The model invokes the program and displays its returned reference. No model API,
background service, polling or network request is used by the program or view.

## Use

Invoke the `session-stats` skill and ask for session statistics. Without a target,
it uses the invoking process's `CODEX_THREAD_ID`. Explicit targets can be:

- `codex://threads/<UUID>`
- A conversation @ mention with `thread://<UUID>?hostId=local`
- A UUID passed by structured conversation-reference metadata

Repeated references to the same session are accepted. Conflicting sessions, malformed
links, unknown sessions and remote hosts fail without switching to the current session.
The mention title does not select the session.

The view has main-session, recursive child-agent and combined scopes, token breakdown,
turn counts, average native TTFT, end-to-end output throughput and per-turn details.
Changing scope uses already computed data. Each invocation produces a new snapshot;
the current invocation's unfinished turn appears as in progress when recorded.
Inline fragments are limited to 1 MB. Larger sessions receive an explicit size-limit
error; this version does not paginate them across multiple fragments.

## Install for local trial

Python 3.12 or later is required. Build a standalone payload from this repository:

```sh
uv run python -m codex_maintenance.session_stats package \
  --output dist/session-stats-marketplace/plugins/session-stats
```

The destination must not already exist. Rebuild into a new directory when updating.
The package includes the Python standard-library-only implementation and fixed HTML
template; runtime execution does not require uv or the repository.

Create `dist/session-stats-marketplace/.agents/plugins/marketplace.json`:

```json
{
  "name": "codex-maintenance-local",
  "plugins": [{
    "name": "session-stats",
    "source": {"source": "local", "path": "./plugins/session-stats"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

Register and install with the Codex plugin CLI:

```sh
codex plugin marketplace add "$PWD/dist/session-stats-marketplace" --json
codex plugin add session-stats@codex-maintenance-local --json
```

This uses the [official plugin packaging and marketplace format](https://developers.openai.com/plugins/build/plugins).
Keep the local marketplace directory while using or updating the installation.
Local installation and automated checks do not constitute user acceptance.

## Direct execution

```sh
python3 /path/to/plugin/scripts/session_stats.py snapshot \
  --target 'codex://threads/<UUID>' \
  --output-dir /absolute/task-owned/visualization-directory
```

Omit `--target` for the current session. `--host local` accepts a structured mention's
host. `--at 2026-10-05T02:00:00Z` fixes the UTC cutoff for a reproducible snapshot.
`--timezone Asia/Taipei` selects the display timezone; direct CLI execution defaults to UTC.
The output directory must be writable and accessible to the conversation renderer.
The CLI returns only sanitized artifact paths and the inline display reference.

Codex home selection is explicit `--codex-home`, then `CODEX_HOME`, then an existing
`~/Library/Application Support/Codex/home`, then `~/.codex`. The program chooses one
home and does not search another home after a missing-session error.

## Accounting and source format

The collector opens the highest-version `state_*.sqlite` read-only, follows
`threads.rollout_path`, and traverses `thread_spawn_edges`. It reads only records
through the capture cutoff and bounds each rollout read to its initial byte size.
An incomplete final line is skipped and reported. This is a bounded snapshot of
active files, not a transaction spanning all writers and rollout files.

The supported native format was observed in Codex 0.159.0 local rollouts:

- `token_usage_record` owns usage by `thread_id`, `turn_id` and `response_id`.
  Identical response IDs are counted once. Conflicting records are flagged and
  excluded from additional accounting. Token values must be nonnegative integers;
  recorded total must equal input plus output when all three exist.
- Cached input is a subset of input; reasoning output is a subset of output.
  Token dimensions with missing measurements remain null. Total uses the recorded
  total, never the sum of all displayed dimensions.
- Turns are distinct owned lifecycle IDs, not the number of messages. Native
  `item_completed` user-message IDs are counted separately when available.
- Forked histories can include a copied parent `session_meta` and rewritten event
  timestamps. Explicitly owned usage/item turn IDs and native lifecycle start times
  relative to the target's creation exclude inherited parent turns.
- Native `task_complete.duration_ms` supplies turn duration. A start/end difference
  is used only when both recorded timestamps are available. An active turn has no
  completed duration or throughput.
- Native `task_complete.time_to_first_token_ms` supplies TTFT. The view averages
  measured turns and shows coverage. This is the recorded turn metric, not a claim
  about every internal model request's latency.
- End-to-end throughput is output tokens divided by matched turn duration, including
  tool execution and waiting. Aggregate throughput divides summed output by summed
  durations, including parallel child durations. It is not concurrent wall-clock
  throughput or model decode speed. Decode speed remains uncollected because no
  verified generation-duration field is available.
- Cached-input percentage is summed cached input divided by summed input; reasoning
  percentage is summed reasoning output divided by summed output. Missing values or
  zero denominators produce null, not zero percent.
- Compactions use explicitly owned `ContextCompaction` item completions, deduplicated
  by item ID within each thread. Duration is `completed_at_ms - started_at_ms` and
  is summed across unique items. Missing, reversed or conflicting durations produce
  a null total. Threads with no observed owned item records have unknown compaction
  coverage. An observed item stream without compactions yields zero. Parallel child
  durations are cumulative rather than elapsed wall-clock time.
- Legacy-only `token_count` uses the last cumulative record without summing it and
  is marked incomplete. Forked legacy counters cannot establish ownership and are
  excluded. Modern response records take precedence over legacy counters; missing
  per-turn usage remains visible.

These rollout fields are an observed local storage format, not a stable public API.
Schema changes fail safely or surface missing/incomplete measurements. An unavailable
child is reported and prevents a falsely complete combined token total.

## Privacy and retention

The program reads session records locally and exports only an allowlist of identifiers,
timestamps, numerical measurements, coverage and fixed diagnostic codes. It exports
no message body, prompt, tool arguments, tool output, title or credentials. Exceptions
from raw parsing and filesystem operations are replaced with content-free diagnostics.

Each snapshot writes content-addressed HTML and sanitized JSON in the supplied
visualization directory. Those files persist so previous messages can render. There
are no extra logs, caches or automatic cleanup jobs. Remove those specific snapshot
files when their associated conversation output is no longer needed. Session history,
configuration and the index database are never modified.
