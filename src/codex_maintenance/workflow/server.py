"""Read-only loopback monitor for one workflow run."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from codex_maintenance.workflow.collector import HEALTH_NAME, INDEX_NAME
from codex_maintenance.workflow.model import WorkflowError
from codex_maintenance.workflow.store import WorkflowStore

_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/monitor.css": ("monitor.css", "text/css; charset=utf-8"),
    "/monitor.js": ("monitor.js", "text/javascript; charset=utf-8"),
}


def _assets_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    packaged = root / "assets"
    return packaged if packaged.is_dir() else root / "plugins" / "workflow-monitor" / "assets"


def _endpoint_file(db_path: Path, run_id: str) -> Path:
    return db_path.resolve().parent / f"{run_id}.monitor.json"


def _collector_health(snapshot: dict[str, object], plugin_data: Path | None) -> str:
    if plugin_data is None:
        return "finished" if snapshot["state"] == "finished" else "unknown"
    diagnostics = plugin_data / HEALTH_NAME
    if diagnostics.is_file() and not diagnostics.is_symlink():
        try:
            with diagnostics.open("rb") as stream:
                stream.seek(max(0, diagnostics.stat().st_size - 65536))
                tail = stream.read(65536)
            for line in reversed(tail.splitlines()):
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if (
                    isinstance(event, dict)
                    and event.get("code")
                    in {"index_read_failed", "run_write_failed", "collector_failed"}
                    and isinstance(event.get("at"), (int, float))
                    and event["at"] >= snapshot["created_at"]
                ):
                    # Diagnostics are plugin-wide. This does not attribute a failure to this run.
                    return "degraded"
                break
        except OSError:
            return "unavailable"
    if snapshot["state"] == "finished":
        return "finished"
    index = plugin_data / INDEX_NAME
    if not index.is_file():
        return "unregistered"
    try:
        with sqlite3.connect(f"{index.resolve().as_uri()}?mode=ro", uri=True, timeout=0.25) as db:
            registered = db.execute(
                "SELECT 1 FROM active_runs WHERE run_id=?", (snapshot["id"],)
            ).fetchone()
    except sqlite3.Error:
        return "unavailable"
    return "registered" if registered else "unregistered"


def _public_snapshot(snapshot: dict[str, object], plugin_data: Path | None) -> dict[str, object]:
    """Expose only fields needed by the monitor, never report paths or agent IDs."""
    tasks = []
    for task in snapshot["tasks"]:
        tasks.append(
            {
                "id": task["id"],
                "stage": task["stage"],
                "name": task["name"],
                "state": task["state"],
                "accepted_version": task["accepted_version"],
                "acceptance_valid": task["acceptance_valid"],
                "attempts": [
                    {
                        "number": a["number"],
                        "returned": a["returned"],
                        "observed_start": a["observed_start"],
                        "observed_stop": a["observed_stop"],
                    }
                    for a in task["attempts"]
                ],
                "reports": [
                    {"version": r["version"], "valid": r["valid"], "created_at": r["created_at"]}
                    for r in task["reports"]
                ],
            }
        )
    return {
        "id": snapshot["id"],
        "stage": snapshot["stage"],
        "stages": snapshot["stages"],
        "state": snapshot["state"],
        "created_at": snapshot["created_at"],
        "finished_at": snapshot["finished_at"],
        "tasks": tasks,
        "revisions": [
            {
                "review_task_id": r["review_task_id"],
                "review_version": r["review_version"],
                "synthesis_task_id": r["synthesis_task_id"],
                "synthesis_version": r["synthesis_version"],
            }
            for r in snapshot["revisions"]
        ],
        "observations": snapshot["observations"],
        "last_observation_at": snapshot["last_observation_at"],
        "collector_health": _collector_health(snapshot, plugin_data),
    }


def make_server(
    db_path: Path, run_id: str, port: int = 0, plugin_data: Path | None = None
) -> ThreadingHTTPServer:
    db_path = db_path.resolve()
    if not db_path.is_file():
        raise WorkflowError("run database does not exist")
    store = WorkflowStore(db_path)
    store.snapshot(run_id)  # Reject an unknown run before listening.
    token = secrets.token_urlsafe(32)
    instance_id = hashlib.sha256(token.encode()).hexdigest()[:24]
    assets = _assets_dir()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; object-src 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self._send(403, b"Forbidden", "text/plain; charset=utf-8")
                return
            path = urlsplit(self.path).path
            if path == "/health":
                try:
                    store.snapshot(run_id)
                except (OSError, WorkflowError):
                    self._send(503, b'{"ok":false}', "application/json; charset=utf-8")
                    return
                health = {"ok": True, "run_id": run_id, "instance_id": instance_id}
                self._send(200, json.dumps(health).encode(), "application/json; charset=utf-8")
            elif path == "/api/status":
                try:
                    data = _public_snapshot(store.snapshot(run_id), plugin_data)
                except (OSError, WorkflowError):
                    self._send(
                        503, b'{"error":"status unavailable"}', "application/json; charset=utf-8"
                    )
                    return
                self._send(200, json.dumps(data).encode(), "application/json; charset=utf-8")
            elif path.startswith("/api/reports/"):
                parts = path.split("/")
                if len(parts) != 5 or not parts[3] or not parts[4].isdigit():
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
                    return
                try:
                    report = store.get_report(run_id, parts[3], int(parts[4]))
                except WorkflowError:
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
                    return
                self._send(200, str(report["content"]).encode(), "text/plain; charset=utf-8")
            elif path in _ASSETS:
                filename, mime = _ASSETS[path]
                self._send(200, (assets / filename).read_bytes(), mime)
            else:
                self._send(404, b"Not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            if (
                self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                or self.path != "/internal/close"
                or self.headers.get("X-Monitor-Token") != token
            ):
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            self._send(200, b"Closed", "text/plain; charset=utf-8")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.monitor_token = token  # type: ignore[attr-defined]
    server.monitor_instance_id = instance_id  # type: ignore[attr-defined]
    return server


def serve(db_path: Path, run_id: str, port: int = 0, plugin_data: Path | None = None) -> str:
    existing = monitor_url(db_path, run_id)
    if existing:
        print(existing, flush=True)
        return existing
    server = make_server(db_path, run_id, port, plugin_data)
    endpoint = _endpoint_file(db_path, run_id)
    address = f"http://127.0.0.1:{server.server_port}"
    data = {
        "url": address,
        "token": server.monitor_token,  # type: ignore[attr-defined]
        "instance_id": server.monitor_instance_id,  # type: ignore[attr-defined]
        "pid": os.getpid(),
    }
    descriptor, name = tempfile.mkstemp(prefix="workflow-monitor-", dir=endpoint.parent)
    tmp = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        tmp.replace(endpoint)
    finally:
        tmp.unlink(missing_ok=True)
    print(address, flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        try:
            if json.loads(endpoint.read_text())["token"] == data["token"]:
                endpoint.unlink()
        except (OSError, ValueError, KeyError):
            pass
    return address


def close(db_path: Path, run_id: str) -> bool:
    if monitor_url(db_path, run_id) is None:
        return False
    endpoint = _endpoint_file(db_path, run_id)
    try:
        data = json.loads(endpoint.read_text(encoding="utf-8"))
        url = data["url"]
        if not url.startswith("http://127.0.0.1:"):
            return False
        request = Request(
            url + "/internal/close", method="POST", headers={"X-Monitor-Token": data["token"]}
        )
        with urlopen(request, timeout=2) as response:
            return response.status == 200
    except (OSError, ValueError, KeyError):
        return False


def monitor_url(db_path: Path, run_id: str) -> str | None:
    try:
        data = json.loads(_endpoint_file(db_path, run_id).read_text(encoding="utf-8"))
        url = data["url"]
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not isinstance(data["instance_id"], str)
        ):
            return None
        with urlopen(url + "/health", timeout=2) as response:
            if response.status == 200:
                health = json.load(response)
                if (
                    isinstance(health, dict)
                    and health.get("run_id") == run_id
                    and health.get("instance_id") == data["instance_id"]
                ):
                    return url
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def export_report(db_path: Path, run_id: str, task_id: str, version: int, output: Path) -> None:
    report = WorkflowStore(db_path).get_report(run_id, task_id, version)
    output.write_text(str(report["content"]), encoding="utf-8")
