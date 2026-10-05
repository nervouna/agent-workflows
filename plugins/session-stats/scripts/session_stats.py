"""Run the packaged standard-library-only snapshot program."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from codex_maintenance.session_stats.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
