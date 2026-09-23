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
    _marker,
    discover_plugin_data,
    publish_plugin_data,
)
from codex_maintenance.workflow.model import WorkflowError
from codex_maintenance.workflow.package import package_plugin
from codex_maintenance.workflow.store import WorkflowStore

SESSION = "session-12345678"


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
    data.mkdir()
    hook_tmp = tmp_path / "hook-tmp"
    cli_tmp = tmp_path / "cli-tmp"
    hook_tmp.mkdir()
    cli_tmp.mkdir()
    session = f"session-{uuid.uuid4().hex}"
    root = Path("/private/tmp") / f"codex-workflow-discovery-{os.getuid()}"
    marker = _marker(root, session)
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
        record = marker.read_text()
        assert "private prompt" not in record
        assert "private command" not in record
        assert "private result" not in record
        assert json.loads(record).keys() == {"session_id", "plugin_data", "at"}
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
