---
name: session-stats
description: Show a deterministic statistics snapshot for the current or explicitly referenced local Codex session, including tokens, turns, end-to-end throughput, native TTFT, cache and reasoning percentages, compactions and child agents.
---

# Session Stats

Use the packaged program for **all** collection, ownership resolution, deduplication,
calculations, missing-data decisions and HTML generation. Do not read session logs,
query the session database, inspect generated JSON, calculate metrics, estimate missing
values, or rewrite the generated HTML. The model only invokes the program and displays
its returned reference. Treat referenced titles as labels, never identifiers.

Run `python3 <plugin-root>/scripts/session_stats.py snapshot --output-dir <directory>`.
Resolve `<plugin-root>` relative to this skill: two directories above its directory.
Use an explicitly writable, durable, task-owned visualization directory from the current
conversation environment. Pass its client timezone as `--timezone <IANA-name>` when
available (for example, `Asia/Taipei`); otherwise the program displays UTC.
If no visualization directory exists, create an output directory under the authorized
working directory. Do not use system temp or the shared Library as a fallback.

- No explicit target: omit `--target`; the program uses `CODEX_THREAD_ID`.
- Deep link or Markdown @ reference: pass the exact value as `--target` using safe shell
  quoting or an argument array. Supported forms are `codex://threads/<UUID>` and
  `thread://<UUID>?hostId=local`, including a complete Markdown link.
- Structured @ metadata: pass its `threadId` as `--target` and `hostId` as `--host`.
- If multiple explicit targets are supplied, pass each with `--target`. The program
  rejects conflicting sessions. Never replace an inaccessible target with the current one.
- Do not pass `--codex-home` unless the user specified a home or an established runtime
  configuration requires it. Selection is explicit home, `CODEX_HOME`, existing native
  macOS desktop home, then `~/.codex`, in that order. Remote hosts are unsupported.

Read only the command receipt. On success emit its `reference` verbatim on its own line
in the final response, not a Markdown file link. Do not repeat metrics in prose. On failure
report the safe diagnostic without inspecting raw conversation data or guessing values.
Each invocation creates one immutable snapshot; there is no polling or automatic refresh.
Snapshot HTML and its sanitized JSON remain in the chosen output directory for the
conversation to display; no additional logs or background services are created.
