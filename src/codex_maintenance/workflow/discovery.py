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
MAX_STARTUP_DIAGNOSTIC_BYTES = 65536
STARTUP_DIAGNOSTIC_NAME = "startup-health.jsonl"
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}\Z")
STARTUP_CODES = frozenset(
    {
        "invoked",
        "missing_env",
        "invalid_event",
        "data_path_failed",
        "data_path_not_absolute",
        "data_path_parent_missing",
        "data_path_parent_unavailable",
        "data_path_parent_symlink",
        "data_path_parent_type",
        "data_path_parent_mkdir",
        "data_path_parent_owner",
        "data_path_parent_permissions",
        "data_path_leaf_mkdir",
        "data_path_leaf_unavailable",
        "data_path_leaf_symlink",
        "data_path_leaf_type",
        "data_path_leaf_owner",
        "data_path_leaf_permissions",
        "data_path_resolve_mismatch",
        "marker_failed",
        "marker_published",
    }
)


class PluginDataError(WorkflowError):
    """The host-provided plugin data location could not be prepared."""

    def __init__(self, reason: str) -> None:
        if reason not in STARTUP_CODES or not reason.startswith("data_path_"):
            raise ValueError("invalid plugin data failure reason")
        self.reason = reason
        super().__init__(reason)


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


def record_startup(code: str, *, root: Path | None = None) -> None:
    """Best-effort, fixed-code diagnostics outside a possibly absent PLUGIN_DATA."""
    if code not in STARTUP_CODES:
        return
    try:
        root = _checked_root(_root() if root is None else root, create=True)
        path = root / STARTUP_DIAGNOSTIC_NAME
        entry = json.dumps({"at": time.time(), "code": code}) + "\n"
        if path.exists():
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                return
            if info.st_size + len(entry) > MAX_STARTUP_DIAGNOSTIC_BYTES:
                path.unlink()
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(entry)
    except (OSError, WorkflowError):
        return


def _prepare_plugin_data(plugin_data: Path) -> Path:
    if not plugin_data.is_absolute():
        raise PluginDataError("data_path_not_absolute")
    if not plugin_data.name or ".." in plugin_data.parts:
        raise PluginDataError("data_path_resolve_mismatch")
    parent = Path(plugin_data.anchor)
    parent_info = None
    for component in (None, *plugin_data.parent.parts[1:]):
        if component is not None:
            parent = parent / component
        try:
            info = parent.lstat()
        except FileNotFoundError:
            if parent_info is None or parent_info.st_uid != os.getuid():
                raise PluginDataError("data_path_parent_owner") from None
            try:
                parent.mkdir(mode=0o700)
                parent.chmod(0o700)
                info = parent.lstat()
            except OSError as error:
                raise PluginDataError("data_path_parent_mkdir") from error
        except OSError as error:
            raise PluginDataError("data_path_parent_unavailable") from error
        if stat.S_ISLNK(info.st_mode):
            raise PluginDataError("data_path_parent_symlink")
        if not stat.S_ISDIR(info.st_mode):
            raise PluginDataError("data_path_parent_type")
        if info.st_uid not in (0, os.getuid()):
            raise PluginDataError("data_path_parent_owner")
        if info.st_mode & 0o022:
            raise PluginDataError("data_path_parent_permissions")
        parent_info = info
    try:
        leaf = plugin_data.lstat()
    except FileNotFoundError:
        try:
            plugin_data.mkdir(mode=0o700)
        except OSError as error:
            raise PluginDataError("data_path_leaf_mkdir") from error
        try:
            leaf = plugin_data.lstat()
        except OSError as error:
            raise PluginDataError("data_path_leaf_unavailable") from error
    except OSError as error:
        raise PluginDataError("data_path_leaf_unavailable") from error
    if stat.S_ISLNK(leaf.st_mode):
        raise PluginDataError("data_path_leaf_symlink")
    if not stat.S_ISDIR(leaf.st_mode):
        raise PluginDataError("data_path_leaf_type")
    if leaf.st_uid != os.getuid():
        raise PluginDataError("data_path_leaf_owner")
    if leaf.st_mode & 0o022:
        raise PluginDataError("data_path_leaf_permissions")
    try:
        data = plugin_data.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise PluginDataError("data_path_leaf_unavailable") from error
    if data.parent != parent:
        raise PluginDataError("data_path_resolve_mismatch")
    return data


def publish_plugin_data(session_id: str, plugin_data: Path, *, root: Path | None = None) -> None:
    """Publish only the exact session ID and host data path, atomically and privately."""
    root = _root() if root is None else root
    marker = _marker(root, session_id)
    data = _prepare_plugin_data(plugin_data)
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
