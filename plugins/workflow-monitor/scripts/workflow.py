"""Run the packaged workflow CLI without the source checkout or uv."""

import os
import sys
from pathlib import Path

root = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(root / "lib"))

from codex_maintenance.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
