from __future__ import annotations

import json
from pathlib import Path

from codex_maintenance.cli import main


def test_workflow_cli_starts_and_reads_status(tmp_path: Path, capsys) -> None:
    database = tmp_path / "run.sqlite3"
    assert main(["workflow", "--db", str(database), "start", "--session-id", "session"]) == 0
    run_id = json.loads(capsys.readouterr().out)
    assert main(["workflow", "--db", str(database), "status", run_id]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["id"] == run_id
    assert status["stage"] == "scan"
