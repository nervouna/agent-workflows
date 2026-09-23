"""Build a temporary, source-independent workflow plugin payload."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def package_plugin(destination: Path | None = None) -> Path:
    """Copy the one maintained source tree into an installable plugin directory."""
    repository = Path(__file__).resolve().parents[3]
    source_plugin = repository / "plugins" / "workflow-monitor"
    source_code = repository / "src" / "codex_maintenance"
    if destination is None:
        destination = Path(tempfile.mkdtemp(prefix="codex-workflow-plugin-")) / "workflow-monitor"
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    for root in (source_plugin, source_code):
        if any(path.is_symlink() for path in root.rglob("*")):
            raise ValueError("plugin package sources must not contain symlinks")
    shutil.copytree(source_plugin, destination)
    shutil.copytree(
        source_code,
        destination / "lib" / "codex_maintenance",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return destination
