from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from codex_maintenance.workflow.collector import (
    HEALTH_NAME,
    INDEX_NAME,
    collect_event,
    parse_event,
    register_run,
    unregister_run,
)
from codex_maintenance.workflow.model import WorkflowError
from codex_maintenance.workflow.package import package_plugin
from codex_maintenance.workflow.store import WorkflowStore


def event(**extra: object) -> bytes:
    return json.dumps(
        {
            "hook_event_name": "SubagentStart",
            "session_id": "parent",
            "agent_id": "agent",
            "turn_id": "turn",
            "tool_input": "private prompt and command",
            "tool_response": "private response",
            **extra,
        }
    ).encode()


def test_collector_whitelists_fields_and_dispatches_same_session_runs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    stores = [WorkflowStore(tmp_path / f"run-{n}.db") for n in range(2)]
    runs = [store.start_run("parent") for store in stores]
    for store, run in zip(stores, runs, strict=True):
        register_run(data, store.path, run)
    assert collect_event(data, event(unexpected={"nested": "private"})) == 2
    for store, run in zip(stores, runs, strict=True):
        assert store.snapshot(run)["observations"] == 1
        with sqlite3.connect(store.path) as db:
            columns = [item[1] for item in db.execute("PRAGMA table_info(observations)")]
            values = str(db.execute("SELECT * FROM observations").fetchall())
        assert set(columns) == {
            "id",
            "schema_version",
            "source",
            "session_id",
            "kind",
            "agent_id",
            "turn_id",
            "tool_use_id",
            "received_at",
        }
        assert "private" not in values
    assert collect_event(data, event(session_id="other")) == 0
    assert collect_event(data, event(hook_event_name="FutureEvent")) == 0
    assert collect_event(data, b"{broken") == 0


def test_shared_database_receives_one_observation_for_two_runs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    store = WorkflowStore(tmp_path / "shared.db")
    first = store.start_run("parent")
    second = store.start_run("parent")
    register_run(data, store.path, first)
    register_run(data, store.path, second)

    assert collect_event(data, event()) == 1
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert store.snapshot(first)["observations"] == 1
    assert store.snapshot(second)["observations"] == 1


def test_registration_is_idempotent_but_conflicts_are_diagnosed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = WorkflowStore(tmp_path / "first.db")
    run = first.start_run("parent")
    register_run(data, first.path, run)
    register_run(data, first.path, run)
    other = WorkflowStore(tmp_path / "other.db")
    with sqlite3.connect(other.path) as db:
        db.execute("INSERT INTO runs(id,session_id,created_at) VALUES(?,?,?)", (run, "parent", 0))
    with pytest.raises(WorkflowError, match="different database"):
        register_run(data, other.path, run)
    unregister_run(data, run)
    assert collect_event(data, event()) == 0


def test_hook_fast_exit_and_nonblocking_failure(tmp_path: Path) -> None:
    data = tmp_path / "data"
    assert collect_event(data, event()) == 0
    assert not data.exists()
    store = WorkflowStore(tmp_path / "run.db")
    run = store.start_run("parent")
    register_run(data, store.path, run)
    # A locked index must not delay or fail the agent operation indefinitely.
    with sqlite3.connect(data / INDEX_NAME) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        assert collect_event(data, event()) == 0
    with sqlite3.connect(store.path) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        assert collect_event(data, event()) == 0
    diagnostics = (data / HEALTH_NAME).read_text()
    assert "index_read_failed" in diagnostics
    assert "run_write_failed" in diagnostics
    assert "private" not in diagnostics
    assert parse_event(event(agent_id=123)) is None
    assert parse_event(event(turn_id="")) is None
    assert parse_event(b"x" * (1024 * 1024 + 1)) is None


def test_read_only_database_failure_is_diagnostic_only(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    store = WorkflowStore(tmp_path / "run.db")
    register_run(data, store.path, store.start_run("parent"))

    def read_only(*_args, **_kwargs):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(WorkflowStore, "ingest_observation", read_only)
    assert collect_event(data, event()) == 0
    diagnostics = (data / HEALTH_NAME).read_text()
    assert "run_write_failed" in diagnostics
    assert "readonly database" not in diagnostics


def test_packaged_hook_works_without_checkout(tmp_path: Path) -> None:
    payload = package_plugin(tmp_path / "payload")
    store = WorkflowStore(tmp_path / "run.db")
    run = store.start_run("parent")
    data = tmp_path / "data"
    register_run(data, store.path, run)
    env = {"PATH": os.environ["PATH"], "PLUGIN_ROOT": str(payload), "PLUGIN_DATA": str(data)}
    result = subprocess.run(
        [sys.executable, str(payload / "hooks" / "collect.py")],
        input=event(),
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert store.snapshot(run)["observations"] == 1
    assert (payload / "lib" / "codex_maintenance" / "workflow" / "store.py").is_file()
    assert not any(path.is_symlink() for path in payload.rglob("*"))


def test_cli_registration_and_unregister(tmp_path: Path, capsys) -> None:
    from codex_maintenance.cli import main

    db = tmp_path / "run.db"
    data = tmp_path / "data"
    assert main(["workflow", "--db", str(db), "start", "--session-id", "parent"]) == 0
    run = json.loads(capsys.readouterr().out)
    assert main(["workflow", "--db", str(db), "register", run, "--plugin-data", str(data)]) == 0
    assert collect_event(data, event()) == 1
    assert main(["workflow", "--db", str(db), "unregister", run, "--plugin-data", str(data)]) == 0
    assert collect_event(data, event()) == 0
