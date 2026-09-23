"""Private, short-lived handoff of host plugin data from SessionStart to the CLI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from codex_maintenance.workflow.model import WorkflowError

MAX_AGE_SECONDS = 3600
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}\Z")


def _root() -> Path:
    temporary = Path("/private/tmp") if sys.platform == "darwin" else Path(tempfile.gettempdir())
    return temporary / f"codex-workflow-discovery-{os.getuid()}"


def _checked_root(root: Path, *, create: bool) -> Path:
    if create:
        with suppress(FileExistsError):
            root.mkdir(mode=0o700)
    try:
        info = root.lstat()
    except FileNotFoundError as error:
        raise WorkflowError("no SessionStart discovery marker is available") from error
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise WorkflowError("discovery directory is not private")
    return root


def _marker(root: Path, session_id: str) -> Path:
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise WorkflowError("invalid session ID for plugin discovery")
    return root / (hashlib.sha256(session_id.encode()).hexdigest() + ".json")


def publish_plugin_data(session_id: str, plugin_data: Path, *, root: Path | None = None) -> None:
    """Publish only the exact session ID and host data path, atomically and privately."""
    root = _root() if root is None else root
    marker = _marker(root, session_id)
    if not plugin_data.is_absolute() or not plugin_data.is_dir():
        raise WorkflowError("host PLUGIN_DATA is not an absolute directory")
    data = plugin_data.resolve(strict=True)
    if data.stat().st_uid != os.getuid():
        raise WorkflowError("host PLUGIN_DATA has a different owner")
    _checked_root(root, create=True)
    descriptor, name = tempfile.mkstemp(prefix=".marker-", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(
                {"session_id": session_id, "plugin_data": str(data), "at": time.time()}, stream
            )
        os.replace(name, marker)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def discover_plugin_data(session_id: str, *, root: Path | None = None) -> Path:
    """Resolve a fresh marker only when its stored identity and permissions match."""
    root = _checked_root(_root() if root is None else root, create=False)
    marker = _marker(root, session_id)
    try:
        info = marker.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise WorkflowError("discovery marker is not private")
        with marker.open(encoding="utf-8") as stream:
            record = json.load(stream)
    except FileNotFoundError as error:
        raise WorkflowError("no SessionStart marker matches this session ID") from error
    except (json.JSONDecodeError, UnicodeError) as error:
        raise WorkflowError("invalid SessionStart discovery marker") from error
    if not isinstance(record, dict) or record.get("session_id") != session_id:
        raise WorkflowError("SessionStart discovery identity mismatch")
    at = record.get("at")
    if not isinstance(at, (int, float)) or not 0 <= time.time() - at <= MAX_AGE_SECONDS:
        raise WorkflowError("SessionStart discovery marker is stale")
    value = record.get("plugin_data")
    if not isinstance(value, str):
        raise WorkflowError("invalid host PLUGIN_DATA path")
    data = Path(value)
    if not data.is_absolute() or not data.is_dir() or data.stat().st_uid != os.getuid():
        raise WorkflowError("host PLUGIN_DATA is unavailable")
    return data.resolve(strict=True)
