"""Read structural fields only; never include conversation content in reports."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from . import StatsError

TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def timestamp(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, UTC) if math.isfinite(value) else None
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, OverflowError, OSError):
        pass
    return None


def iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def number(value):
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        else None
    )


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value):
        return None
    return value


def resolve_target(targets, host=None):
    resolved = set()
    for value in targets or [os.environ.get("CODEX_THREAD_ID", "")]:
        match = re.fullmatch(r"\[[^\n]*\]\(([^\s]+)\)", value)
        value = match.group(1) if match else value
        target_host = host or "local"
        if "://" in value:
            link = urlparse(value)
            query = parse_qs(link.query, keep_blank_values=True)
            if link.scheme == "codex" and link.netloc == "threads":
                value = link.path.removeprefix("/")
            elif link.scheme == "thread" and not link.path:
                value = link.netloc
            else:
                raise StatsError("Invalid session link.")
            if link.fragment or set(query) - {"hostId"} or len(query.get("hostId", [])) > 1:
                raise StatsError("Invalid session link parameters.")
            if "hostId" in query:
                if host and host != query["hostId"][0]:
                    raise StatsError("Conflicting host identifiers.")
                target_host = query["hostId"][0]
        if target_host != "local":
            raise StatsError("Only sessions on the local host are supported.")
        try:
            normalized = str(UUID(value))
            if normalized != value.lower():
                raise ValueError
        except (ValueError, AttributeError):
            raise StatsError(
                "A valid session UUID or current CODEX_THREAD_ID is required."
            ) from None
        resolved.add(normalized)
    if len(resolved) != 1:
        raise StatsError("Multiple different sessions were specified; select one.")
    return resolved.pop()


def resolve_home(explicit):
    if explicit:
        home = Path(explicit).expanduser()
    elif os.environ.get("CODEX_HOME"):
        home = Path(os.environ["CODEX_HOME"]).expanduser()
    else:
        desktop = Path.home() / "Library/Application Support/Codex/home"
        home = desktop if desktop.is_dir() else Path.home() / ".codex"
    if not home.is_dir():
        raise StatsError("Codex home is unavailable.")
    return home.resolve()


def read_index(home, target):
    databases = sorted(
        home.glob("state_*.sqlite"),
        key=lambda p: int(p.stem.split("_")[-1]) if p.stem.split("_")[-1].isdigit() else -1,
    )
    if not databases:
        raise StatsError("Codex session index is unavailable.")
    with sqlite3.connect(databases[-1].as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        rows = db.execute("SELECT id, rollout_path FROM threads").fetchall()
        available = dict(rows)
        if target not in available:
            raise StatsError("Requested session was not found in the selected Codex home.")
        try:
            edges = db.execute(
                "SELECT parent_thread_id, child_thread_id FROM thread_spawn_edges"
            ).fetchall()
            edge_warning = False
        except sqlite3.OperationalError:
            edges, edge_warning = [], True
        selected, pending = [], [target]
        while pending:
            current = pending.pop(0)
            if current in selected:
                continue
            if len(selected) >= 1000:
                raise StatsError("Session descendant count exceeds the supported limit.")
            selected.append(current)
            pending.extend(
                sorted(
                    child for parent, child in edges if parent == current and child not in selected
                )
            )
    return [
        (thread, Path(available[thread]) if thread in available else None) for thread in selected
    ], edge_warning


def tokens(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for key in TOKEN_KEYS:
        raw = value.get(key)
        result[key] = (
            raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else None
        )
    if (
        result["input_tokens"] is not None
        and result["cached_input_tokens"] is not None
        and result["cached_input_tokens"] > result["input_tokens"]
    ):
        return None
    if (
        result["output_tokens"] is not None
        and result["reasoning_output_tokens"] is not None
        and result["reasoning_output_tokens"] > result["output_tokens"]
    ):
        return None
    if (
        all(result[k] is not None for k in ("input_tokens", "output_tokens", "total_tokens"))
        and result["input_tokens"] + result["output_tokens"] != result["total_tokens"]
    ):
        return None
    return result if any(v is not None for v in result.values()) else None


def sum_tokens(items):
    items = list(items)
    return {
        key: sum(item[key] for item in items)
        if items and all(item[key] is not None for item in items)
        else None
        for key in TOKEN_KEYS
    }


def collect_thread(thread, path, cutoff):
    warnings = set()
    turns, responses, user_ids = {}, {}, set()
    legacy, active, own_meta, forked = [], None, False, False
    compactions = {}
    observed_items = False
    created_at = None
    future_session = False
    owned_turns = set()
    if path is None or not path.is_file():
        return {
            "thread_id": thread,
            "turns": [],
            "tokens": dict.fromkeys(TOKEN_KEYS),
            "user_message_count": None,
            "warnings": ["session_unavailable"],
            "usage_source": "unavailable",
        }

    def turn(key):
        return turns.setdefault(
            key,
            {
                "thread_id": thread,
                "turn_id": key,
                "started_at": None,
                "completed_at": None,
                "duration_ms": None,
                "native_ttft_ms": None,
                "status": "incomplete",
                "_usage": [],
                "_native_start": None,
            },
        )

    with path.open("rb") as stream:
        limit = os.fstat(stream.fileno()).st_size
        while stream.tell() < limit:
            raw = stream.readline(limit - stream.tell())
            if not raw.endswith(b"\n"):
                warnings.add("truncated_record")
                continue
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeError):
                warnings.add("malformed_record")
                continue
            if not isinstance(row, dict):
                warnings.add("malformed_record")
                continue
            at = timestamp(row.get("timestamp"))
            if at is None:
                warnings.add("missing_event_timestamp")
                continue
            payload = row.get("payload")
            if at > cutoff:
                if (
                    row.get("type") == "session_meta"
                    and isinstance(payload, dict)
                    and payload.get("id") == thread
                ):
                    future_session = True
                continue
            if not isinstance(payload, dict):
                continue
            if row.get("type") == "session_meta":
                if payload.get("id") == thread:
                    if not own_meta:
                        own_meta = True
                        forked = forked or bool(payload.get("forked_from_id"))
                        created_at = at
                else:
                    forked = True
                continue
            if not own_meta:
                continue
            kind = payload.get("type") if row.get("type") == "event_msg" else row.get("type")
            if payload.get("thread_id") not in (None, thread):
                continue
            key = identifier(payload.get("turn_id")) or active
            if kind == "task_started":
                if not key:
                    warnings.add("missing_turn_id")
                    continue
                active = key
                record = turn(key)
                record["_native_start"] = timestamp(payload.get("started_at"))
                start = record["_native_start"] or at
                record["started_at"] = iso(start)
                if record["status"] != "completed":
                    record["status"] = "in_progress"
            elif kind in ("task_complete", "turn_aborted"):
                if not key:
                    warnings.add("missing_turn_id")
                    continue
                record = turn(key)
                end = timestamp(payload.get("completed_at")) or at
                record["_native_start"] = (
                    timestamp(payload.get("started_at")) or record["_native_start"]
                )
                start = record["_native_start"] or timestamp(record["started_at"])
                duration = number(payload.get("duration_ms"))
                if duration is None and start and end >= start:
                    duration = (end - start).total_seconds() * 1000
                record.update(
                    started_at=iso(start),
                    completed_at=iso(end),
                    duration_ms=duration,
                    native_ttft_ms=number(payload.get("time_to_first_token_ms")),
                    status="completed" if kind == "task_complete" else "interrupted",
                )
                if active == key:
                    active = None
            elif kind == "token_usage_record":
                # Explicit ownership is necessary to exclude inherited fork history.
                if payload.get("thread_id") != thread:
                    warnings.add("unowned_usage_record")
                    continue
                response = identifier(payload.get("response_id"))
                usage = tokens(payload.get("usage"))
                if not response or not key or usage is None:
                    warnings.add("invalid_usage_record")
                    continue
                identity = response
                if identity in responses and responses[identity] != (key, usage):
                    warnings.add("conflicting_usage_record")
                    continue
                responses[identity] = (key, usage)
                owned_turns.add(key)
            elif kind == "token_count":
                info = payload.get("info")
                if isinstance(info, dict):
                    usage = tokens(info.get("total_token_usage"))
                    if usage:
                        legacy.append(usage)
            elif kind == "item_completed":
                if payload.get("thread_id") == thread and key:
                    owned_turns.add(key)
                item = payload.get("item", {})
                if payload.get("thread_id") == thread and isinstance(item, dict):
                    observed_items = True
                    if item.get("type") in ("ContextCompaction", "contextCompaction"):
                        item_id = identifier(item.get("id"))
                        if item_id:
                            start = number(payload.get("started_at_ms"))
                            end = number(payload.get("completed_at_ms"))
                            elapsed = (
                                end - start
                                if start is not None and end is not None and end >= start
                                else None
                            )
                            if item_id in compactions and compactions[item_id] != elapsed:
                                compactions[item_id] = None
                            else:
                                compactions[item_id] = elapsed
                if isinstance(item, dict) and item.get("type") in (
                    "UserMessage",
                    "userMessage",
                    "user_message",
                ):
                    item_id = identifier(item.get("id"))
                    if item_id and payload.get("thread_id") == thread:
                        user_ids.add(item_id)
    if not own_meta and future_session:
        return None
    if not own_meta:
        raise StatsError("Session file identity did not match the requested session.")
    if forked:
        # Forks retain copied parent lifecycle with rewritten outer timestamps.
        # Native inner starts and explicit owned item/usage IDs establish ownership.
        turns = {
            key: record
            for key, record in turns.items()
            if key in owned_turns
            or (
                created_at
                and record["_native_start"]
                and record["_native_start"].timestamp() >= math.floor(created_at.timestamp())
            )
        }
    for key, usage in responses.values():
        turn(key)["_usage"].append(usage)
    totals = sum_tokens(usage for _, usage in responses.values())
    source = "per_response" if responses else "unavailable"
    if not responses and legacy:
        # Cumulative counters are never summed. Fork baselines cannot be inferred safely.
        if not forked:
            totals = legacy[-1]
            source = "legacy_cumulative"
        warnings.add("legacy_usage_incomplete")
    elif responses and legacy:
        warnings.add("legacy_counters_ignored")
    if not responses and not legacy:
        warnings.add("usage_unavailable")
    result_turns = []
    for record in turns.values():
        record.pop("_native_start")
        record["tokens"] = sum_tokens(record.pop("_usage"))
        if record["tokens"]["total_tokens"] is None:
            warnings.add("partial_turn_usage")
        duration, output = record["duration_ms"], record["tokens"]["output_tokens"]
        record["end_to_end_output_tokens_per_second"] = (
            round(output * 1000 / duration, 3) if duration and output is not None else None
        )
        record["model_generation_tokens_per_second"] = None
        result_turns.append(record)
    result_turns.sort(key=lambda r: (r["started_at"] or r["completed_at"] or "", r["turn_id"]))
    return {
        "thread_id": thread,
        "turns": result_turns,
        "tokens": totals,
        "user_message_count": len(user_ids) if user_ids else None,
        "compaction_count": len(compactions) if observed_items else None,
        "compaction_duration_ms": sum(compactions.values())
        if observed_items and all(v is not None for v in compactions.values())
        else None,
        "usage_source": source,
        "warnings": sorted(warnings),
    }


def aggregate(threads):
    rows = [row for thread in threads for row in thread["turns"]]
    measured = [
        row for row in rows if row["duration_ms"] and row["tokens"]["output_tokens"] is not None
    ]
    duration = sum(row["duration_ms"] for row in measured)
    ttfts = [row["native_ttft_ms"] for row in rows if row["native_ttft_ms"] is not None]
    totals = sum_tokens(thread["tokens"] for thread in threads)

    def percent(numerator, denominator):
        return (
            round(totals[numerator] * 100 / totals[denominator], 3)
            if totals[numerator] is not None and totals[denominator]
            else None
        )

    def complete_sum(key):
        values = [thread.get(key) for thread in threads]
        return sum(values) if values and all(v is not None for v in values) else None

    return {
        "cache_hit_percent": percent("cached_input_tokens", "input_tokens"),
        "reasoning_percent": percent("reasoning_output_tokens", "output_tokens"),
        "compaction_count": complete_sum("compaction_count"),
        "compaction_duration_ms": complete_sum("compaction_duration_ms"),
        "thread_count": len(threads),
        "turn_count": len(rows),
        "completed_turn_count": sum(row["status"] == "completed" for row in rows),
        "tokens": totals,
        "native_ttft_mean_ms": round(sum(ttfts) / len(ttfts), 3) if ttfts else None,
        "ttft_measured_turn_count": len(ttfts),
        "end_to_end_output_tokens_per_second": round(
            sum(row["tokens"]["output_tokens"] for row in measured) * 1000 / duration, 3
        )
        if duration
        else None,
        "throughput_measured_turn_count": len(measured),
        "model_generation_tokens_per_second": None,
    }


def snapshot(home, target, cutoff):
    index, edge_warning = read_index(home, target)
    threads = []
    for thread, path in index:
        try:
            collected = collect_thread(thread, path, cutoff)
            if collected is not None:
                if thread == target and "session_unavailable" in collected["warnings"]:
                    raise StatsError("Requested session data is unavailable.")
                threads.append(collected)
            elif thread == target:
                raise StatsError("Requested session did not exist at the cutoff.")
        except (OSError, StatsError):
            if thread == target:
                raise StatsError(
                    "Requested session data is unavailable or has a mismatched identity."
                ) from None
            threads.append(
                {
                    "thread_id": thread,
                    "turns": [],
                    "tokens": dict.fromkeys(TOKEN_KEYS),
                    "user_message_count": None,
                    "warnings": ["session_unavailable"],
                    "usage_source": "unavailable",
                }
            )
    return {
        "schema_version": 1,
        "target_id": target,
        "host_id": "local",
        "captured_at": iso(cutoff),
        "scopes": {
            "main": aggregate(threads[:1]),
            "children": aggregate(threads[1:]),
            "combined": aggregate(threads),
        },
        "threads": threads,
        "turns": [row for thread in threads for row in thread["turns"]],
        "warnings": ["descendant_index_unavailable"] if edge_warning else [],
        "definitions": {
            "tokens": (
                "Cached input is a subset of input; reasoning output is a subset of output. "
                "Total uses the recorded total, not the sum of every field."
            ),
            "turns": (
                "Distinct owned task turns; user message count is reported separately "
                "when native item IDs exist."
            ),
            "throughput": (
                "Recorded output tokens divided by matched completed/interrupted turn duration; "
                "aggregate uses summed tokens / summed durations, including tool time. "
                "Parallel child durations are summed, not wall-clock elapsed time."
            ),
            "ttft": (
                "Native task_complete.time_to_first_token_ms; mean over measured turns, "
                "not inferred per-request latency."
            ),
            "generation_speed": "Unavailable: no verified model generation duration.",
            "cutoff": (
                "Events at or before captured_at, bounded by each file size when opened; "
                "active writers may leave incomplete records."
            ),
            "legacy": (
                "Legacy cumulative-only totals are incomplete; "
                "never summed or used for per-turn throughput."
            ),
        },
    }
