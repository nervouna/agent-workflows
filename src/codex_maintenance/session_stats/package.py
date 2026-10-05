"""Build a standalone plugin from the single maintained production source."""

import shutil
from pathlib import Path

from . import StatsError


def package_plugin(destination: Path) -> Path:
    repository = Path(__file__).resolve().parents[3]
    payload = repository / "plugins" / "session-stats"
    source = Path(__file__).parent
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise StatsError("Plugin package destination must be a new directory.")
    for root in (payload, source):
        if any(path.is_symlink() for path in root.rglob("*")):
            raise StatsError("Plugin sources must not contain symlinks.")
    shutil.copytree(payload, destination)
    library = destination / "lib" / "codex_maintenance"
    library.mkdir(parents=True)
    (library / "__init__.py").write_text("")
    shutil.copytree(
        source, library / "session_stats", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    return destination
