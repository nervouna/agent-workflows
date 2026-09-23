"""Thin installed-hook entry; all behavior lives in the packaged library."""

import os
import sys
from pathlib import Path

root = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(root / "lib"))

from codex_maintenance.workflow.collector import hook_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(hook_main())
