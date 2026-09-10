#!/usr/bin/env python3
"""Collect deterministic Codex history metrics and render a private report."""

from __future__ import annotations

import argparse
import contextlib
import copy
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONTRACT_VERSION = 1
SOURCE_KINDS = [
    "cli",
    "vscode",
    "exec",
    "appServer",
    "subAgent",
    "subAgentReview",
    "subAgentCompact",
    "subAgentThreadSpawn",
    "subAgentOther",
    "unknown",
]
SENSITIVE_KEYS = re.compile(
    r"(?:authorization|password|passwd|passphrase|secret|token|api[_-]?key|cookie|session)",
    re.IGNORECASE,
)
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
    re.compile(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_\-]{16,}\b"),
]


def _timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 100_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    raise ValueError(f"unsupported timestamp: {value!r}")


def _in_window(value: Any, start: datetime, end: datetime) -> bool:
    try:
        instant = _timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return start <= instant < end


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _tidy_number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 2)


def describe_distribution(values: list[int | float]) -> dict[str, int | float]:
    """Return stable, interpolation-based descriptive statistics."""
    if not values:
        return {"count": 0, "mean": 0, "median": 0, "p25": 0, "p75": 0, "p90": 0}
    numeric = [float(value) for value in values]
    return {
        "count": len(numeric),
        "mean": _tidy_number(sum(numeric) / len(numeric)),
        "median": _tidy_number(_percentile(numeric, 0.5)),
        "p25": _tidy_number(_percentile(numeric, 0.25)),
        "p75": _tidy_number(_percentile(numeric, 0.75)),
        "p90": _tidy_number(_percentile(numeric, 0.9)),
    }


def _optional_distribution(values: list[int | float]) -> dict[str, int | float | None]:
    if values:
        return describe_distribution(values)
    return {"count": 0, "mean": None, "median": None, "p25": None, "p75": None, "p90": None}


def summarize_activity(timestamps: list[Any], *, timezone: str) -> dict[str, dict[str, int]]:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown timezone: {timezone}") from error
    hours: Counter[str] = Counter()
    day_parts: Counter[str] = Counter()
    weekdays: Counter[str] = Counter()
    for raw in timestamps:
        try:
            local = _timestamp(raw).astimezone(zone)
        except (TypeError, ValueError, OverflowError):
            continue
        hours[f"{local.hour:02d}"] += 1
        part = (
            "late_night"
            if local.hour < 6
            else "morning"
            if local.hour < 12
            else "afternoon"
            if local.hour < 18
            else "evening"
        )
        day_parts[part] += 1
        weekdays["weekday" if local.weekday() < 5 else "weekend"] += 1
    return {
        "by_hour": dict(sorted(hours.items())),
        "day_parts": dict(day_parts.items()),
        "weekday_weekend": dict(weekdays.items()),
    }


def _coverage(available: int, eligible: int) -> dict[str, int | float]:
    return {
        "available": available,
        "eligible": eligible,
        "ratio": round(available / eligible, 4) if eligible else 0.0,
    }


def _top_decile_share(values: list[int]) -> float | None:
    if not values or not sum(values):
        return None
    count = max(1, math.ceil(len(values) * 0.1))
    return round(sum(sorted(values, reverse=True)[:count]) / sum(values), 4)


def _calendar_distribution(timestamps: list[Any], timezone: str) -> dict[str, Any]:
    zone = ZoneInfo(timezone)
    dates: Counter[str] = Counter()
    weekdays: Counter[str] = Counter()
    for value in timestamps:
        try:
            local = _timestamp(value).astimezone(zone)
        except (TypeError, ValueError, OverflowError):
            continue
        dates[local.date().isoformat()] += 1
        weekdays[local.strftime("%A").lower()] += 1
    return {
        "active_days": len(dates),
        "by_date": dict(sorted(dates.items())),
        "by_weekday": dict(weekdays.items()),
    }


TOKEN_FIELDS = {
    "input_tokens": "inputTokens",
    "cached_input_tokens": "cachedInputTokens",
    "net_new_input_tokens": "netNewInputTokens",
    "output_tokens": "outputTokens",
    "total_tokens": "totalTokens",
}


def _latest_usage_groups(thread: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots = thread.get("usage_snapshots") or []
    if not snapshots:
        return []
    latest = snapshots[-1]
    groups = latest.get("groups") if isinstance(latest, dict) else None
    return [group for group in (groups or []) if isinstance(group, dict)]


def summarize_history(
    threads: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    timezone: str,
    collection_time: datetime | None = None,
) -> dict[str, Any]:
    """Summarize normalized history in the half-open interval [start, end)."""
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if start >= end:
        raise ValueError("start must be earlier than end")
    roots = [thread for thread in threads if not _is_subagent(thread)]
    children = [thread for thread in threads if _is_subagent(thread)]

    def turns_in_window(thread: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            turn
            for turn in thread.get("turns", [])
            if isinstance(turn, dict) and _in_window(turn.get("timestamp"), start, end)
        ]

    active_roots = [(thread, turns_in_window(thread)) for thread in roots]
    active_roots = [(thread, turns) for thread, turns in active_roots if turns]
    active_children = sum(bool(turns_in_window(thread)) for thread in children)
    new_roots = [thread for thread in roots if _in_window(thread.get("created_at"), start, end)]

    turn_values: list[int] = []
    message_values: list[int] = []
    activity_timestamps: list[Any] = []
    tool_calls: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    message_roles: Counter[str] = Counter()
    projects: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    span_values: list[int] = []
    for thread, turns in active_roots:
        turn_values.append(len(turns))
        project = Path(str(thread.get("cwd") or "")).name or "unknown"
        projects[project] += 1
        sources[str(thread.get("source") or "unknown")] += 1
        all_instants = []
        for turn in turns:
            try:
                all_instants.append(_timestamp(turn.get("timestamp")))
            except (TypeError, ValueError, OverflowError):
                continue
        if all_instants:
            span_values.append(int((max(all_instants) - min(all_instants)).total_seconds()))
        messages = 0
        for turn in turns:
            activity_timestamps.append(turn.get("timestamp"))
            if turn.get("status"):
                status_counts[str(turn["status"])] += 1
            for item in turn.get("items", []):
                if not isinstance(item, dict):
                    continue
                if item.get("type") in {"user_message", "assistant_message"}:
                    messages += 1
                    message_roles[str(item["type"])] += 1
                elif item.get("type") in {"tool_call", "function_call"}:
                    tool_calls[str(item.get("name") or "unknown")] += 1
        message_values.append(messages)

    current = collection_time is None or end == collection_time.astimezone(UTC)
    token_totals: dict[str, int | None] = dict.fromkeys(TOKEN_FIELDS)
    coverage = {field: _coverage(0, len(new_roots)) for field in TOKEN_FIELDS}
    per_conversation: list[int] = []
    models: Counter[str] = Counter()
    reasoning: Counter[str] = Counter()
    if current:
        available = {field: 0 for field in TOKEN_FIELDS}
        sums = {field: 0 for field in TOKEN_FIELDS}
        for thread in new_roots:
            groups = _latest_usage_groups(thread)
            per_thread: dict[str, int | None] = {}
            for output_field, input_field in TOKEN_FIELDS.items():
                values = [group.get(input_field) for group in groups]
                valid = [value for value in values if isinstance(value, (int, float))]
                per_thread[output_field] = (
                    int(sum(valid)) if groups and len(valid) == len(groups) else None
                )
                if per_thread[output_field] is not None:
                    available[output_field] += 1
                    sums[output_field] += int(per_thread[output_field])
            if per_thread["total_tokens"] is not None:
                per_conversation.append(int(per_thread["total_tokens"]))
            for group in groups:
                if group.get("model"):
                    models[str(group["model"])] += 1
                if group.get("reasoningEffort"):
                    reasoning[str(group["reasoningEffort"])] += 1
        coverage = {field: _coverage(available[field], len(new_roots)) for field in TOKEN_FIELDS}
        token_totals = {field: sums[field] if available[field] else None for field in TOKEN_FIELDS}

    collection_iso = collection_time.astimezone(UTC).isoformat() if collection_time else None
    return {
        "contract_version": CONTRACT_VERSION,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": timezone,
            "end_exclusive": True,
        },
        "conversations": {
            "active": len(active_roots),
            "new": len(new_roots),
            "subagents_active": active_children,
        },
        "totals": {"turns": sum(turn_values), "messages": sum(message_values)},
        "turns_per_conversation": {"values": turn_values, **describe_distribution(turn_values)},
        "messages_per_conversation": {
            "values": message_values,
            **describe_distribution(message_values),
        },
        "activity": summarize_activity(activity_timestamps, timezone=timezone),
        "calendar": _calendar_distribution(activity_timestamps, timezone),
        "message_roles": dict(message_roles.items()),
        "conversation_spans_seconds": {
            "values": span_values,
            **describe_distribution(span_values),
        },
        "projects": dict(projects.most_common()),
        "sources": dict(sources.most_common()),
        "long_tail": {
            "top_10_percent_turn_share": _top_decile_share(turn_values),
            "top_10_percent_message_share": _top_decile_share(message_values),
        },
        "tools": dict(tool_calls.most_common()),
        "turn_statuses": dict(status_counts.most_common()),
        "tokens": {
            "totals": token_totals,
            "per_conversation": {
                "values": per_conversation,
                **_optional_distribution(per_conversation),
            },
            "cohort": "new_root_conversations",
            "window_status": (
                "current_cumulative" if current else "unavailable_historical_cumulative_only"
            ),
            "collection_time": collection_iso,
            "coverage": coverage,
            "models": dict(models.most_common()),
            "reasoning_efforts": dict(reasoning.most_common()),
            "top_10_percent_share": _top_decile_share(per_conversation),
        },
    }


def _replace_secrets(text: str, home: Path) -> str:
    home_text = str(home)
    if home_text and home_text != "/":
        text = text.replace(home_text, "~")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def redact_data(value: Any, *, home: Path | None = None) -> Any:
    """Recursively copy and redact paths, secret values, and inline credentials."""
    home = home or Path.home()

    def redact(item: Any, key: str | None = None) -> Any:
        if key and SENSITIVE_KEYS.search(key):
            return "[REDACTED]"
        if isinstance(item, dict):
            return {str(k): redact(v, str(k)) for k, v in item.items()}
        if isinstance(item, list):
            return [redact(entry) for entry in item]
        if isinstance(item, tuple):
            return [redact(entry) for entry in item]
        if isinstance(item, str):
            return _replace_secrets(item, home)
        return copy.deepcopy(item)

    return redact(value)


def _source_kind(source: Any) -> str:
    if isinstance(source, str):
        if source in SOURCE_KINDS:
            return source
        aliases = {"review": "subAgentReview", "compact": "subAgentCompact"}
        return aliases.get(source, "unknown")
    if not isinstance(source, dict):
        return "unknown"
    subagent = source.get("subAgent")
    if isinstance(subagent, str):
        return {
            "review": "subAgentReview",
            "compact": "subAgentCompact",
            "thread_spawn": "subAgentThreadSpawn",
        }.get(subagent, "subAgentOther")
    if isinstance(subagent, dict):
        keys = {str(key).replace("-", "_") for key in subagent}
        if "thread_spawn" in keys or "threadSpawn" in subagent:
            return "subAgentThreadSpawn"
        if "review" in keys:
            return "subAgentReview"
        if "compact" in keys:
            return "subAgentCompact"
        return "subAgentOther"
    return "unknown"


def _parent_id(thread: dict[str, Any]) -> Any:
    direct = thread.get("parentThreadId") or thread.get("parent_thread_id")
    if direct:
        return direct
    subagent = (
        thread.get("source", {}).get("subAgent") if isinstance(thread.get("source"), dict) else None
    )
    if isinstance(subagent, dict):
        spawn = subagent.get("thread_spawn") or subagent.get("threadSpawn")
        if isinstance(spawn, dict):
            return spawn.get("parent_thread_id") or spawn.get("parentThreadId")
    return None


def _is_subagent(thread: dict[str, Any]) -> bool:
    explicit = thread.get("is_subagent")
    if explicit is True or _parent_id(thread):
        return True
    return _source_kind(thread.get("source")).startswith("subAgent")


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [entry.get("text", "") for entry in content if isinstance(entry, dict)]
        return "\n".join(text for text in texts if text)
    return ""


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = item.get("type")
    known = {
        "userMessage": "user_message",
        "agentMessage": "assistant_message",
        "user_message": "user_message",
        "assistant_message": "assistant_message",
        "functionCall": "tool_call",
        "toolCall": "tool_call",
        "function_call": "tool_call",
        "tool_call": "tool_call",
    }
    tool_names = {
        "commandExecution": "shell",
        "fileChange": "file_change",
        "collabAgentToolCall": "subagent",
        "subAgentActivity": "subagent_activity",
        "webSearch": "web_search",
        "imageView": "image_view",
        "sleep": "wait",
        "imageGeneration": "image_generation",
        "enteredReviewMode": "review",
        "exitedReviewMode": "review",
        "contextCompaction": "context_compaction",
    }
    if kind in tool_names:
        return {"type": "tool_call", "name": tool_names[kind]}
    if kind == "mcpToolCall":
        server = str(item.get("server") or "mcp")
        tool = str(item.get("tool") or "unknown")
        return {"type": "tool_call", "name": f"{server}/{tool}"}
    if kind == "dynamicToolCall":
        return {"type": "tool_call", "name": str(item.get("tool") or "dynamic")}
    normalized_kind = known.get(str(kind), str(kind or "unknown"))
    result: dict[str, Any] = {"type": normalized_kind}
    if normalized_kind in {"user_message", "assistant_message"}:
        result["text"] = str(item.get("text") or _text_content(item.get("content")))
    elif normalized_kind in {"tool_call", "function_call"}:
        result["name"] = str(item.get("name") or item.get("tool") or "unknown")
    else:
        result["original_type"] = str(kind or "unknown")
        if "text" in item or "content" in item:
            result["text"] = str(item.get("text") or _text_content(item.get("content")))
    return result


def _normalize_thread(
    summary: dict[str, Any], detail: dict[str, Any], usage: Any
) -> dict[str, Any]:
    thread = detail.get("thread", detail) if isinstance(detail, dict) else {}
    raw_turns = thread.get("turns") or []
    turns = []
    for raw in raw_turns:
        if not isinstance(raw, dict):
            continue
        timestamp = raw.get("startedAt") or raw.get("createdAt") or raw.get("timestamp")
        turns.append(
            {
                "id": raw.get("id"),
                "timestamp": timestamp,
                "status": raw.get("status"),
                "items_view": raw.get("itemsView"),
                "items": [
                    _normalize_item(item)
                    for item in (raw.get("items") or [])
                    if isinstance(item, dict)
                ],
            }
        )
    usage_value = usage.get("threadUsage") if isinstance(usage, dict) else None
    return {
        "id": summary.get("id") or thread.get("id"),
        "created_at": summary.get("createdAt") or thread.get("createdAt"),
        "parent_thread_id": _parent_id(summary) or _parent_id(thread),
        "is_subagent": _is_subagent(summary) or _is_subagent(thread),
        "source": _source_kind(summary.get("source") or thread.get("source")),
        "cwd": summary.get("cwd") or thread.get("cwd"),
        "title": summary.get("name") or summary.get("title") or thread.get("name"),
        "turns": turns,
        "usage_snapshots": [usage_value] if isinstance(usage_value, dict) else [],
    }


class AppServerTransport:
    """Minimal newline-delimited JSON-RPC transport for ``codex app-server``."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or [shutil.which("codex") or "codex", "app-server"]
        self.process: subprocess.Popen[str] | None = None
        self.request_id = 0

    def __enter__(self) -> AppServerTransport:
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return self

    def __exit__(self, *_: object) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)

    def _send(self, payload: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("app-server transport is not running")
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.request_id += 1
        request_id = self.request_id
        self._send({"id": request_id, "method": method, "params": params})
        if not self.process or not self.process.stdout:
            raise RuntimeError("app-server transport is not running")
        while line := self.process.stdout.readline():
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get("id") != request_id:
                continue
            if "error" in response:
                error = response["error"]
                code = error.get("code") if isinstance(error, dict) else None
                suffix = f" (code {code})" if isinstance(code, (int, str)) else ""
                raise RuntimeError(f"app-server {method} failed{suffix}")
            result = response.get("result")
            return result if isinstance(result, dict) else {}
        code = self.process.poll()
        raise RuntimeError(
            f"app-server closed while handling {method}"
            + (f" (exit {code})" if code is not None else "")
        )

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"method": method, "params": params})


def _thread_may_intersect(
    summary: dict[str, Any], start: datetime | None, end: datetime | None
) -> bool:
    if start is None or end is None:
        return True
    created_raw = summary.get("createdAt")
    try:
        created = _timestamp(created_raw)
    except (TypeError, ValueError, OverflowError):
        created = None
    if created is not None and created >= end:
        return False
    activity = []
    for field in ("updatedAt", "recencyAt"):
        try:
            activity.append(_timestamp(summary.get(field)))
        except (TypeError, ValueError, OverflowError):
            continue
    return not (activity and max(activity) < start)


def _turn_metadata_pages(
    transport: Any, thread_id: str, start: datetime, end: datetime
) -> tuple[list[dict[str, Any]], int]:
    turns: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()
    page_count = 0
    while True:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "limit": 100,
            "sortDirection": "asc",
            "itemsView": "notLoaded",
        }
        if cursor is not None:
            params["cursor"] = cursor
        try:
            page = transport.request("thread/turns/list", params)
        except RuntimeError as error:
            raise RuntimeError(
                "thread/turns/list unavailable; refusing to read full thread history"
            ) from error
        page_count += 1
        for turn in page.get("data") or []:
            if not isinstance(turn, dict) or not turn.get("id"):
                raise RuntimeError("thread/turns/list returned incomplete turn metadata")
            view = str(turn.get("itemsView") or "missing")
            if view != "notLoaded":
                raise RuntimeError(f"thread/turns/list returned unexpected itemsView {view!r}")
            if turn.get("items") != []:
                raise RuntimeError("thread/turns/list returned non-empty turn metadata items")
            try:
                in_window = _in_window(turn["startedAt"], start, end)
                _timestamp(turn["startedAt"])
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                raise RuntimeError("thread/turns/list returned incomplete turn metadata") from error
            if in_window:
                turns.append(turn)
        next_cursor = page.get("nextCursor")
        if not next_cursor:
            return turns, page_count
        if next_cursor in seen:
            raise RuntimeError("app-server returned a repeated turn pagination cursor")
        seen.add(next_cursor)
        cursor = str(next_cursor)


def _item_pages(transport: Any, thread_id: str, turn_id: str) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()
    page_count = 0
    while True:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "turnId": turn_id,
            "limit": 100,
            "sortDirection": "asc",
        }
        if cursor is not None:
            params["cursor"] = cursor
        try:
            page = transport.request("thread/items/list", params)
        except RuntimeError as error:
            raise RuntimeError(
                "thread/items/list unavailable; cannot collect complete window history"
            ) from error
        page_count += 1
        for entry in page.get("data") or []:
            if (
                not isinstance(entry, dict)
                or entry.get("turnId") != turn_id
                or not isinstance(entry.get("item"), dict)
            ):
                raise RuntimeError("thread/items/list returned incomplete or mismatched items")
            items.append(entry["item"])
        next_cursor = page.get("nextCursor")
        if not next_cursor:
            return items, page_count
        if next_cursor in seen:
            raise RuntimeError("app-server returned a repeated item pagination cursor")
        seen.add(next_cursor)
        cursor = str(next_cursor)


def _hydrate_window_turns(
    transport: Any, thread_id: str, start: datetime, end: datetime
) -> tuple[list[dict[str, Any]], int, int]:
    turns, turn_pages = _turn_metadata_pages(transport, thread_id, start, end)
    item_pages = 0
    hydrated = []
    for turn in turns:
        items, pages = _item_pages(transport, thread_id, str(turn["id"]))
        item_pages += pages
        hydrated.append({**turn, "itemsView": "full", "items": items})
    return hydrated, turn_pages, item_pages


def collect_from_app_server(
    transport: Any,
    *,
    collection_time: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Collect only turns and items inside a required half-open time window."""
    if start is None or end is None:
        raise ValueError("start and end are required for narrow history collection")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if start >= end:
        raise ValueError("start must be earlier than end")
    collection_time = collection_time or datetime.now(UTC)
    transport.request(
        "initialize",
        {
            "clientInfo": {
                "name": "codex-insights",
                "title": "Codex Insights",
                "version": "1",
            },
            "capabilities": {"experimentalApi": True},
        },
    )
    transport.notify("initialized", {})
    summaries: list[dict[str, Any]] = []
    for archived in (False, True):
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params: dict[str, Any] = {
                "archived": archived,
                "sourceKinds": SOURCE_KINDS,
                "limit": 100,
            }
            if cursor is not None:
                params["cursor"] = cursor
            page = transport.request("thread/list", params)
            summaries.extend(item for item in (page.get("data") or []) if isinstance(item, dict))
            next_cursor = page.get("nextCursor")
            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise RuntimeError("app-server returned a repeated pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = str(next_cursor)

    candidates = [summary for summary in summaries if _thread_may_intersect(summary, start, end)]
    threads = []
    usage_available = 0
    turn_page_count = 0
    item_page_count = 0
    root_threads = 0
    root_window_turns = 0
    subagent_threads = 0
    subagent_window_turns = 0
    for summary in candidates:
        thread_id = summary.get("id")
        if not thread_id:
            continue
        if _is_subagent(summary):
            subagent_threads += 1
            try:
                raw_turns, turn_pages = _turn_metadata_pages(transport, str(thread_id), start, end)
            except RuntimeError as error:
                raise RuntimeError(f"failed to read subagent turn metadata: {error}") from error
            item_pages = 0
            subagent_window_turns += len(raw_turns)
        else:
            root_threads += 1
            try:
                raw_turns, turn_pages, item_pages = _hydrate_window_turns(
                    transport, str(thread_id), start, end
                )
            except RuntimeError as error:
                raise RuntimeError(f"failed to read complete root items: {error}") from error
            root_window_turns += len(raw_turns)
        turn_page_count += turn_pages
        item_page_count += item_pages
        detail = {"thread": {**summary, "turns": raw_turns}}
        try:
            usage = transport.request("account/usage/read", {"threadId": thread_id})
        except RuntimeError:
            usage = {"threadUsage": None}
        if isinstance(usage, dict) and isinstance(usage.get("threadUsage"), dict):
            usage_available += 1
        threads.append(_normalize_thread(summary, detail, usage))
    preserved_items: Counter[str] = Counter()
    for thread in threads:
        for turn in thread["turns"]:
            for item in turn["items"]:
                if item.get("original_type"):
                    preserved_items[str(item["original_type"])] += 1
    return {
        "contract_version": CONTRACT_VERSION,
        "collection_time": collection_time.astimezone(UTC).isoformat(),
        "threads": threads,
        "coverage": {
            "thread_usage": _coverage(usage_available, len(threads)),
            "enumerated_threads": len(summaries),
            "candidate_threads": len(candidates),
            "read_threads": len(threads),
            "unknown_sources": sum(thread["source"] == "unknown" for thread in threads),
            "preserved_non_message_item_types": dict(preserved_items.most_common()),
            "turn_hydration": {
                "mode": "root_window_items_subagent_metadata_only",
                "root_items": {
                    "eligible_threads": root_threads,
                    "full_threads": root_threads,
                    "window_turns": root_window_turns,
                    "item_pages": item_page_count,
                },
                "subagent_metadata": {
                    "threads": subagent_threads,
                    "window_turns": subagent_window_turns,
                },
                "turn_pages": turn_page_count,
            },
        },
    }


@contextlib.contextmanager
def temporary_history_directory(parent: Path | None = None) -> Iterator[Path]:
    """Create a private, automatically removed directory bearing a safety sentinel."""
    directory = Path(tempfile.mkdtemp(prefix="codex-insights-", dir=parent))
    os.chmod(directory, 0o700)
    sentinel = directory / ".codex-insights-temporary"
    sentinel.write_text(str(CONTRACT_VERSION), encoding="utf-8")
    os.chmod(sentinel, 0o600)
    try:
        yield directory
    finally:
        if sentinel.is_file() and directory.name.startswith("codex-insights-"):
            shutil.rmtree(directory)


def next_report_path(
    output_directory: Path,
    *,
    start_date: str,
    end_date: str,
    now: datetime | None = None,
) -> Path:
    base = output_directory / f"Codex Insights {start_date} to {end_date}.html"
    if not base.exists():
        return base
    now = now or datetime.now()
    suffix = now.strftime("%H%M%S")
    candidate = output_directory / f"Codex Insights {start_date} to {end_date} {suffix}.html"
    sequence = 2
    while candidate.exists():
        candidate = output_directory / (
            f"Codex Insights {start_date} to {end_date} {suffix}-{sequence}.html"
        )
        sequence += 1
    return candidate


def _analysis_html(analysis: str) -> str:
    """Render a deliberately small, safe Markdown subset without links or raw HTML."""
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{'<br>'.join(paragraph)}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            blocks.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items.clear()

    for raw_line in analysis.splitlines():
        line = html.escape(raw_line.strip())
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1)) + 1
            blocks.append(f"<h{level}>{heading.group(2)}</h{level}>")
        elif bullet:
            flush_paragraph()
            list_items.append(bullet.group(1))
        elif not line:
            flush_paragraph()
            flush_list()
        else:
            flush_list()
            paragraph.append(line)
    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def render_html(*, metrics: dict[str, Any], analysis: str, title: str) -> str:
    escaped_title = html.escape(title)
    metrics_json = html.escape(json.dumps(metrics, ensure_ascii=False, indent=2))
    conversations = metrics.get("conversations", {})
    totals = metrics.get("totals", {})
    turns = metrics.get("turns_per_conversation", {})
    token_metrics = metrics.get("tokens", {})
    tokens = token_metrics.get("per_conversation", {})
    token_coverage = token_metrics.get("coverage", {}).get("total_tokens", {})
    token_available = token_coverage.get("available", 0)
    token_eligible = token_coverage.get("eligible", 0)
    historical_note = (
        "；历史窗口不可用"
        if token_metrics.get("window_status") == "unavailable_historical_cumulative_only"
        else ""
    )
    token_label = (
        f"平均 token（本期新建根对话，{token_available}/{token_eligible} 有数据{historical_note}）"
    )
    token_mean = tokens.get("mean")

    def display(value: Any) -> str:
        return "未知" if value is None else str(value)

    cards = [
        ("活跃对话", conversations.get("active", "未知")),
        ("新对话", conversations.get("new", "未知")),
        ("平均回合数", turns.get("mean", "未知")),
        (token_label, display(token_mean)),
        ("总回合数", totals.get("turns", "未知")),
        ("活跃天数", metrics.get("calendar", {}).get("active_days", "未知")),
    ]
    card_html = "".join(
        '<article class="card">'
        f"<span>{html.escape(str(label))}</span>"
        f"<strong>{html.escape(str(value))}</strong>"
        "</article>"
        for label, value in cards
    )

    def bars(values: dict[str, Any]) -> str:
        numeric = [value for value in values.values() if isinstance(value, (int, float))]
        maximum = max(numeric, default=0)
        rows = []
        for label, value in values.items():
            if not isinstance(value, (int, float)):
                continue
            width = 0 if not maximum else round(value / maximum * 100, 2)
            rows.append(
                '<div class="bar-row">'
                f"<span>{html.escape(str(label))}</span>"
                f'<i style="width:{width}%"></i><strong>{html.escape(str(value))}</strong>'
                "</div>"
            )
        return "".join(rows) or '<p class="muted">本期没有可用数据。</p>'

    def dimension(title: str, values: dict[str, Any], *, percent: bool = False) -> str:
        if not values:
            return ""
        rows = []
        entries = list(values.items())
        for label, value in entries[:10]:
            shown = (
                f"{round(value * 100, 1):g}%"
                if percent and isinstance(value, (int, float))
                else display(value)
            )
            rows.append(
                f"<div><dt>{html.escape(str(label))}</dt><dd>{html.escape(shown)}</dd></div>"
            )
        if len(entries) > 10:
            rows.append(f"<div><dt>其余</dt><dd>{len(entries) - 10} 项</dd></div>")
        return (
            f'<article class="dimension"><h3>{html.escape(title)}</h3>'
            f"<dl>{''.join(rows)}</dl></article>"
        )

    def section(title: str, content: str) -> str:
        if not content:
            return ""
        return f'<section><h2>{html.escape(title)}</h2><div class="grid">{content}</div></section>'

    activity = metrics.get("activity", {})
    calendar = metrics.get("calendar", {})
    calendar_html = ""
    if calendar.get("by_date"):
        calendar_html += (
            f'<article class="dimension"><h3>每日活动</h3>{bars(calendar["by_date"])}</article>'
        )
    if calendar.get("by_weekday"):
        calendar_html += (
            f'<article class="dimension"><h3>星期分布</h3>{bars(calendar["by_weekday"])}</article>'
        )
    collaboration_html = "".join(
        (
            dimension("项目", metrics.get("projects", {})),
            dimension("工具", metrics.get("tools", {})),
            dimension("来源", metrics.get("sources", {})),
        )
    )
    model_html = "".join(
        (
            dimension("模型", token_metrics.get("models", {})),
            dimension("推理强度", token_metrics.get("reasoning_efforts", {})),
        )
    )
    long_tail = {
        "回合": metrics.get("long_tail", {}).get("top_10_percent_turn_share"),
        "消息": metrics.get("long_tail", {}).get("top_10_percent_message_share"),
    }
    token_share = token_metrics.get("top_10_percent_share")
    if token_share is not None:
        token_long_tail_label = (
            f"token（本期新建根对话，{token_available}/{token_eligible} 有数据）"
        )
        coverage_ratio = token_coverage.get("ratio")
        token_coverage_complete = (
            coverage_ratio >= 1
            if isinstance(coverage_ratio, (int, float))
            else token_eligible > 0 and token_available == token_eligible
        )
        long_tail[token_long_tail_label] = token_share if token_coverage_complete else "覆盖不足"
    long_tail = {label: value for label, value in long_tail.items() if value is not None}
    long_tail_html = dimension("长尾：前 10% 对话占比", long_tail, percent=True)
    distributions = [
        ("每个对话的回合数", metrics.get("turns_per_conversation", {})),
        ("每个对话的消息数", metrics.get("messages_per_conversation", {})),
        ("每个对话的 token", tokens),
    ]
    distribution_rows = "".join(
        "<tr>"
        f"<th>{html.escape(label)}</th>"
        + "".join(
            f"<td>{html.escape(display(values.get(field)))}</td>"
            for field in ("mean", "median", "p25", "p75", "p90")
        )
        + "</tr>"
        for label, values in distributions
    )
    return f"""<!doctype html>
<html lang="zh-Hans"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escaped_title}</title>
<style>
:root {{
  color-scheme:light dark; --paper:#f6f2e9; --ink:#27231e;
  --muted:#726b61; --accent:#a2472f;
}}
* {{ box-sizing:border-box }}
body {{
  margin:0; background:var(--paper); color:var(--ink);
  font:17px/1.7 ui-serif,Georgia,serif;
}}
main {{ max-width:900px; margin:auto; padding:7vw 5vw }}
h1 {{ font-size:clamp(2.4rem,7vw,5rem); line-height:1; letter-spacing:-.04em }}
.deck {{ color:var(--muted); max-width:42rem }}
.cards {{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:1rem; margin:3rem 0;
}}
.card {{ border-top:3px solid var(--accent); padding:1rem 0 }}
.card span {{
  display:block; color:var(--muted); font:13px/1.3 ui-sans-serif,system-ui;
}}
.card strong {{ font-size:2rem }}
section {{ margin:4rem 0 }}
h2,h3,h4 {{ line-height:1.2 }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:3rem }}
.dimension h3 {{ margin-top:0 }}
.dimension dl {{ margin:0 }}
.dimension dl div {{ display:flex; justify-content:space-between; gap:1rem; padding:.35rem 0 }}
.dimension dt {{ overflow-wrap:anywhere }} .dimension dd {{ margin:0; font-weight:700 }}
.bar-row {{ display:grid; grid-template-columns:5rem 1fr 3rem; gap:.7rem; align-items:center }}
.bar-row span,.bar-row strong {{ font:12px/1.4 ui-sans-serif,system-ui }}
.bar-row i {{ display:block; height:.6rem; background:var(--accent); min-width:2px }}
table {{ width:100%; border-collapse:collapse }}
th,td {{ padding:.7rem; border-bottom:1px solid var(--muted); text-align:right }}
th:first-child {{ text-align:left }} .muted,details {{ color:var(--muted) }}
pre {{
  overflow:auto; white-space:pre-wrap; font:12px/1.45 ui-monospace,monospace;
}}
@media (prefers-color-scheme:dark) {{
  :root {{ --paper:#1d1b18; --ink:#eee8dc; --muted:#aaa196; --accent:#ef8c6f }}
}}
</style></head><body><main>
<p class="deck">一份保存在本地、回看近期人机协作的私人复盘。</p>
<h1>{escaped_title}</h1><div class="cards">{card_html}</div>
<section><h2>数据分布</h2>
<table><thead><tr><th>指标</th><th>平均</th><th>中位数</th><th>P25</th><th>P75</th><th>P90</th></tr></thead>
<tbody>{distribution_rows}</tbody></table></section>
<section class="grid"><div><h2>一天中的活动</h2>{bars(activity.get("by_hour", {}))}</div>
<div><h2>工作日与周末</h2>{bars(activity.get("weekday_weekend", {}))}
<h3>时段</h3>{bars(activity.get("day_parts", {}))}</div></section>
{section("日历分布", calendar_html)}
{section("协作分布", collaboration_html)}
{section("模型使用", model_html)}
{section("长尾分布", long_tail_html)}
<section class="analysis">{_analysis_html(analysis)}</section>
<details><summary>指标原始值与覆盖率</summary><pre>{metrics_json}</pre></details>
</main></body></html>"""


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        raise


def write_work_sentinel(directory: Path, *, owned: bool) -> None:
    sentinel = directory / ".codex-insights-workdir"
    write_report(
        sentinel,
        json.dumps(
            {
                "contract_version": CONTRACT_VERSION,
                "directory": str(directory.resolve()),
                "owned": owned,
            }
        ),
    )


def cleanup_work_directory(directory: Path, *, metrics_path: Path | None = None) -> bool:
    """Remove only a collector-created directory protected by a matching sentinel."""
    directory = directory.expanduser().resolve()
    if not directory.exists():
        return False
    sentinel = directory / ".codex-insights-workdir"
    if metrics_path is not None and metrics_path.expanduser().resolve().parent != directory:
        raise RuntimeError("cleanup directory must contain the metrics file")
    if not sentinel.is_file() or sentinel.is_symlink():
        raise RuntimeError("refusing cleanup: work directory sentinel is missing")
    try:
        marker = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("refusing cleanup: invalid work directory sentinel") from error
    if (
        not isinstance(marker, dict)
        or marker.get("contract_version") != CONTRACT_VERSION
        or marker.get("directory") != str(directory)
        or not isinstance(marker.get("owned"), bool)
    ):
        raise RuntimeError("refusing cleanup: work directory sentinel does not match")
    if marker["owned"]:
        shutil.rmtree(directory)
    else:
        _clean_collection_artifacts(directory, owned=False)
    return True


def _clean_collection_artifacts(directory: Path, *, owned: bool) -> None:
    if owned:
        cleanup_work_directory(directory)
        return
    for name in ("metrics.json", "history.json", ".codex-insights-workdir"):
        path = directory / name
        if path.is_file() and not path.is_symlink():
            path.unlink()


def _parse_cli_time(value: str) -> datetime:
    try:
        return _timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"invalid date or timestamp: {value}") from error


def _parse_boundary(value: str | None, timezone: str) -> datetime | None:
    if value is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {timezone}") from error
        return datetime.fromisoformat(value).replace(tzinfo=zone).astimezone(UTC)
    return _parse_cli_time(value)


def _collect_command(args: argparse.Namespace) -> int:
    work_directory = args.work_dir.expanduser().resolve()
    owned = not work_directory.exists()
    work_directory.mkdir(parents=True, exist_ok=True)
    if any(work_directory.iterdir()):
        raise RuntimeError("work directory is not empty; use a fresh directory")
    if owned:
        os.chmod(work_directory, 0o700)
    write_work_sentinel(work_directory, owned=owned)
    try:
        collection_time = datetime.now(UTC)
        end = _parse_boundary(args.end, args.timezone) or collection_time
        start = _parse_boundary(args.start, args.timezone) or end - timedelta(days=7)
        with AppServerTransport() as transport:
            collection = collect_from_app_server(
                transport,
                collection_time=collection_time,
                start=start,
                end=end,
            )
        metrics = summarize_history(
            collection["threads"],
            start=start,
            end=end,
            timezone=args.timezone,
            collection_time=collection_time,
        )
        metrics["collection_coverage"] = collection["coverage"]
        history = {
            "contract_version": CONTRACT_VERSION,
            "window": metrics["window"],
            "collection_time": collection["collection_time"],
            "threads": collection["threads"],
        }
        outputs = {
            "metrics": work_directory / "metrics.json",
            "history": work_directory / "history.json",
        }
        for name, path in outputs.items():
            payload = metrics if name == "metrics" else redact_data(history)
            write_report(path, json.dumps(payload, ensure_ascii=False, indent=2))
        print(json.dumps({name: str(path.resolve()) for name, path in outputs.items()}))
        return 0
    except BaseException:
        _clean_collection_artifacts(work_directory, owned=owned)
        raise


def _render_command(args: argparse.Namespace) -> int:
    output: Path | None = None
    try:
        metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
        analysis = args.analysis.read_text(encoding="utf-8")
        output_directory = (args.output_dir or Path.home() / "Desktop").expanduser().resolve()
        output_directory.mkdir(parents=True, exist_ok=True)
        output = next_report_path(
            output_directory,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        title = f"Codex Insights · {args.start_date} to {args.end_date}"
        write_report(output, render_html(metrics=metrics, analysis=analysis, title=title))
    finally:
        if args.cleanup_work_dir:
            cleanup_work_directory(args.cleanup_work_dir, metrics_path=args.metrics)
    if output is None:
        raise RuntimeError("report output was not created")
    print(str(output.resolve()))
    return 0


def _cleanup_command(args: argparse.Namespace) -> int:
    removed = cleanup_work_directory(args.work_dir)
    print(json.dumps({"directory": str(args.work_dir.expanduser().resolve()), "removed": removed}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect", help="collect and normalize Codex history")
    collect.add_argument("--work-dir", type=Path, required=True)
    collect.add_argument("--start", help="inclusive ISO date or timestamp")
    collect.add_argument("--end", help="exclusive ISO date or timestamp")
    collect.add_argument("--timezone", default=os.environ.get("TZ", "UTC"))
    collect.set_defaults(handler=_collect_command)
    render = subparsers.add_parser("render", help="render metrics and analysis to HTML")
    render.add_argument("--metrics", type=Path, required=True)
    render.add_argument("--analysis", type=Path, required=True)
    render.add_argument("--start-date", required=True)
    render.add_argument("--end-date", required=True)
    render.add_argument("--output-dir", type=Path)
    render.add_argument(
        "--cleanup-work-dir",
        type=Path,
        help="remove the sentinel-protected collection directory after rendering",
    )
    render.set_defaults(handler=_render_command)
    cleanup = subparsers.add_parser("cleanup", help="remove a sentinel-protected work directory")
    cleanup.add_argument("--work-dir", type=Path, required=True)
    cleanup.set_defaults(handler=_cleanup_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"insights: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
