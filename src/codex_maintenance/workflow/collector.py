"""Small, best-effort adapter between trusted Codex hooks and run databases."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from contextlib import suppress
from pathlib import Path

from codex_maintenance.workflow.model import OBSERVATIONS, Observation, WorkflowError
from codex_maintenance.workflow.store import WorkflowStore

INDEX_NAME = "active-runs.sqlite3"
HEALTH_NAME = "collector-health.jsonl"
MAX_EVENT_BYTES = 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 65536


def _index_path(plugin_data: Path) -> Path:
    return plugin_data / INDEX_NAME


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=0.25)
    db.execute("PRAGMA busy_timeout=250")
    return db


def _diagnose(plugin_data: Path, code: str) -> None:
    """Keep a small local failure trail without event fields or paths."""
    path = plugin_data / HEALTH_NAME
    entry = json.dumps({"at": time.time(), "code": code}) + "\n"
    with suppress(OSError):
        if path.is_file() and path.stat().st_size + len(entry.encode()) > MAX_DIAGNOSTIC_BYTES:
            path.replace(plugin_data / f"{HEALTH_NAME}.1")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(entry)


def register_run(plugin_data: Path, database: Path, run_id: str) -> None:
    """Register one active run without assuming one run per parent session."""
    database = database.resolve(strict=True)
    snapshot = WorkflowStore(database).snapshot(run_id)
    if snapshot["state"] != "active":
        raise WorkflowError("only active runs can be registered")
    plugin_data.mkdir(parents=True, exist_ok=True)
    with _connect(_index_path(plugin_data)) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS active_runs (
                run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, database_path TEXT NOT NULL
            )"""
        )
        existing = db.execute(
            "SELECT session_id,database_path FROM active_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        candidate = (snapshot["session_id"], str(database))
        if existing and existing != candidate:
            raise WorkflowError("run_id is already registered with a different database")
        db.execute(
            "INSERT OR IGNORE INTO active_runs(run_id,session_id,database_path) VALUES(?,?,?)",
            (run_id, *candidate),
        )


def unregister_run(plugin_data: Path, run_id: str) -> None:
    path = _index_path(plugin_data)
    if not path.is_file():
        return
    with _connect(path) as db:
        db.execute("DELETE FROM active_runs WHERE run_id=?", (run_id,))


def parse_event(raw: bytes) -> Observation | None:
    """Discard all input except documented lifecycle IDs and event name."""
    if len(raw) > MAX_EVENT_BYTES:
        return None
    try:
        event = json.loads(raw)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(event, dict):
        return None
    kind = event.get("hook_event_name")
    session_id = event.get("session_id")
    agent_id = event.get("agent_id", "")
    turn_id = event.get("turn_id", "")
    tool_use_id = event.get("tool_use_id")
    if kind not in OBSERVATIONS or not isinstance(session_id, str):
        return None
    if not all(isinstance(value, str) for value in (agent_id, turn_id)):
        return None
    if tool_use_id is not None and not isinstance(tool_use_id, str):
        tool_use_id = None
    observation = Observation(session_id, kind, agent_id, turn_id, tool_use_id=tool_use_id)
    try:
        observation.validate()
    except WorkflowError:
        return None
    return observation


def collect_event(plugin_data: Path, raw: bytes) -> int:
    """Return successful writes; callers may ignore this best-effort result."""
    index = _index_path(plugin_data)
    if not index.is_file():
        return 0
    observation = parse_event(raw)
    if observation is None:
        return 0
    try:
        with _connect(index) as db:
            rows = db.execute(
                "SELECT DISTINCT database_path FROM active_runs WHERE session_id=?",
                (observation.session_id,),
            ).fetchall()
    except (OSError, sqlite3.Error):
        _diagnose(plugin_data, "index_read_failed")
        return 0
    written = 0
    for (database_path,) in rows:
        path = Path(database_path)
        if not path.is_file():
            continue
        try:
            store = WorkflowStore(path, timeout=0.25)
            written += bool(
                store.ingest_observation(
                    observation.session_id,
                    observation.kind,
                    observation.agent_id,
                    observation.turn_id,
                    source="hook",
                    tool_use_id=observation.tool_use_id,
                )
            )
        except (OSError, sqlite3.Error, WorkflowError):
            _diagnose(plugin_data, "run_write_failed")
            continue
    return written


def hook_main() -> int:
    """Hooks must never block an agent operation or emit control JSON."""
    data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data or not _index_path(Path(data)).is_file():
        return 0
    # No event input, prompt, command, or tool result may reach hook output.
    try:
        collect_event(Path(data), sys.stdin.buffer.read(MAX_EVENT_BYTES + 1))
    except Exception:
        _diagnose(Path(data), "collector_failed")
    return 0
