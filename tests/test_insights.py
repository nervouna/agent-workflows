import argparse
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/insights/scripts/insights.py"
SOURCE_KINDS = {
    "cli",
    "vscode",
    "exec",
    "appServer",
    "subAgent",
    "subAgentReview",
    "subAgentCompact",
    "subAgentThreadSpawn",
    "subAgentOther",
    "unknown",
}


@pytest.fixture(scope="module")
def insights():
    spec = importlib.util.spec_from_file_location("insights_skill", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def message(role: str, text: str) -> dict:
    return {"type": f"{role}_message", "text": text}


def turn(timestamp: str, *items: dict, usage_snapshots: list[dict] | None = None) -> dict:
    return {
        "timestamp": timestamp,
        "items": list(items),
        "usage_snapshots": usage_snapshots or [],
    }


def usage_snapshot(*groups: dict) -> dict:
    # Synthetic account/usage/read threadUsage groups. Multiple snapshots for one
    # thread are cumulative updates, so only the latest snapshot may be aggregated.
    return {"groups": list(groups)}


class FakeAppServerTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.pages = {
            (False, None): {
                "data": [
                    {
                        "id": "active-root",
                        "createdAt": 1_789_000_000,
                        "parentThreadId": None,
                        "source": "exec",
                    }
                ],
                "nextCursor": "active-next",
            },
            (False, "active-next"): {
                "data": [
                    {
                        "id": "active-child",
                        "createdAt": 1_789_003_600,
                        "parentThreadId": "active-root",
                        "source": {
                            "subAgent": {
                                "thread_spawn": {
                                    "parent_thread_id": "active-root",
                                    "depth": 1,
                                }
                            }
                        },
                    }
                ],
                "nextCursor": None,
            },
            (True, None): {
                "data": [
                    {
                        "id": "archived-root",
                        "createdAt": 1_788_220_800,
                        "parentThreadId": None,
                        "source": "cli",
                    }
                ],
                "nextCursor": "archived-next",
            },
            (True, "archived-next"): {
                "data": [
                    {
                        "id": "archived-child",
                        "createdAt": 1_789_007_200,
                        "parentThreadId": "archived-root",
                        "source": {"subAgent": "review"},
                    }
                ],
                "nextCursor": None,
            },
        }

    def request(self, method: str, params: dict) -> dict:
        self.calls.append(("request", method, params))
        if method == "initialize":
            assert all(
                isinstance(params["clientInfo"].get(field), str)
                and params["clientInfo"][field].strip()
                for field in ("name", "title", "version")
            )
            assert params["capabilities"]["experimentalApi"] is True
            return {"serverInfo": {"name": "synthetic", "version": "0"}}
        if method == "thread/list":
            assert set(params["sourceKinds"]) == SOURCE_KINDS
            return self.pages[(params["archived"], params.get("cursor"))]
        if method == "thread/turns/list":
            assert params["itemsView"] == "notLoaded"
            thread_id = params["threadId"]
            return {
                "data": [
                    {
                        "id": f"turn-{thread_id}",
                        "status": "completed",
                        "startedAt": 1_789_003_600,
                        "itemsView": "notLoaded",
                        "items": [],
                    }
                ],
                "nextCursor": None,
            }
        if method == "thread/items/list":
            thread_id = params["threadId"]
            assert thread_id in {"active-root", "archived-root"}
            turn_id = params["turnId"]
            assert params["sortDirection"] == "asc"
            assert params["limit"] == 100
            return {
                "data": [
                    {
                        "turnId": turn_id,
                        "item": {
                            "id": f"user-{thread_id}",
                            "type": "userMessage",
                            "content": [{"type": "text", "text": thread_id}],
                        },
                    },
                    {
                        "turnId": turn_id,
                        "item": {
                            "id": f"agent-{thread_id}",
                            "type": "agentMessage",
                            "text": "synthetic response",
                        },
                    },
                ],
                "nextCursor": None,
            }
        if method == "account/usage/read":
            thread_id = params["threadId"]
            if thread_id == "archived-root":
                return {"threadUsage": None}
            return {
                "threadUsage": {
                    "groups": [
                        {
                            "model": "synthetic-model",
                            "reasoningEffort": "medium",
                            "inputTokens": 10,
                            "cachedInputTokens": 2,
                            "netNewInputTokens": 8,
                            "outputTokens": 5,
                            "totalTokens": 15,
                            "estimatedUsageCreditsMicros": None,
                        }
                    ]
                }
            }
        raise AssertionError(f"unexpected request: {method}")

    def notify(self, method: str, params: dict) -> None:
        self.calls.append(("notify", method, params))
        assert method == "initialized"


def test_window_root_separation_and_turn_message_counts(insights) -> None:
    threads = [
        {
            "id": "root-old",
            "parent_thread_id": None,
            "created_at": "2026-09-01T00:00:00Z",
            "turns": [
                turn(
                    "2026-09-08T23:59:59Z",
                    message("user", "outside"),
                    message("assistant", "outside"),
                ),
                turn(
                    "2026-09-09T01:00:00Z",
                    message("user", "inside"),
                    {"type": "tool_call", "name": "exec"},
                    message("assistant", "inside"),
                ),
                turn(
                    "2026-09-10T12:00:00Z",
                    message("user", "inside again"),
                ),
            ],
        },
        {
            "id": "root-new",
            "parent_thread_id": None,
            "created_at": "2026-09-09T02:00:00Z",
            "turns": [
                turn(
                    "2026-09-11T07:59:59Z",
                    message("user", "inside"),
                    message("assistant", "inside"),
                ),
                turn("2026-09-11T08:00:00Z", message("user", "end is exclusive")),
            ],
        },
        {
            "id": "child",
            "parent_thread_id": "root-old",
            "created_at": "2026-09-10T00:00:00Z",
            "turns": [
                turn(
                    "2026-09-10T01:00:00Z",
                    message("user", "delegated"),
                    message("assistant", "delegated"),
                )
            ],
        },
    ]

    report = insights.summarize_history(
        threads,
        start=datetime(2026, 9, 9, 0, 0, tzinfo=UTC),
        end=datetime(2026, 9, 11, 8, 0, tzinfo=UTC),
        timezone="Asia/Taipei",
    )

    assert report["conversations"] == {"active": 2, "new": 1, "subagents_active": 1}
    assert report["totals"]["turns"] == 3
    assert report["totals"]["messages"] == 5
    assert report["turns_per_conversation"]["values"] == [2, 1]
    assert report["messages_per_conversation"]["values"] == [3, 2]


def test_app_server_collection_pages_active_and_archived_history(insights) -> None:
    transport = FakeAppServerTransport()
    collection_time = datetime(2026, 9, 11, tzinfo=UTC)

    collection = insights.collect_from_app_server(
        transport,
        collection_time=collection_time,
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert [thread["id"] for thread in collection["threads"]] == [
        "active-root",
        "active-child",
        "archived-root",
        "archived-child",
    ]
    assert all(thread["turns"] for thread in collection["threads"])
    assert collection["threads"][0]["created_at"] == 1_789_000_000
    assert collection["threads"][0]["parent_thread_id"] is None
    assert collection["threads"][1]["parent_thread_id"] == "active-root"
    assert collection["threads"][0]["source"] == "exec"
    assert collection["threads"][1]["source"] == "subAgentThreadSpawn"
    assert collection["threads"][3]["source"] == "subAgentReview"
    assert collection["threads"][1]["turns"][0]["items"] == []
    assert collection["threads"][3]["turns"][0]["items"] == []
    assert collection["threads"][0]["turns"][0]["timestamp"] == 1_789_003_600
    assert [item["type"] for item in collection["threads"][0]["turns"][0]["items"]] == [
        "user_message",
        "assistant_message",
    ]
    assert collection["collection_time"] == collection_time.isoformat()
    assert collection["coverage"]["thread_usage"] == {
        "available": 3,
        "eligible": 4,
        "ratio": 0.75,
    }

    summary = insights.summarize_history(
        collection["threads"],
        start=datetime(2026, 9, 9, tzinfo=UTC),
        end=datetime(2026, 9, 11, tzinfo=UTC),
        timezone="Asia/Taipei",
        collection_time=collection_time,
    )
    assert summary["conversations"] == {"active": 2, "new": 1, "subagents_active": 2}

    assert [(kind, method) for kind, method, _ in transport.calls[:2]] == [
        ("request", "initialize"),
        ("notify", "initialized"),
    ]
    list_calls = [params for _, method, params in transport.calls if method == "thread/list"]
    assert [(call["archived"], call.get("cursor")) for call in list_calls] == [
        (False, None),
        (False, "active-next"),
        (True, None),
        (True, "archived-next"),
    ]
    turn_calls = [params for _, method, params in transport.calls if method == "thread/turns/list"]
    assert {call["threadId"] for call in turn_calls} == {
        "active-root",
        "active-child",
        "archived-root",
        "archived-child",
    }
    usage_calls = [
        params for _, method, params in transport.calls if method == "account/usage/read"
    ]
    assert {call["threadId"] for call in usage_calls} == {
        "active-root",
        "active-child",
        "archived-root",
        "archived-child",
    }
    item_calls = [params for _, method, params in transport.calls if method == "thread/items/list"]
    assert {call["threadId"] for call in item_calls} == {"active-root", "archived-root"}
    assert collection["coverage"]["turn_hydration"] == {
        "mode": "root_window_items_subagent_metadata_only",
        "root_items": {
            "eligible_threads": 2,
            "full_threads": 2,
            "window_turns": 2,
            "item_pages": 2,
        },
        "subagent_metadata": {"threads": 2, "window_turns": 2},
        "turn_pages": 4,
    }


class SourceOnlySubagentTransport:
    def __init__(self) -> None:
        self.item_threads: list[str] = []

    def notify(self, method: str, params: dict) -> None:
        assert method == "initialized"

    def request(self, method: str, params: dict) -> dict:
        if method == "initialize":
            return {}
        if method == "thread/list":
            if params["archived"]:
                return {"data": []}
            return {
                "data": [
                    {"id": "root", "createdAt": 100, "updatedAt": 350, "source": "vscode"},
                    {
                        "id": "review",
                        "createdAt": 100,
                        "updatedAt": 350,
                        "source": {"subAgent": "review"},
                    },
                    {
                        "id": "compact",
                        "createdAt": 100,
                        "updatedAt": 350,
                        "source": {"subAgent": "compact"},
                    },
                    {
                        "id": "guardian",
                        "createdAt": 100,
                        "updatedAt": 350,
                        "source": {"subAgent": {"other": "guardian"}},
                    },
                ]
            }
        if method == "thread/turns/list":
            thread_id = params["threadId"]
            return {
                "data": [
                    {
                        "id": f"turn-{thread_id}",
                        "startedAt": 350,
                        "status": "completed",
                        "itemsView": "notLoaded",
                        "items": [],
                    }
                ]
            }
        if method == "thread/items/list":
            self.item_threads.append(params["threadId"])
            assert params["threadId"] == "root"
            return {
                "data": [
                    {
                        "turnId": params["turnId"],
                        "item": {
                            "type": "userMessage",
                            "content": [{"type": "text", "text": "root"}],
                        },
                    }
                ]
            }
        if method == "account/usage/read":
            return {"threadUsage": None}
        raise RuntimeError(f"unexpected method {method}")


def test_source_only_subagents_are_metadata_only_without_fake_parent(insights) -> None:
    transport = SourceOnlySubagentTransport()
    collection = insights.collect_from_app_server(
        transport,
        start=datetime.fromtimestamp(300, tz=UTC),
        end=datetime.fromtimestamp(400, tz=UTC),
    )

    assert transport.item_threads == ["root"]
    assert [thread["is_subagent"] for thread in collection["threads"]] == [
        False,
        True,
        True,
        True,
    ]
    assert all(thread["parent_thread_id"] is None for thread in collection["threads"])
    assert all(thread["turns"][0]["items"] == [] for thread in collection["threads"][1:])
    summary = insights.summarize_history(
        collection["threads"],
        start=datetime.fromtimestamp(300, tz=UTC),
        end=datetime.fromtimestamp(400, tz=UTC),
        timezone="UTC",
    )
    assert summary["conversations"] == {"active": 1, "new": 0, "subagents_active": 3}
    assert collection["coverage"]["turn_hydration"]["root_items"]["full_threads"] == 1
    assert collection["coverage"]["turn_hydration"]["subagent_metadata"]["threads"] == 3


def test_cumulative_thread_usage_and_missing_coverage(insights) -> None:
    collection_time = datetime(2026, 9, 10, tzinfo=UTC)
    complete_latest = usage_snapshot(
        {
            "model": "gpt-a",
            "reasoningEffort": "high",
            "inputTokens": 180,
            "cachedInputTokens": 60,
            "netNewInputTokens": 120,
            "outputTokens": 50,
            "totalTokens": 230,
            "estimatedUsageCreditsMicros": None,
        },
        {
            "model": "gpt-b",
            "reasoningEffort": "medium",
            "inputTokens": 40,
            "cachedInputTokens": 0,
            "netNewInputTokens": 40,
            "outputTokens": 30,
            "totalTokens": 70,
            "estimatedUsageCreditsMicros": None,
        },
    )
    threads = [
        {
            "id": "complete",
            "parent_thread_id": None,
            "created_at": "2026-09-09T00:00:00Z",
            "turns": [turn("2026-09-09T01:00:00Z", message("user", "one"))],
            "usage_snapshots": [
                usage_snapshot(
                    {
                        "model": "gpt-a",
                        "reasoningEffort": "high",
                        "inputTokens": 90,
                        "cachedInputTokens": 20,
                        "netNewInputTokens": 70,
                        "outputTokens": 30,
                        "totalTokens": 120,
                    }
                ),
                complete_latest,
            ],
        },
        {
            "id": "partial",
            "parent_thread_id": None,
            "created_at": "2026-09-09T00:00:00Z",
            "turns": [turn("2026-09-09T02:00:00Z", message("user", "two"))],
            "usage_snapshots": [
                usage_snapshot(
                    {
                        "model": "gpt-a",
                        "reasoningEffort": None,
                        "inputTokens": 10,
                        "cachedInputTokens": None,
                        "netNewInputTokens": None,
                        "outputTokens": 4,
                        "totalTokens": None,
                    }
                )
            ],
        },
        {
            "id": "old-but-active",
            "parent_thread_id": None,
            "created_at": "2026-09-01T00:00:00Z",
            "turns": [turn("2026-09-09T03:00:00Z", message("user", "continued"))],
            "usage_snapshots": [
                usage_snapshot(
                    {
                        "model": "gpt-a",
                        "reasoningEffort": "high",
                        "inputTokens": 900,
                        "cachedInputTokens": 100,
                        "netNewInputTokens": 800,
                        "outputTokens": 99,
                        "totalTokens": 999,
                    }
                )
            ],
        },
    ]

    report = insights.summarize_history(
        threads,
        start=datetime(2026, 9, 9, tzinfo=UTC),
        end=datetime(2026, 9, 10, tzinfo=UTC),
        timezone="Asia/Taipei",
        collection_time=collection_time,
    )

    assert report["tokens"]["totals"] == {
        "input_tokens": 230,
        "cached_input_tokens": 60,
        "net_new_input_tokens": 160,
        "output_tokens": 84,
        "total_tokens": 300,
    }
    assert report["tokens"]["per_conversation"]["values"] == [300]
    assert report["tokens"]["cohort"] == "new_root_conversations"
    assert report["tokens"]["window_status"] == "current_cumulative"
    assert report["tokens"]["collection_time"] == collection_time.isoformat()
    assert report["tokens"]["coverage"]["total_tokens"] == {
        "available": 1,
        "eligible": 2,
        "ratio": 0.5,
    }
    assert report["tokens"]["coverage"]["input_tokens"]["ratio"] == 1.0
    assert report["tokens"]["coverage"]["cached_input_tokens"]["ratio"] == 0.5
    assert report["tokens"]["coverage"]["net_new_input_tokens"]["ratio"] == 0.5
    assert report["tokens"]["coverage"]["output_tokens"]["ratio"] == 1.0

    historical = insights.summarize_history(
        threads,
        start=datetime(2026, 9, 9, tzinfo=UTC),
        end=datetime(2026, 9, 9, 12, tzinfo=UTC),
        timezone="Asia/Taipei",
        collection_time=collection_time,
    )

    assert historical["tokens"]["totals"] == dict.fromkeys(
        (
            "input_tokens",
            "cached_input_tokens",
            "net_new_input_tokens",
            "output_tokens",
            "total_tokens",
        )
    )
    assert historical["tokens"]["per_conversation"]["values"] == []
    assert historical["tokens"]["per_conversation"]["mean"] is None
    assert historical["tokens"]["coverage"]["total_tokens"] == {
        "available": 0,
        "eligible": 2,
        "ratio": 0.0,
    }
    assert historical["tokens"]["window_status"] == "unavailable_historical_cumulative_only"


def test_summary_statistics_and_local_time_distribution(insights) -> None:
    assert insights.describe_distribution([1, 2, 3, 4]) == {
        "count": 4,
        "mean": 2.5,
        "median": 2.5,
        "p25": 1.75,
        "p75": 3.25,
        "p90": 3.7,
    }

    activity = insights.summarize_activity(
        ["2026-09-11T23:30:00Z", "2026-09-14T11:00:00Z"],
        timezone="Asia/Taipei",
    )

    assert activity["by_hour"] == {"07": 1, "19": 1}
    assert activity["day_parts"] == {"morning": 1, "evening": 1}
    assert activity["weekday_weekend"] == {"weekday": 1, "weekend": 1}


def test_redaction_is_recursive_and_does_not_mutate_input(insights) -> None:
    source = {
        "cwd": "/Users/example/Private/project",
        "message": (
            "Read /Users/example/Private/notes.txt with sk-proj-SYNTHETIC1234567890 "
            "and Authorization: Bearer eySYNTHETIC.payload.signature"
        ),
        "authorization": "Bearer synthetic-authorization-value",
        "github": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
        "password": "synthetic-password-value",
        "nested": ["safe", {"token": "synthetic-value-to-redact"}],
        "client_secret": "synthetic-client-secret-value",
    }

    redacted = insights.redact_data(source, home=Path("/Users/example"))

    assert source["cwd"].startswith("/Users/example/")
    assert redacted["cwd"] == "~/Private/project"
    serialized = repr(redacted)
    assert "/Users/example" not in serialized
    assert "SYNTHETIC1234567890" not in serialized
    assert "synthetic-authorization-value" not in serialized
    assert "eySYNTHETIC.payload.signature" not in serialized
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij" not in serialized
    assert "synthetic-password-value" not in serialized
    assert "synthetic-client-secret-value" not in serialized
    assert serialized.count("[REDACTED]") >= 6


def test_report_path_never_overwrites_an_existing_file(insights, tmp_path: Path) -> None:
    base = tmp_path / "Codex Insights 2026-09-05 to 2026-09-11.html"
    base.write_text("first", encoding="utf-8")
    timestamped = tmp_path / "Codex Insights 2026-09-05 to 2026-09-11 093012.html"
    timestamped.write_text("second", encoding="utf-8")

    result = insights.next_report_path(
        tmp_path,
        start_date="2026-09-05",
        end_date="2026-09-11",
        now=datetime(2026, 9, 11, 9, 30, 12, tzinfo=UTC),
    )

    assert result == tmp_path / "Codex Insights 2026-09-05 to 2026-09-11 093012-2.html"
    assert base.read_text(encoding="utf-8") == "first"
    assert timestamped.read_text(encoding="utf-8") == "second"


def test_html_is_self_contained_and_escapes_model_content(insights) -> None:
    hostile = '<script>alert("synthetic")</script><img src="https://example.invalid/x">'

    html = insights.render_html(
        metrics={"conversations": {"active": 2}},
        analysis=hostile,
        title="Codex Insights <sample>",
    )

    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert hostile not in html
    assert "Codex Insights &lt;sample&gt;" in html
    csp = re.search(
        r'<meta[^>]+http-equiv="Content-Security-Policy"[^>]+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    assert csp is not None
    assert "default-src 'none'" in csp.group(1)
    assert "style-src 'unsafe-inline'" in csp.group(1)
    assert re.search(r"<(?:link|iframe)\b", html, re.IGNORECASE) is None
    assert re.search(r"<(?:object|embed)\b", html, re.IGNORECASE) is None
    assert re.search(r"(?:src|href)=[\"']https?://", html, re.IGNORECASE) is None
    assert re.search(r"@import|url\(\s*[\"']?https?://", html, re.IGNORECASE) is None
    assert re.search(r"\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(", html, re.IGNORECASE) is None


def test_html_body_presents_computed_dimensions_before_raw_json(insights) -> None:
    metrics = {
        "conversations": {"active": 2, "new": 1},
        "totals": {"turns": 4, "messages": 8},
        "calendar": {
            "active_days": 1,
            "by_date": {"2099-01-02": 4},
            "by_weekday": {"weekday-unique": 4},
        },
        "projects": {"ProjectUnique": 2},
        "tools": {"ToolUnique": 3},
        "sources": {"SourceUnique": 2},
        "long_tail": {"top_10_percent_turn_share": 0.75},
        "tokens": {
            "per_conversation": {"mean": 123, "median": 123},
            "coverage": {"total_tokens": {"available": 1, "eligible": 2}},
            "models": {"ModelUnique": 1},
            "reasoning_efforts": {"EffortUnique": 1},
            "window_status": "current_cumulative",
        },
    }

    rendered = insights.render_html(metrics=metrics, analysis="Synthetic", title="Insights")
    visible_body = rendered.split("<details>", maxsplit=1)[0]

    assert '<html lang="zh-Hans">' in rendered
    for heading in ("每日活动", "星期分布", "项目", "工具", "来源", "模型", "推理强度", "长尾"):
        assert heading in visible_body
    for value in (
        "2099-01-02",
        "weekday-unique",
        "ProjectUnique",
        "ToolUnique",
        "SourceUnique",
        "ModelUnique",
        "EffortUnique",
        "75%",
    ):
        assert value in visible_body


@pytest.mark.parametrize(
    ("coverage", "share", "expected", "unexpected"),
    [
        (
            {"available": 1, "eligible": 2, "ratio": 0.5},
            0.99,
            "token（本期新建根对话，1/2 有数据）</dt><dd>覆盖不足",
            "99%",
        ),
        (
            {"available": 2, "eligible": 2, "ratio": 1.0},
            0.8,
            "token（本期新建根对话，2/2 有数据）</dt><dd>80%",
            "覆盖不足",
        ),
    ],
)
def test_token_long_tail_respects_new_root_coverage(
    insights, coverage: dict, share: float, expected: str, unexpected: str
) -> None:
    metrics = {
        "long_tail": {"top_10_percent_turn_share": 0.5},
        "tokens": {
            "per_conversation": {"mean": 100},
            "coverage": {"total_tokens": coverage},
            "top_10_percent_share": share,
        },
    }

    rendered = insights.render_html(metrics=metrics, analysis="Synthetic", title="Insights")
    visible_body = rendered.split("<details>", maxsplit=1)[0]
    assert expected in visible_body
    assert unexpected not in visible_body


def test_final_report_is_written_owner_only(insights, tmp_path: Path) -> None:
    output = tmp_path / "insights.html"

    insights.write_report(output, "<!doctype html><title>Synthetic</title>")

    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_render_cli_defaults_to_home_desktop(tmp_path: Path) -> None:
    home = tmp_path / "home"
    desktop = home / "Desktop"
    desktop.mkdir(parents=True)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"conversations": {"active": 1}}), encoding="utf-8")
    analysis = tmp_path / "analysis.md"
    analysis.write_text("A synthetic observation.", encoding="utf-8")
    environment = os.environ.copy()
    environment["HOME"] = str(home)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "render",
            "--metrics",
            str(metrics),
            "--analysis",
            str(analysis),
            "--start-date",
            "2026-09-05",
            "--end-date",
            "2026-09-11",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    reports = list(desktop.glob("Codex Insights 2026-09-05 to 2026-09-11*.html"))
    assert result.returncode == 0, result.stderr
    assert len(reports) == 1
    assert stat.S_IMODE(reports[0].stat().st_mode) == 0o600


def test_temporary_history_directory_is_removed_after_failure(insights, tmp_path: Path) -> None:
    created: Path | None = None

    with (
        pytest.raises(RuntimeError, match="synthetic failure"),
        insights.temporary_history_directory(parent=tmp_path) as directory,
    ):
        created = directory
        (directory / "normalized.json").write_text("synthetic", encoding="utf-8")
        raise RuntimeError("synthetic failure")

    assert created is not None
    assert not created.exists()


def test_temporary_history_directory_is_removed_after_success(insights, tmp_path: Path) -> None:
    with insights.temporary_history_directory(parent=tmp_path) as directory:
        created = directory
        (directory / "normalized.json").write_text("synthetic", encoding="utf-8")

    assert not created.exists()


class WindowedTransport:
    def __init__(
        self,
        *,
        invalid_turn: bool = False,
        outside_summary: bool = False,
        turns_unsupported: bool = False,
        items_unsupported: bool = False,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.invalid_turn = invalid_turn
        self.outside_summary = outside_summary
        self.turns_unsupported = turns_unsupported
        self.items_unsupported = items_unsupported

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def notify(self, method: str, params: dict) -> None:
        self.calls.append((method, params))

    def request(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        if method == "initialize":
            assert params["capabilities"] == {"experimentalApi": True}
            return {}
        if method == "thread/list":
            if params["archived"]:
                return {"data": [], "nextCursor": None}
            return {
                "data": [
                    {
                        "id": "before",
                        "createdAt": 100,
                        "updatedAt": 200,
                        "source": "cli",
                    },
                    {
                        "id": "inside",
                        "createdAt": 100,
                        "updatedAt": 350,
                        "source": "cli",
                    },
                    {
                        "id": "after",
                        "createdAt": 500,
                        "updatedAt": 600,
                        "source": "cli",
                    },
                ],
                "nextCursor": None,
            }
        if method == "thread/turns/list":
            if self.turns_unsupported:
                raise RuntimeError("unsupported method -32601")
            assert params["itemsView"] == "notLoaded"
            if self.invalid_turn:
                return {"data": [{"id": "missing-time", "itemsView": "notLoaded"}]}
            if params.get("cursor") is None:
                return {
                    "data": [
                        {
                            "id": "before-turn",
                            "startedAt": 250,
                            "status": "completed",
                            "itemsView": "summary" if self.outside_summary else "notLoaded",
                            "items": (
                                [{"type": "agentMessage", "text": "sk-SYNTHETIC-SENSITIVE"}]
                                if self.outside_summary
                                else []
                            ),
                        },
                        {
                            "id": "inside-turn",
                            "startedAt": 350,
                            "status": "completed",
                            "itemsView": "notLoaded",
                            "items": [],
                        },
                    ],
                    "nextCursor": "next-turn-page",
                }
            return {
                "data": [
                    {
                        "id": "after-turn",
                        "startedAt": 450,
                        "status": "completed",
                        "itemsView": "notLoaded",
                        "items": [],
                    }
                ],
                "nextCursor": None,
            }
        if method == "thread/items/list":
            if self.items_unsupported:
                raise RuntimeError("unsupported method -32601")
            assert params["turnId"] == "inside-turn"
            assert params["sortDirection"] == "asc"
            assert params["limit"] == 100
            if params.get("cursor") is None:
                return {
                    "data": [
                        {
                            "turnId": "inside-turn",
                            "item": {
                                "type": "userMessage",
                                "content": [{"type": "text", "text": "inside"}],
                            },
                        }
                    ],
                    "nextCursor": "next-item-page",
                }
            return {
                "data": [
                    {
                        "turnId": "inside-turn",
                        "item": {"type": "agentMessage", "text": "response"},
                    }
                ],
                "nextCursor": None,
            }
        if method == "account/usage/read":
            return {"threadUsage": None}
        raise RuntimeError("unsupported method")


def test_collection_pages_full_turns_and_clips_window(insights) -> None:
    transport = WindowedTransport()
    collection = insights.collect_from_app_server(
        transport,
        start=datetime.fromtimestamp(300, tz=UTC),
        end=datetime.fromtimestamp(400, tz=UTC),
        collection_time=datetime.fromtimestamp(400, tz=UTC),
    )

    assert [thread["id"] for thread in collection["threads"]] == ["inside"]
    assert [turn["id"] for turn in collection["threads"][0]["turns"]] == ["inside-turn"]
    turn_calls = [params for method, params in transport.calls if method == "thread/turns/list"]
    assert [call.get("cursor") for call in turn_calls] == [None, "next-turn-page"]
    assert all(call["itemsView"] == "notLoaded" for call in turn_calls)
    item_calls = [params for method, params in transport.calls if method == "thread/items/list"]
    assert [call.get("cursor") for call in item_calls] == [None, "next-item-page"]
    assert {call["turnId"] for call in item_calls} == {"inside-turn"}
    assert not any(
        params.get("threadId") in {"before", "after"}
        for method, params in transport.calls
        if method in {"thread/turns/list", "thread/read"}
    )

    summary = insights.summarize_history(
        collection["threads"],
        start=datetime.fromtimestamp(300, tz=UTC),
        end=datetime.fromtimestamp(400, tz=UTC),
        timezone="UTC",
    )
    assert summary["conversation_spans_seconds"]["values"] == [0]


def test_incomplete_turn_metadata_and_unsupported_items_fail_closed(insights) -> None:
    with pytest.raises(RuntimeError, match="turn metadata"):
        insights.collect_from_app_server(
            WindowedTransport(invalid_turn=True),
            start=datetime.fromtimestamp(300, tz=UTC),
            end=datetime.fromtimestamp(400, tz=UTC),
        )
    with pytest.raises(RuntimeError, match="thread/items/list"):
        insights.collect_from_app_server(
            WindowedTransport(items_unsupported=True),
            start=datetime.fromtimestamp(300, tz=UTC),
            end=datetime.fromtimestamp(400, tz=UTC),
        )


def test_outside_summary_with_items_fails_without_item_reads_and_cleans(
    insights, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = WindowedTransport(outside_summary=True)
    monkeypatch.setattr(insights, "AppServerTransport", lambda: transport)
    work = tmp_path / "outside-summary"
    with pytest.raises(RuntimeError, match="itemsView"):
        insights._collect_command(
            argparse.Namespace(
                work_dir=work,
                start="1970-01-01T00:05:00Z",
                end="1970-01-01T00:06:40Z",
                timezone="UTC",
            )
        )
    assert not any(method == "thread/items/list" for method, _ in transport.calls)
    assert not work.exists()


@pytest.mark.parametrize(
    ("view", "items"),
    [
        (None, []),
        ("summary", []),
        ("full", []),
        ("notLoaded", [{"type": "agentMessage", "text": "synthetic"}]),
    ],
)
def test_turn_metadata_requires_not_loaded_and_empty(insights, view, items) -> None:
    class InvalidShapeTransport(WindowedTransport):
        def request(self, method: str, params: dict) -> dict:
            response = super().request(method, params)
            if method == "thread/turns/list" and response.get("data"):
                turn = response["data"][0]
                if view is None:
                    turn.pop("itemsView", None)
                else:
                    turn["itemsView"] = view
                turn["items"] = items
            return response

    transport = InvalidShapeTransport()
    with pytest.raises(RuntimeError, match="itemsView|non-empty"):
        insights.collect_from_app_server(
            transport,
            start=datetime.fromtimestamp(300, tz=UTC),
            end=datetime.fromtimestamp(400, tz=UTC),
        )
    assert not any(method == "thread/items/list" for method, _ in transport.calls)


@pytest.mark.parametrize("unsupported", ["turns", "items"])
def test_unsupported_narrow_history_method_cleans_collect_directory(
    insights,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsupported: str,
) -> None:
    transport = WindowedTransport(
        turns_unsupported=unsupported == "turns",
        items_unsupported=unsupported == "items",
    )
    monkeypatch.setattr(insights, "AppServerTransport", lambda: transport)
    work = tmp_path / unsupported
    with pytest.raises(RuntimeError, match=f"thread/{unsupported}"):
        insights._collect_command(
            argparse.Namespace(
                work_dir=work,
                start="1970-01-01T00:05:00Z",
                end="1970-01-01T00:06:40Z",
                timezone="UTC",
            )
        )
    assert not work.exists()
    assert not any(method == "thread/read" for method, _ in transport.calls)


def test_token_unknown_is_not_rendered_as_zero(insights) -> None:
    report = insights.summarize_history(
        [],
        start=datetime(2026, 9, 1, tzinfo=UTC),
        end=datetime(2026, 9, 2, tzinfo=UTC),
        timezone="UTC",
        collection_time=datetime(2026, 9, 3, tzinfo=UTC),
    )
    assert report["tokens"]["totals"]["total_tokens"] is None
    assert report["tokens"]["per_conversation"]["mean"] is None
    rendered = insights.render_html(metrics=report, analysis="Synthetic", title="Insights")
    assert "平均 token（本期新建根对话，0/0 有数据；历史窗口不可用）" in rendered
    assert "<strong>未知</strong>" in rendered


class NullTransport:
    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_collect_failure_cleans_only_directory_it_created(
    insights, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(insights, "AppServerTransport", NullTransport)
    monkeypatch.setattr(
        insights,
        "collect_from_app_server",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
    )
    created = tmp_path / "created"
    args = argparse.Namespace(
        work_dir=created,
        start=None,
        end=None,
        timezone="UTC",
    )
    with pytest.raises(RuntimeError, match="synthetic failure"):
        insights._collect_command(args)
    assert not created.exists()

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(RuntimeError, match="synthetic failure"):
        insights._collect_command(argparse.Namespace(**{**vars(args), "work_dir": existing}))
    assert existing.is_dir()
    assert list(existing.iterdir()) == []


def test_collect_postprocessing_failure_removes_owned_directory(
    insights, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(insights, "AppServerTransport", NullTransport)
    monkeypatch.setattr(
        insights,
        "collect_from_app_server",
        lambda *_args, **_kwargs: {
            "threads": [],
            "coverage": {},
            "collection_time": datetime.now(UTC).isoformat(),
        },
    )
    monkeypatch.setattr(
        insights,
        "summarize_history",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("postprocess failed")),
    )
    work = tmp_path / "postprocess"
    with pytest.raises(RuntimeError, match="postprocess failed"):
        insights._collect_command(
            argparse.Namespace(work_dir=work, start=None, end=None, timezone="UTC")
        )
    assert not work.exists()


def test_render_failure_finally_cleans_and_cleanup_retry_is_safe(insights, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    metrics = work / "metrics.json"
    metrics.write_text("{}", encoding="utf-8")
    insights.write_work_sentinel(work, owned=True)
    args = argparse.Namespace(
        metrics=metrics,
        analysis=work / "missing-analysis.md",
        output_dir=tmp_path / "reports",
        start_date="2026-09-01",
        end_date="2026-09-02",
        cleanup_work_dir=work,
    )
    with pytest.raises(FileNotFoundError):
        insights._render_command(args)
    assert not work.exists()
    assert insights.cleanup_work_directory(work) is False


def test_render_success_cleans_owned_work_directory(insights, tmp_path: Path) -> None:
    work = tmp_path / "work-success"
    work.mkdir()
    metrics = work / "metrics.json"
    metrics.write_text(json.dumps({"conversations": {"active": 1}}), encoding="utf-8")
    analysis = work / "analysis.md"
    analysis.write_text("Synthetic", encoding="utf-8")
    insights.write_work_sentinel(work, owned=True)
    result = insights._render_command(
        argparse.Namespace(
            metrics=metrics,
            analysis=analysis,
            output_dir=tmp_path / "reports",
            start_date="2026-09-01",
            end_date="2026-09-02",
            cleanup_work_dir=work,
        )
    )
    assert result == 0
    assert not work.exists()
    assert len(list((tmp_path / "reports").glob("*.html"))) == 1


def test_render_write_failure_still_cleans(insights, tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work-write-failure"
    work.mkdir()
    metrics = work / "metrics.json"
    metrics.write_text("{}", encoding="utf-8")
    analysis = work / "analysis.md"
    analysis.write_text("Synthetic", encoding="utf-8")
    insights.write_work_sentinel(work, owned=True)
    monkeypatch.setattr(
        insights,
        "write_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("write failed")),
    )
    with pytest.raises(OSError, match="write failed"):
        insights._render_command(
            argparse.Namespace(
                metrics=metrics,
                analysis=analysis,
                output_dir=tmp_path / "reports",
                start_date="2026-09-01",
                end_date="2026-09-02",
                cleanup_work_dir=work,
            )
        )
    assert not work.exists()
