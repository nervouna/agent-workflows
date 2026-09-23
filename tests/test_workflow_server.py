"""Loopback monitor contracts and report access."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from codex_maintenance.cli import main
from codex_maintenance.workflow.collector import collect_event, register_run, unregister_run
from codex_maintenance.workflow.server import close, export_report, make_server, monitor_url, serve
from codex_maintenance.workflow.store import WorkflowStore


def _get(url: str) -> tuple[int, bytes, dict[str, str]]:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status, response.read(), dict(response.headers)
    except HTTPError as error:
        return error.code, error.read(), dict(error.headers)


@pytest.fixture
def monitor(tmp_path):
    database = tmp_path / "run.db"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    server = make_server(database, run_id)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield store, run_id, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def test_status_and_fixed_assets(monitor):
    store, run_id, url = monitor
    task_id = store.create_task(run_id, "scan", "<img src=x onerror=alert(1)>")
    code, body, headers = _get(url + "/api/status")
    assert code == 200
    data = json.loads(body)
    assert data["tasks"][0]["name"] == "<img src=x onerror=alert(1)>"
    assert "session_id" not in data
    assert "agent_id" not in body.decode()
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert data["tasks"][0]["id"] == task_id
    _, script, _ = _get(url + "/monitor.js")
    assert b"textContent" in script
    assert b"innerHTML" not in script
    assert _get(url + "/health")[0] == 200
    assert _get(url + "/")[0] == 200


def test_old_reports_and_no_file_read(monitor, tmp_path):
    store, run_id, url = monitor
    task = store.create_task(run_id, "scan", "scan")
    attempt = store.begin_attempt(task)
    store.bind_attempt(attempt, "agent", "turn")
    store.mark_returned(attempt)
    assert store.submit_report(task, "first") == 1
    assert store.submit_report(task, "second") == 2
    assert _get(url + f"/api/reports/{task}/1")[1] == b"first"
    assert _get(url + f"/api/reports/{task}/2")[1] == b"second"
    assert _get(url + f"/api/reports/{task}/3")[0] == 404
    secret = tmp_path / "private.txt"
    secret.write_text("SECRET")
    for path in ("/../private.txt", "/%2e%2e/private.txt", "/api/reports/../../private.txt"):
        code, body, _ = _get(url + path)
        assert code == 404
        assert b"SECRET" not in body
    assert _get(url + "/api/reports/other/1")[0] == 404


def test_close_requires_private_token(monitor):
    _, _, url = monitor
    request = Request(url + "/internal/close", method="POST")
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)
    assert error.value.code == 404


def test_foreign_host_is_rejected(monitor):
    _, _, url = monitor
    request = Request(url + "/api/status", headers={"Host": "foreign.example"})
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)
    assert error.value.code == 403


def test_collector_registration_health(tmp_path):
    database = tmp_path / "run.db"
    plugin_data = tmp_path / "plugin-data"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    server = make_server(database, run_id, plugin_data=plugin_data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/status"
    try:
        assert json.loads(_get(url)[1])["collector_health"] == "unregistered"
        register_run(plugin_data, database, run_id)
        assert json.loads(_get(url)[1])["collector_health"] == "registered"
        unregister_run(plugin_data, run_id)
        assert json.loads(_get(url)[1])["collector_health"] == "unregistered"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_registered_collector_failure_is_shown_as_plugin_wide(tmp_path, monkeypatch):
    database = tmp_path / "run.db"
    plugin_data = tmp_path / "plugin-data"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    register_run(plugin_data, database, run_id)

    def failed_write(*args, **kwargs):
        raise sqlite3.OperationalError("simulated write failure")

    monkeypatch.setattr(WorkflowStore, "ingest_observation", failed_write)
    event = json.dumps({"hook_event_name": "SessionStart", "session_id": "session"}).encode()
    assert collect_event(plugin_data, event) == 0
    server = make_server(database, run_id, plugin_data=plugin_data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/status"
        status = json.loads(_get(url)[1])
        assert status["collector_health"] == "degraded"
        assert "simulated write failure" not in json.dumps(status)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stale_endpoint_cannot_impersonate_another_monitor(tmp_path):
    database = tmp_path / "run.db"
    store = WorkflowStore(database)
    requested_run = store.start_run("requested")
    other_run = store.start_run("other")
    other = make_server(database, other_run)
    other_thread = threading.Thread(target=other.serve_forever, daemon=True)
    other_thread.start()
    stale_url = f"http://127.0.0.1:{other.server_port}"
    endpoint = tmp_path / f"{requested_run}.monitor.json"
    endpoint.write_text(
        json.dumps(
            {"url": stale_url, "instance_id": other.monitor_instance_id, "token": "stale", "pid": 0}
        )
    )
    requested_thread = None
    try:
        assert monitor_url(database, requested_run) is None
        requested_thread = threading.Thread(
            target=serve, args=(database, requested_run), daemon=True
        )
        requested_thread.start()
        actual_url = None
        for _ in range(100):
            actual_url = monitor_url(database, requested_run)
            if actual_url:
                break
            time.sleep(0.01)
        assert actual_url is not None and actual_url != stale_url
        assert json.loads(_get(actual_url + "/health")[1])["run_id"] == requested_run
        assert close(database, requested_run)
        requested_thread.join(timeout=2)
        assert not requested_thread.is_alive()
    finally:
        other.shutdown()
        other.server_close()
        other_thread.join(timeout=2)


def test_stale_instance_identity_rejected_even_for_same_run(tmp_path):
    database = tmp_path / "run.db"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    server = make_server(database, run_id)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = tmp_path / f"{run_id}.monitor.json"
    endpoint.write_text(
        json.dumps(
            {
                "url": f"http://127.0.0.1:{server.server_port}",
                "instance_id": "old-instance",
                "token": "old",
            }
        )
    )
    try:
        assert monitor_url(database, run_id) is None
        assert not close(database, run_id)
        assert _get(f"http://127.0.0.1:{server.server_port}/health")[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_restart_uses_persistent_state(tmp_path):
    database = tmp_path / "run.db"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    task_id = store.create_task(run_id, "scan", "persisted")
    first = make_server(database, run_id)
    first.server_close()
    second = make_server(database, run_id)
    thread = threading.Thread(target=second.serve_forever, daemon=True)
    thread.start()
    try:
        status = json.loads(_get(f"http://127.0.0.1:{second.server_port}/api/status")[1])
        assert status["tasks"][0]["id"] == task_id
    finally:
        second.shutdown()
        second.server_close()
        thread.join(timeout=2)


def test_service_close_and_export_after_close(tmp_path):
    database = tmp_path / "run.db"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    task = store.create_task(run_id, "scan", "scan")
    attempt = store.begin_attempt(task)
    store.bind_attempt(attempt, "agent", "turn")
    store.mark_returned(attempt)
    store.submit_report(task, "report survives service shutdown")
    worker = threading.Thread(target=serve, args=(database, run_id), daemon=True)
    worker.start()
    for _ in range(100):
        url = monitor_url(database, run_id)
        if url:
            break
        time.sleep(0.01)
    assert url is not None
    assert close(database, run_id)
    worker.join(timeout=2)
    assert not worker.is_alive()
    output = tmp_path / "export.txt"
    export_report(database, run_id, task, 1, output)
    assert output.read_text() == "report survives service shutdown"


def test_finish_keeps_monitor_available_until_explicit_close(tmp_path):
    database = tmp_path / "run.db"
    store = WorkflowStore(database)
    run_id = store.start_run("session")
    last_task = ""
    for stage in ("scan", "review", "synthesis", "independent_review"):
        last_task = store.create_task(run_id, stage, stage)
        attempt = store.begin_attempt(last_task)
        store.bind_attempt(attempt, f"agent-{stage}", f"turn-{stage}")
        store.mark_returned(attempt)
        version = store.submit_report(last_task, f"report-{stage}")
        store.accept_report(last_task, version)
        if stage != "independent_review":
            store.advance_stage(run_id)
    worker = threading.Thread(target=serve, args=(database, run_id), daemon=True)
    worker.start()
    url = None
    for _ in range(100):
        url = monitor_url(database, run_id)
        if url:
            break
        time.sleep(0.01)
    assert url is not None
    assert main(["workflow", "--db", str(database), "finish", run_id]) == 0
    assert json.loads(_get(url + "/api/status")[1])["state"] == "finished"
    assert main(["workflow", "--db", str(database), "close", run_id]) == 0
    worker.join(timeout=2)
    assert not worker.is_alive()
    output = tmp_path / "final.txt"
    export_report(database, run_id, last_task, 1, output)
    assert output.read_text() == "report-independent_review"
