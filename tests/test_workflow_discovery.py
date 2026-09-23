from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_maintenance.cli import main
from codex_maintenance.workflow import collector
from codex_maintenance.workflow.collector import HEALTH_NAME, collect_event, register_run
from codex_maintenance.workflow.discovery import (
    STARTUP_DIAGNOSTIC_NAME,
    PluginDataError,
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
    data = tmp_path / "new-parent" / "nested" / "plugin-data"
    root = tmp_path / "handoff"
    publish_plugin_data(SESSION, data, root=root)
    assert data.is_dir()
    assert data.parent.stat().st_mode & 0o777 == 0o700
    assert data.parent.parent.stat().st_mode & 0o777 == 0o700
    assert data.stat().st_mode & 0o777 == 0o700
    assert discover_plugin_data(SESSION, root=root) == data


def test_publish_rejects_unsafe_host_data_location(tmp_path: Path) -> None:
    root = tmp_path / "handoff"
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked-data"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PluginDataError, match="data_path_leaf_symlink"):
        publish_plugin_data(SESSION, link, root=root)
    ancestor = tmp_path / "unsafe-parent"
    ancestor.mkdir()
    ancestor.chmod(0o777)
    with pytest.raises(PluginDataError, match="data_path_parent_permissions"):
        publish_plugin_data(SESSION, ancestor / "missing" / "data", root=root)
    assert not (ancestor / "missing").exists()
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PluginDataError, match="data_path_parent_symlink"):
        publish_plugin_data(SESSION, parent_link / "missing" / "data", root=root)
    assert not (outside / "missing").exists()
    assert not root.exists()


def test_host_data_reason_codes_are_specific_and_fixed(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "handoff"
    leaf = tmp_path / "data"
    cases = [(Path("relative"), "data_path_not_absolute")]
    for path, reason in cases:
        with pytest.raises(PluginDataError) as caught:
            publish_plugin_data(SESSION, path, root=root)
        assert caught.value.reason == reason

    tmp_path.chmod(0o777)
    with pytest.raises(PluginDataError) as caught:
        publish_plugin_data(SESSION, leaf, root=root)
    assert caught.value.reason == "data_path_parent_permissions"
    tmp_path.chmod(0o700)

    leaf.write_text("not a directory")
    with pytest.raises(PluginDataError) as caught:
        publish_plugin_data(SESSION, leaf, root=root)
    assert caught.value.reason == "data_path_leaf_type"
    leaf.unlink()
    leaf.mkdir(mode=0o777)
    leaf.chmod(0o777)
    with pytest.raises(PluginDataError) as caught:
        publish_plugin_data(SESSION, leaf, root=root)
    assert caught.value.reason == "data_path_leaf_permissions"
    leaf.rmdir()

    original_mkdir = Path.mkdir

    def denied_mkdir(path: Path, *args, **kwargs) -> None:
        if path == leaf:
            raise PermissionError("sensitive operating-system detail")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied_mkdir)
    with pytest.raises(PluginDataError) as caught:
        publish_plugin_data(SESSION, leaf, root=root)
    assert caught.value.reason == "data_path_leaf_mkdir"
    assert "sensitive" not in str(caught.value)
    assert not root.exists()


def test_host_data_owner_and_resolve_reasons(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "handoff"
    leaf = tmp_path / "data"
    leaf.mkdir()
    with monkeypatch.context() as patch:
        patch.setattr(os, "getuid", lambda: -1)
        with pytest.raises(PluginDataError) as caught:
            publish_plugin_data(SESSION, leaf, root=root)
        assert caught.value.reason == "data_path_parent_owner"

    original_lstat = Path.lstat

    def different_owner(path: Path):
        info = original_lstat(path)
        if path == leaf:
            return SimpleNamespace(st_mode=info.st_mode, st_uid=-1)
        return info

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", different_owner)
        with pytest.raises(PluginDataError) as caught:
            publish_plugin_data(SESSION, leaf, root=root)
        assert caught.value.reason == "data_path_leaf_owner"

    original_resolve = Path.resolve

    def mismatched_resolve(path: Path, *args, **kwargs):
        if path == leaf:
            return tmp_path.parent / "other" / leaf.name
        return original_resolve(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", mismatched_resolve)
        with pytest.raises(PluginDataError) as caught:
            publish_plugin_data(SESSION, leaf, root=root)
        assert caught.value.reason == "data_path_resolve_mismatch"
    assert not root.exists()


def test_host_data_unavailable_reasons(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "handoff"
    leaf = tmp_path / "data"
    original_lstat = Path.lstat

    def denied_parent(path: Path):
        if path == tmp_path:
            raise PermissionError("private filesystem error")
        return original_lstat(path)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", denied_parent)
        with pytest.raises(PluginDataError) as caught:
            publish_plugin_data(SESSION, leaf, root=root)
        assert caught.value.reason == "data_path_parent_unavailable"
        assert "private" not in str(caught.value)

    def denied_leaf(path: Path):
        if path == leaf:
            raise PermissionError("private filesystem error")
        return original_lstat(path)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", denied_leaf)
        with pytest.raises(PluginDataError) as caught:
            publish_plugin_data(SESSION, leaf, root=root)
        assert caught.value.reason == "data_path_leaf_unavailable"
    assert not root.exists()


def test_missing_parent_creation_failure_is_fixed_code(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "new-parent"
    root = tmp_path / "handoff"
    original_mkdir = Path.mkdir

    def denied_mkdir(path: Path, *args, **kwargs) -> None:
        if path == parent:
            raise PermissionError("private filesystem error")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied_mkdir)
    with pytest.raises(PluginDataError) as caught:
        publish_plugin_data(SESSION, parent / "data", root=root)
    assert caught.value.reason == "data_path_parent_mkdir"
    assert "private" not in str(caught.value)
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
    unsafe_parent = tmp_path / "unsafe-parent"
    unsafe_parent.mkdir()
    unsafe_parent.chmod(0o777)
    root = Path("/private/tmp") / f"codex-workflow-discovery-{os.getuid()}"
    diagnostic = root / STARTUP_DIAGNOSTIC_NAME
    for extra_env, raw, code in [
        ({}, b'{"private":"prompt-secret"}', "missing_env"),
        ({"PLUGIN_DATA": str(tmp_path / "data")}, b'{"private":"command-secret"}', "invalid_event"),
        (
            {"PLUGIN_DATA": str(tmp_path / "unsafe-parent" / "data")},
            b'{"hook_event_name":"SessionStart","session_id":"session-12345678","private":"path-secret"}',
            "data_path_parent_permissions",
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


def test_rejected_host_data_is_not_collected_or_diagnosed(tmp_path: Path) -> None:
    payload = package_plugin(tmp_path / "payload")
    target = tmp_path / "target-data"
    link = tmp_path / "linked-data"
    store = WorkflowStore(tmp_path / "run.db")
    session = f"session-{uuid.uuid4().hex}"
    run = store.start_run(session)
    register_run(target, store.path, run)
    link.symlink_to(target, target_is_directory=True)
    event = {"hook_event_name": "SessionStart", "session_id": session}

    result = subprocess.run(
        [sys.executable, str(payload / "hooks" / "discover.py")],
        input=json.dumps(event).encode(),
        capture_output=True,
        env={
            "PATH": os.environ["PATH"],
            "PLUGIN_ROOT": str(payload),
            "PLUGIN_DATA": str(link),
        },
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == result.stderr == b""
    assert store.snapshot(run)["observations"] == 0
    assert not (target / HEALTH_NAME).exists()


def test_marker_failure_does_not_access_plugin_data(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / collector.INDEX_NAME).touch()
    calls: list[str] = []
    event = json.dumps({"hook_event_name": "SessionStart", "session_id": SESSION}).encode()
    monkeypatch.setenv("PLUGIN_DATA", str(data))
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(event)))

    def marker_failure(*_args, **_kwargs) -> None:
        raise WorkflowError("private marker detail")

    monkeypatch.setattr(collector, "publish_plugin_data", marker_failure)
    monkeypatch.setattr(collector, "collect_event", lambda *_args: calls.append("collect"))
    monkeypatch.setattr(collector, "_diagnose", lambda *_args: calls.append("diagnose"))
    assert collector.hook_main(discover=True) == 0
    assert calls == []
