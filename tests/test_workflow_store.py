from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codex_maintenance.workflow.store import WorkflowError, WorkflowStore


def store(tmp_path: Path) -> WorkflowStore:
    return WorkflowStore(tmp_path / "run.sqlite3")


def test_unbound_attempt_cannot_return_or_advance(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    task = db.create_task(run, "scan", "source")
    attempt = db.begin_attempt(task)
    with pytest.raises(WorkflowError):
        db.mark_returned(attempt)
    with pytest.raises(WorkflowError):
        db.advance_stage(run)
    db.bind_attempt(attempt, "real-agent")
    db.mark_returned(attempt)
    assert db.snapshot(run)["tasks"][0]["attempts"][0]["turn_id"] is None


def test_file_report_has_immutable_content_and_scoped_lookup(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    other_run = db.start_run("session")
    task = db.create_task(run, "scan", "source")
    attempt = db.begin_attempt(task)
    db.bind_attempt(attempt, "agent")
    db.mark_returned(attempt)
    report = tmp_path / "report.txt"
    report.write_text("original")
    version = db.submit_report_file(task, report)
    report.write_text("changed")
    assert db.get_report(run, task, version)["content"] == "original"
    with pytest.raises(WorkflowError):
        db.get_report(other_run, task, version)
    with pytest.raises(WorkflowError):
        db.accept_report(task, version)


def test_independent_review_revision_cycle_preserves_history(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    for stage in ("scan", "review", "synthesis"):
        task = db.create_task(run, stage, stage)
        attempt = db.begin_attempt(task)
        db.bind_attempt(attempt, stage)
        db.mark_returned(attempt)
        version = db.submit_report(task, stage)
        db.accept_report(task, version)
        db.advance_stage(run)
        if stage == "synthesis":
            synthesis_task = task
            synthesis_version = version
    review_task = db.create_task(run, "independent_review", "fresh review")
    attempt = db.begin_attempt(review_task)
    db.bind_attempt(attempt, "review-agent")
    db.mark_returned(attempt)
    review_version = db.submit_report(review_task, "revise the synthesis")
    db.request_revision(review_task, synthesis_task, review_version)
    status = db.snapshot(run)
    assert status["stage"] == "synthesis"
    assert status["tasks"][-1]["state"] == "revision_requested"
    assert status["revisions"][0]["synthesis_version"] == synthesis_version
    revised_attempt = db.begin_attempt(synthesis_task)
    db.bind_attempt(revised_attempt, "synthesis-agent", "new-turn")
    db.mark_returned(revised_attempt)
    next_version = db.submit_report(synthesis_task, "revised synthesis")
    db.accept_report(synthesis_task, next_version)
    db.advance_stage(run)
    new_review = db.create_task(run, "independent_review", "new context review")
    new_attempt = db.begin_attempt(new_review)
    db.bind_attempt(new_attempt, "fresh-review-agent")
    db.mark_returned(new_attempt)
    final_version = db.submit_report(new_review, "approved revised synthesis")
    db.accept_report(new_review, final_version)
    db.finish_run(run)
    assert db.snapshot(run)["state"] == "finished"
    assert db.get_report(run, review_task, review_version)["content"] == "revise the synthesis"


def test_early_events_replay_and_late_stop_does_not_finish_resume(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session-1")
    task = db.create_task(run, "scan", "source")
    db.ingest_observation("session-1", "SubagentStart", "agent-1", "turn-1")
    first = db.begin_attempt(task)
    db.bind_attempt(first, "agent-1")
    assert db.snapshot(run)["tasks"][0]["attempts"][0]["turn_id"] == "turn-1"

    db.mark_returned(first)
    db.rework_task(task)
    second = db.begin_attempt(task)
    db.bind_attempt(second, "agent-1", "turn-2")
    db.ingest_observation("session-1", "SubagentStop", "agent-1", "turn-1")
    attempts = db.snapshot(run)["tasks"][0]["attempts"]
    assert attempts[0]["observed_stop"] is True
    assert attempts[1]["observed_stop"] is False


def test_versioned_acceptance_and_stage_gate(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session-1")
    task = db.create_task(run, "scan", "source")
    with pytest.raises(WorkflowError):
        db.advance_stage(run)
    attempt = db.begin_attempt(task)
    db.bind_attempt(attempt, "agent")
    db.mark_returned(attempt)
    with pytest.raises(WorkflowError):
        db.submit_report(task, " ")
    v1 = db.submit_report(task, "first report")
    db.accept_report(task, v1)
    v2 = db.submit_report(task, "revised report")
    with pytest.raises(WorkflowError):
        db.advance_stage(run)
    db.accept_report(task, v2)
    assert db.advance_stage(run) == "review"
    assert db.snapshot(run)["tasks"][0]["accepted_version"] == 2


def test_session_isolation_duplicate_notifications_and_concurrent_writers(tmp_path: Path) -> None:
    db = store(tmp_path)
    first_run = db.start_run("session-1")
    second_run = db.start_run("session-2")
    first_task = db.create_task(first_run, "scan", "a")
    second_task = db.create_task(second_run, "scan", "b")
    first_attempt = db.begin_attempt(first_task)
    second_attempt = db.begin_attempt(second_task)
    db.bind_attempt(first_attempt, "agent-shared", "turn-a")
    db.bind_attempt(second_attempt, "agent-shared", "turn-b")

    def deliver(_: int) -> None:
        db.ingest_observation("session-1", "SubagentStop", "agent-shared", "turn-a")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(deliver, range(40)))
    assert db.snapshot(first_run)["tasks"][0]["attempts"][0]["observed_stop"] is True
    assert db.snapshot(second_run)["tasks"][0]["attempts"][0]["observed_stop"] is False
    assert db.snapshot(first_run)["observations"] == 40


def test_report_file_change_invalidates_acceptance(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    task = db.create_task(run, "scan", "source")
    attempt = db.begin_attempt(task)
    db.bind_attempt(attempt, "agent")
    db.mark_returned(attempt)
    report = tmp_path / "report.txt"
    report.write_text("one")
    version = db.submit_report_file(task, report)
    db.accept_report(task, version)
    report.write_text("two")
    assert db.snapshot(run)["tasks"][0]["acceptance_valid"] is False
    with pytest.raises(WorkflowError):
        db.advance_stage(run)


def test_finish_rechecks_earlier_accepted_reports(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    first_report = tmp_path / "scan.txt"
    for stage in ("scan", "review", "synthesis", "independent_review"):
        task = db.create_task(run, stage, stage)
        attempt = db.begin_attempt(task)
        db.bind_attempt(attempt, stage)
        db.mark_returned(attempt)
        report = tmp_path / f"{stage}.txt"
        report.write_text(stage)
        version = db.submit_report_file(task, report)
        db.accept_report(task, version)
        if stage != "independent_review":
            db.advance_stage(run)
    first_report.write_text("changed")
    with pytest.raises(WorkflowError):
        db.finish_run(run)


def test_full_stage_progress_requires_independent_review(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    for index, stage in enumerate(("scan", "review", "synthesis", "independent_review")):
        task = db.create_task(run, stage, stage)
        attempt = db.begin_attempt(task)
        db.bind_attempt(attempt, stage)
        db.mark_returned(attempt)
        report = tmp_path / f"{stage}.txt"
        report.write_text(stage)
        version = db.submit_report_file(task, report)
        db.accept_report(task, version)
        db.mark_returned(attempt)
        assert db.snapshot(run)["tasks"][index]["state"] == "accepted"
        if stage != "independent_review":
            db.advance_stage(run)
    db.finish_run(run)
    db.finish_run(run)
    assert db.snapshot(run)["state"] == "finished"
    with pytest.raises(WorkflowError):
        db.create_task(run, "independent_review", "late")


def test_same_session_multiple_runs_need_unique_explicit_binding(tmp_path: Path) -> None:
    db = store(tmp_path)
    run_a, run_b = db.start_run("same"), db.start_run("same")
    a = db.begin_attempt(db.create_task(run_a, "scan", "a"))
    b = db.begin_attempt(db.create_task(run_b, "scan", "b"))
    db.bind_attempt(a, "agent", "turn")
    with pytest.raises(WorkflowError):
        db.bind_attempt(b, "agent", "turn")
    db.bind_attempt(b, "agent", "different-turn")
    assert db.ingest_observation("unknown", "SubagentStop", "agent", "turn") is False
    assert db.snapshot(run_a)["observations"] == 0


def test_session_observation_has_no_task_effect(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    attempt = db.begin_attempt(db.create_task(run, "scan", "source"))
    db.bind_attempt(attempt, "agent", "turn")
    assert db.ingest_observation("session", "Interrupt") is True
    assert db.ingest_observation("session", "SessionEnd") is True
    status = db.snapshot(run)
    assert status["observations"] == 2
    assert status["last_observation_at"] is not None
    assert status["tasks"][0]["attempts"][0]["returned"] is False
    assert status["tasks"][0]["attempts"][0]["observed_stop"] is False


def test_late_start_completes_first_attempt_binding(tmp_path: Path) -> None:
    db = store(tmp_path)
    run = db.start_run("session")
    attempt = db.begin_attempt(db.create_task(run, "scan", "source"))
    db.bind_attempt(attempt, "agent")
    db.ingest_observation("session", "SubagentStart", "agent", "turn")
    observed = db.snapshot(run)["tasks"][0]["attempts"][0]
    assert observed["turn_id"] == "turn"
    assert observed["observed_start"] is True
