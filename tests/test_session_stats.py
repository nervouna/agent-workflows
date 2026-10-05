"""Public snapshot boundary: accounting, privacy, target routing and packaged execution."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

A = "01a10981-8d52-79f3-9ddb-8afcd28a8ecc"
B = "01a10981-8d52-79f3-9ddb-8afcd28a8ecd"
SECRET = "PRIVATE-CONVERSATION-DO-NOT-EXPORT"


def event(kind, **payload):
    return {
        "timestamp": "2026-10-05T01:00:10Z",
        "type": "event_msg",
        "payload": {"type": kind, **payload},
    }


def fixture_home(tmp_path, records, children=None):
    home = tmp_path / "home"
    home.mkdir()
    db = sqlite3.connect(home / "state_5.sqlite")
    db.execute(
        "CREATE TABLE threads(id TEXT PRIMARY KEY, rollout_path TEXT, "
        "history_mode TEXT, source TEXT)"
    )
    db.execute(
        "CREATE TABLE thread_spawn_edges(parent_thread_id TEXT, child_thread_id TEXT, status TEXT)"
    )
    for thread, rows in {A: records, **(children or {})}.items():
        path = home / f"{thread}.jsonl"
        meta = {
            "type": "session_meta",
            "timestamp": "2026-10-05T01:00:00Z",
            "payload": {"id": thread},
        }
        path.write_text("\n".join(json.dumps(row) for row in [meta, *rows]) + "\n")
        db.execute("INSERT INTO threads VALUES(?,?,?,?)", (thread, str(path), "full", "cli"))
        if thread != A:
            db.execute("INSERT INTO thread_spawn_edges VALUES(?,?,?)", (A, thread, "completed"))
    db.commit()
    db.close()
    return home


def run(home, out, *args, script=None):
    command = (
        [sys.executable, "-I", "-S", str(script)]
        if script
        else [sys.executable, "-m", "codex_maintenance.session_stats"]
    )
    return subprocess.run(
        [
            *command,
            "snapshot",
            "--codex-home",
            str(home),
            "--output-dir",
            str(out),
            "--at",
            "2026-10-05T02:00:00Z",
            *args,
        ],
        env={**os.environ, "CODEX_THREAD_ID": A},
        capture_output=True,
        text=True,
    )


def usage(thread=A, response="r1", turn="t1", **changes):
    values = dict(
        input_tokens=100,
        cached_input_tokens=60,
        cache_write_input_tokens=0,
        output_tokens=20,
        reasoning_output_tokens=5,
        total_tokens=120,
    )
    values.update(changes)
    return {
        "timestamp": "2026-10-05T01:00:10Z",
        "type": "token_usage_record",
        "payload": {"thread_id": thread, "turn_id": turn, "response_id": response, "usage": values},
    }


def completed(turn="t1"):
    return [
        event("task_started", turn_id=turn, started_at=1791162000),
        event(
            "task_complete",
            turn_id=turn,
            started_at=1791162000,
            completed_at=1791162010,
            duration_ms=10000,
            time_to_first_token_ms=2000,
        ),
    ]


def read_result(result):
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    return json.loads(Path(receipt["json_path"]).read_text()), Path(
        receipt["html_path"]
    ).read_text()


def test_snapshot_accounts_once_and_separates_children_without_exporting_content(tmp_path):
    records = [
        *completed(),
        usage(),
        usage(),
        event("user_message", message=SECRET),
        event("token_count", info={"total_token_usage": {"total_tokens": 9999}}),
    ]
    home = fixture_home(tmp_path, records, {B: [*completed(), usage(B)]})
    data, html = read_result(run(home, tmp_path / "out"))
    main = data["scopes"]["main"]
    assert main["tokens"]["total_tokens"] == 120
    assert main["tokens"]["cached_input_tokens"] == 60
    assert main["turn_count"] == 1
    assert main["native_ttft_mean_ms"] == 2000
    assert main["end_to_end_output_tokens_per_second"] == 2
    assert data["scopes"]["combined"]["tokens"]["total_tokens"] == 240
    assert SECRET not in json.dumps(data) + html
    assert "</html>" not in html


def test_target_forms_fail_closed_and_snapshot_is_reproducible(tmp_path):
    home = fixture_home(tmp_path, [*completed(), usage()])
    outputs = []
    for target in [A, f"codex://threads/{A}", f"[@任意标题](thread://{A}?hostId=local)"]:
        data, html = read_result(run(home, tmp_path / str(len(outputs)), "--target", target))
        outputs.append((data, html))
    assert outputs[0] == outputs[1] == outputs[2]
    for args in [
        ("--target", f"thread://{A}?hostId=remote"),
        ("--target", "bad"),
        ("--target", A, "--target", B),
    ]:
        result = run(home, tmp_path / "bad", *args)
        assert result.returncode != 0
        assert not (tmp_path / "bad").exists()
        assert SECRET not in result.stderr


def test_incomplete_turn_and_missing_measurements_are_not_zero(tmp_path):
    home = fixture_home(tmp_path, [event("task_started", turn_id="open"), usage(turn="open")])
    data, _ = read_result(run(home, tmp_path / "out"))
    scope = data["scopes"]["main"]
    assert scope["native_ttft_mean_ms"] is None
    assert scope["end_to_end_output_tokens_per_second"] is None
    assert data["turns"][0]["status"] == "in_progress"
    assert data["turns"][0]["duration_ms"] is None


def test_packaged_cli_runs_without_checkout_imports(tmp_path):
    from codex_maintenance.session_stats.package import package_plugin

    home = fixture_home(tmp_path, [*completed(), usage()])
    root = package_plugin(tmp_path / "plugin")
    data, _ = read_result(run(home, tmp_path / "out", script=root / "scripts" / "session_stats.py"))
    assert data["target_id"] == A


def test_fork_excludes_retimed_parent_history_but_keeps_owned_turns(tmp_path):
    inherited = completed("parent-turn")
    for row in inherited:
        row["payload"]["started_at"] -= 600
        if "completed_at" in row["payload"]:
            row["payload"]["completed_at"] -= 600
    untimed_inherited = completed("untimed-parent")
    for row in untimed_inherited:
        row["payload"].pop("started_at", None)
        row["payload"].pop("completed_at", None)
        row["timestamp"] = "2026-10-05T01:00:00Z"
    parent_meta = {
        "timestamp": "2026-10-05T01:00:00Z",
        "type": "session_meta",
        "payload": {"id": B},
    }
    message = event(
        "item_completed",
        thread_id=A,
        turn_id="t1",
        item={"type": "UserMessage", "id": "message1", "content": SECRET},
    )
    home = fixture_home(
        tmp_path,
        [parent_meta, *inherited, *untimed_inherited, *completed(), usage(), message, message],
    )
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    data, html = read_result(run(home, tmp_path / "out"))
    assert data["scopes"]["main"]["turn_count"] == 1
    assert data["turns"][0]["turn_id"] == "t1"
    assert data["threads"][0]["user_message_count"] == 1
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before
    assert SECRET not in html + json.dumps(data)


def test_legacy_cumulative_is_not_summed_and_malformed_data_is_private(tmp_path):
    home = fixture_home(
        tmp_path,
        [
            *completed(),
            event("token_count", info={"total_token_usage": {"total_tokens": 100}}),
            event("token_count", info={"total_token_usage": {"total_tokens": 150}}),
        ],
    )
    with (home / f"{A}.jsonl").open("a") as f:
        f.write(SECRET + "\n")
    data, html = read_result(run(home, tmp_path / "out"))
    assert data["scopes"]["main"]["tokens"]["total_tokens"] == 150
    assert data["scopes"]["main"]["end_to_end_output_tokens_per_second"] is None
    assert "legacy_usage_incomplete" in data["threads"][0]["warnings"]
    assert "malformed_record" in data["threads"][0]["warnings"]
    assert SECRET not in html + json.dumps(data)


def test_conflicting_response_identity_and_invalid_totals_do_not_inflate_usage(tmp_path):
    home = fixture_home(
        tmp_path,
        [
            *completed(),
            usage(),
            *completed("t2"),
            usage(turn="t2"),
            usage(response="invalid", total_tokens=500),
        ],
    )
    data, _ = read_result(run(home, tmp_path / "out"))
    assert data["scopes"]["main"]["tokens"]["total_tokens"] == 120
    assert "conflicting_usage_record" in data["threads"][0]["warnings"]
    assert "invalid_usage_record" in data["threads"][0]["warnings"]


def test_future_descendants_and_events_are_excluded_by_cutoff(tmp_path):
    future = usage(response="future")
    future["timestamp"] = "2026-10-05T03:00:00Z"
    home = fixture_home(tmp_path, [*completed(), usage(), future], {B: []})
    (home / f"{B}.jsonl").write_text(
        json.dumps(
            {"type": "session_meta", "timestamp": "2026-10-05T03:00:00Z", "payload": {"id": B}}
        )
        + "\n"
    )
    data, _ = read_result(run(home, tmp_path / "out"))
    assert data["scopes"]["combined"]["thread_count"] == 1
    assert data["scopes"]["main"]["tokens"]["total_tokens"] == 120


def test_unavailable_main_fails_without_artifacts_but_child_is_reported(tmp_path):
    home = fixture_home(tmp_path, [*completed(), usage()], {B: []})
    (home / f"{B}.jsonl").unlink()
    data, _ = read_result(run(home, tmp_path / "child-out"))
    assert data["threads"][1]["warnings"] == ["session_unavailable"]
    assert data["scopes"]["combined"]["tokens"]["total_tokens"] is None
    (home / f"{A}.jsonl").unlink()
    result = run(home, tmp_path / "missing-main", "--target", f"codex://threads/{A}")
    assert result.returncode != 0
    assert not (tmp_path / "missing-main").exists()
    assert not result.stdout


def test_ratios_and_compaction_are_owned_deduplicated_and_cutoff_bound(tmp_path):
    def compact(identity, thread=A, start=1000, end=3500):
        return event(
            "item_completed",
            thread_id=thread,
            turn_id="t1",
            started_at_ms=start,
            completed_at_ms=end,
            item={"type": "ContextCompaction", "id": identity},
        )

    first = compact("c1")
    future = compact("future")
    future["timestamp"] = "2026-10-05T03:00:00Z"
    home = fixture_home(
        tmp_path,
        [*completed(), usage(), first, first, compact("inherited", B), future],
        {
            B: [
                *completed(),
                usage(
                    B,
                    input_tokens=900,
                    cached_input_tokens=90,
                    output_tokens=80,
                    reasoning_output_tokens=40,
                    total_tokens=980,
                ),
                compact("c1", B, 4000, 5500),
            ]
        },
    )
    data, _ = read_result(run(home, tmp_path / "out"))
    main, combined = data["scopes"]["main"], data["scopes"]["combined"]
    assert main["cache_hit_percent"] == 60
    assert main["reasoning_percent"] == 25
    assert main["compaction_count"] == 1
    assert main["compaction_duration_ms"] == 2500
    assert combined["cache_hit_percent"] == 15
    assert combined["reasoning_percent"] == 45
    assert combined["compaction_count"] == 2
    assert combined["compaction_duration_ms"] == 4000


def test_missing_compaction_timing_and_zero_denominators_remain_unknown(tmp_path):
    home = fixture_home(
        tmp_path,
        [
            *completed(),
            usage(
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                reasoning_output_tokens=0,
                total_tokens=0,
            ),
            event(
                "item_completed",
                thread_id=A,
                turn_id="t1",
                item={"type": "ContextCompaction", "id": "missing-time"},
            ),
        ],
    )
    data, _ = read_result(run(home, tmp_path / "out"))
    main = data["scopes"]["main"]
    assert main["cache_hit_percent"] is None
    assert main["reasoning_percent"] is None
    assert main["compaction_count"] == 1
    assert main["compaction_duration_ms"] is None
