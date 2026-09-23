"""Exercise the documented CLI sequence without claiming native-agent acceptance."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codex_maintenance.cli import main
from codex_maintenance.workflow.package import package_plugin
from codex_maintenance.workflow.store import WorkflowStore


def test_four_stages_revision_and_missing_artifact_gate(tmp_path: Path, capsys) -> None:
    db = tmp_path / "run.db"
    data = tmp_path / "plugin-data"

    def call(*args: str) -> object | None:
        assert main(["workflow", "--db", str(db), *args]) == 0
        output = capsys.readouterr().out
        return json.loads(output) if output else None

    def task(stage: str, name: str, agent: str, content: str) -> tuple[str, int, Path]:
        task_id = call("task", run, stage, name)
        attempt_id = call("attempt", task_id)
        call("bind", attempt_id, agent)
        call("returned", attempt_id)
        report = tmp_path / f"{name}.txt"
        report.write_text(content)
        version = call("submit", task_id, str(report))
        return task_id, version, report

    run = call("start", "--session-id", "actual-parent", "--plugin-data", str(data))
    scan_a, a_version, _ = task("scan", "source-a", "agent-a", "Evidence A: checked source")
    scan_b, b_version, b_report = task("scan", "source-b", "agent-b", "Evidence B: checked source")
    with pytest.raises(SystemExit):
        call("advance", run)
    capsys.readouterr()
    call("accept", scan_a, str(a_version))
    b_report.unlink()
    with pytest.raises(SystemExit):
        call("accept", scan_b, str(b_version))
    capsys.readouterr()
    b_report.write_text("Evidence B: checked source")
    call("accept", scan_b, str(b_version))
    assert call("advance", run) == "review"

    review, version, _ = task("review", "source-review", "review-agent", "A and B verified")
    call("accept", review, str(version))
    assert call("advance", run) == "synthesis"
    synthesis, version, _ = task("synthesis", "synthesis", "synth-agent", "First synthesis")
    call("accept", synthesis, str(version))
    assert call("advance", run) == "independent_review"
    first_review, first_version, _ = task(
        "independent_review", "independent-1", "fresh-agent-1", "NO-GO: revise evidence"
    )
    call("revision", first_review, synthesis, str(first_version))
    snapshot = call("status", run)
    assert snapshot["stage"] == "synthesis"
    assert len(snapshot["revisions"]) == 1

    new_attempt = call("attempt", synthesis)
    call("bind", new_attempt, "synth-agent", "--turn-id", "new-turn")
    call("returned", new_attempt)
    revised = tmp_path / "synthesis-v2.txt"
    revised.write_text("Revised synthesis with stronger evidence")
    second_version = call("submit", synthesis, str(revised))
    assert second_version == 2
    call("accept", synthesis, str(second_version))
    assert call("advance", run) == "independent_review"
    second_review, second_review_version, _ = task(
        "independent_review", "independent-2", "fresh-agent-2", "GO: evidence verified"
    )
    call("accept", second_review, str(second_review_version))
    call("finish", run, "--plugin-data", str(data))
    snapshot = call("status", run)
    assert snapshot["state"] == "finished"
    tasks = {item["id"]: item for item in snapshot["tasks"]}
    assert tasks[first_review]["state"] == "revision_requested"
    assert [report["version"] for report in tasks[synthesis]["reports"]] == [1, 2]


def test_packaged_skill_and_cli_are_present(tmp_path: Path) -> None:
    payload = package_plugin(tmp_path / "payload")
    skill = payload / "skills" / "workflow-monitor" / "SKILL.md"
    assert skill.is_file()
    result = subprocess.run(
        [sys.executable, str(payload / "scripts" / "workflow.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "workflow" in result.stdout


def test_cli_interruption_requires_new_attempt_and_old_stop_cannot_return_it(
    tmp_path: Path, capsys
) -> None:
    db = tmp_path / "run.db"

    def call(*args: str) -> object | None:
        assert main(["workflow", "--db", str(db), *args]) == 0
        output = capsys.readouterr().out
        return json.loads(output) if output else None

    run = call("start", "--session-id", "parent")
    task = call("task", run, "scan", "source")
    old = call("attempt", task)
    call("bind", old, "agent", "--turn-id", "turn-1")
    call("interrupt", old)
    call("interrupt", old)  # Idempotent while ready to resume.
    report = tmp_path / "report.txt"
    report.write_text("premature report")
    with pytest.raises(SystemExit):
        call("returned", old)
    with pytest.raises(SystemExit):
        call("submit", task, str(report))
    capsys.readouterr()

    new = call("attempt", task)
    call("bind", new, "agent", "--turn-id", "turn-2")
    call("observe", "parent", "SubagentStop", "agent", "turn-1")
    snapshot = call("status", run)
    attempts = snapshot["tasks"][0]["attempts"]
    assert attempts[0]["interrupted"] is True
    assert attempts[0]["returned"] is False
    assert attempts[0]["observed_stop"] is True
    assert attempts[1]["returned"] is False
    assert attempts[1]["observed_stop"] is False
    with pytest.raises(SystemExit):
        call("submit", task, str(report))
    capsys.readouterr()
    call("returned", new)
    version = call("submit", task, str(report))
    call("accept", task, str(version))
    assert call("status", run)["tasks"][0]["acceptance_valid"] is True


def test_existing_run_database_adds_interruption_state(tmp_path: Path) -> None:
    path = tmp_path / "existing.db"
    WorkflowStore(path)
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE attempts DROP COLUMN interrupted")
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: WorkflowStore(path), range(2)))
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
    assert "interrupted" in columns
