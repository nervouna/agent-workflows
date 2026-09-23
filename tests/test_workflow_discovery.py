from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from codex_maintenance.cli import main
from codex_maintenance.workflow.collector import collect_event
from codex_maintenance.workflow.discovery import (
    STARTUP_DIAGNOSTIC_NAME,
    _marker,
    discover_plugin_data,
    publish_plugin_data,
    record_startup,
)
from codex_maintenance.workflow.model import WorkflowError
from codex_maintenance.workflow.package import package_plugin
from codex_maintenance.workflow.store import WorkflowStore

SESSION = "session-12345678"


def test_publish_creates_private_absent_host_data_directory(tmp_path: Path) -> None:
    data = tmp_path / "plugin-data"
    root = tmp_path / "handoff"
    publish_plugin_data(SESSION, data, root=root)
    assert data.is_dir()
    assert data.stat().st_mode & 0o777 == 0o700
    assert discover_plugin_data(SESSION, root=root) == data


def test_publish_rejects_unsafe_host_data_location(tmp_path: Path) -> None:
    root = tmp_path / "handoff"
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked-data"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkflowError, match="not private"):
        publish_plugin_data(SESSION, link, root=root)
    with pytest.raises(WorkflowError, match="unavailable"):
        publish_plugin_data(SESSION, tmp_path / "missing-parent" / "data", root=root)
    assert not root.exists()


def test_startup_diagnostic_is_fixed_private_and_bounded(tmp_path: Path) -> None:
    root = tmp_path / "handoff"
    record_startup("invoked", root=root)
    record_startup("private prompt", root=root)
    path = root / STARTUP_DIAGNOSTIC_NAME
    assert root.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    assert [row["code"] for row in map(json.loads, path.read_text().splitlines())] == ["invoked"]
    for _ in range(1200):
        record_startup("marker_published", root=root)
    assert path.stat().st_size <= 65536


def test_private_handoff_rejects_malformed_stale_and_wrong_identity(tmp_path: Path) -> None:
    root = tmp_path / "handoff"
    data = tmp_path / "plugin-data"
    data.mkdir()
    publish_plugin_data(SESSION, data, root=root)
    marker = _marker(root, SESSION)
    assert root.stat().st_mode & 0o777 == 0o700
    assert marker.stat().st_mode & 0o777 == 0o600
    assert discover_plugin_data(SESSION, root=root) == data
    with pytest.raises(WorkflowError, match="invalid session ID"):
        discover_plugin_data("../bad", root=root)
    record = json.loads(marker.read_text())
    record["session_id"] = "different-session"
    marker.write_text(json.dumps(record))
    with pytest.raises(WorkflowError, match="identity mismatch"):
        discover_plugin_data(SESSION, root=root)
    record["session_id"] = SESSION
    record["at"] = time.time() - 7200
    marker.write_text(json.dumps(record))
    with pytest.raises(WorkflowError, match="stale"):
        discover_plugin_data(SESSION, root=root)
    marker.chmod(0o644)
    with pytest.raises(WorkflowError, match="not private"):
        discover_plugin_data(SESSION, root=root)
    marker.chmod(0o600)
    root.chmod(0o755)
    with pytest.raises(WorkflowError, match="not private"):
        discover_plugin_data(SESSION, root=root)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS shared temporary handoff")
def test_packaged_session_start_discovers_then_registers_without_sensitive_fields(
    tmp_path: Path, capsys
) -> None:
    payload = package_plugin(tmp_path / "payload")
    data = tmp_path / "plugin-data"
    hook_tmp = tmp_path / "hook-tmp"
    cli_tmp = tmp_path / "cli-tmp"
    hook_tmp.mkdir()
    cli_tmp.mkdir()
    session = f"session-{uuid.uuid4().hex}"
    root = Path("/private/tmp") / f"codex-workflow-discovery-{os.getuid()}"
    marker = _marker(root, session)
    diagnostic = root / STARTUP_DIAGNOSTIC_NAME
    hook_env = {
        "PATH": os.environ["PATH"],
        "PLUGIN_ROOT": str(payload),
        "PLUGIN_DATA": str(data),
        "TMPDIR": str(hook_tmp),
    }
    event = {
        "hook_event_name": "SessionStart",
        "session_id": session,
        "prompt": "private prompt",
        "tool_input": "private command",
        "tool_response": "private result",
    }
    try:
        result = subprocess.run(
            [sys.executable, str(payload / "hooks" / "discover.py")],
            input=json.dumps(event).encode(),
            capture_output=True,
            env=hook_env,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout == b""
        assert result.stderr == b""
        assert data.is_dir()
        assert data.stat().st_mode & 0o777 == 0o700
        record = marker.read_text()
        assert "private prompt" not in record
        assert "private command" not in record
        assert "private result" not in record
        assert json.loads(record).keys() == {"session_id", "plugin_data", "at"}
        health = diagnostic.read_text()
        assert "marker_published" in health
        assert "private prompt" not in health
        assert "private command" not in health
        assert "private result" not in health
        assert discover_plugin_data(session, root=root) == data
        db = tmp_path / "run.db"
        assert main(["workflow", "--db", str(db), "start", "--session-id", session]) == 0
        run = json.loads(capsys.readouterr().out)
        assert main(["workflow", "--db", str(db), "register", run, "--plugin-data", str(data)]) == 0
        assert (
            collect_event(
                data,
                json.dumps(
                    {
                        "hook_event_name": "SubagentStart",
                        "session_id": session,
                        "agent_id": "agent-1",
                        "turn_id": "turn-1",
                    }
                ).encode(),
            )
            == 1
        )
        assert WorkflowStore(db).snapshot(run)["session_id"] == session
        assert WorkflowStore(db).snapshot(run)["observations"] == 1
        query = subprocess.run(
            [
                sys.executable,
                str(payload / "scripts" / "workflow.py"),
                "workflow",
                "plugin-data",
                "--session-id",
                session,
            ],
            capture_output=True,
            text=True,
            env={**hook_env, "TMPDIR": str(cli_tmp)},
            check=False,
        )
        assert query.returncode == 0
        assert json.loads(query.stdout) == str(data)
    finally:
        marker.unlink(missing_ok=True)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS shared temporary handoff")
def test_packaged_discovery_reports_missing_env_and_invalid_event_without_output(
    tmp_path: Path,
) -> None:
    payload = package_plugin(tmp_path / "payload")
    root = Path("/private/tmp") / f"codex-workflow-discovery-{os.getuid()}"
    diagnostic = root / STARTUP_DIAGNOSTIC_NAME
    for extra_env, raw, code in [
        ({}, b'{"private":"prompt-secret"}', "missing_env"),
        ({"PLUGIN_DATA": str(tmp_path / "data")}, b'{"private":"command-secret"}', "invalid_event"),
        (
            {"PLUGIN_DATA": str(tmp_path / "missing-parent" / "data")},
            b'{"hook_event_name":"SessionStart","session_id":"session-12345678","private":"path-secret"}',
            "data_path_failed",
        ),
    ]:
        result = subprocess.run(
            [sys.executable, str(payload / "hooks" / "discover.py")],
            input=raw,
            capture_output=True,
            env={"PATH": os.environ["PATH"], "PLUGIN_ROOT": str(payload), **extra_env},
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout == result.stderr == b""
        last = json.loads(diagnostic.read_text().splitlines()[-1])
        assert last["code"] == code
    health = diagnostic.read_text()
    assert "prompt-secret" not in health
    assert "command-secret" not in health
    assert "path-secret" not in health
