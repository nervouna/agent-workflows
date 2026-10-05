"""Fixed, offline metric cards; all calculations are performed in Python."""

import hashlib
import html
import json
from pathlib import Path

from . import StatsError


def fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}"


def token_value(value):
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1000:.1f}K"
    return fmt(value)


def render(data):
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    root = "session-stats-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]
    sections = []
    for scope, label in (("main", "主会话"), ("children", "子代理"), ("combined", "合计")):
        metrics = data["scopes"][scope]
        duration = metrics["compaction_duration_ms"]
        ttft = metrics["native_ttft_mean_ms"]
        ttft_seconds = ttft is not None and ttft > 1000
        cards = [
            ("总消耗", metrics["tokens"]["total_tokens"], "token"),
            ("端到端吞吐", metrics["end_to_end_output_tokens_per_second"], "token/s"),
            ("平均 TTFT", ttft / 1000 if ttft_seconds else ttft, "s" if ttft_seconds else "ms"),
            ("输入", metrics["tokens"]["input_tokens"], "token"),
            ("输入（缓存命中）", metrics["tokens"]["cached_input_tokens"], "token"),
            ("输出", metrics["tokens"]["output_tokens"], "token"),
            ("缓存命中", metrics["cache_hit_percent"], "%"),
            ("推理", metrics["tokens"]["reasoning_output_tokens"], "token"),
            ("推理占比", metrics["reasoning_percent"], "%"),
            ("对话轮数", metrics["turn_count"], "轮"),
            ("压缩次数", metrics["compaction_count"], "次"),
            ("压缩耗时", duration / 1000 if duration is not None else None, "s"),
        ]
        content = "".join(
            f'<div class="metric"><dt>{html.escape(name)}</dt>'
            '<dd><span class="value">'
            f"{token_value(value) if unit == 'token' else fmt(value)}</span>"
            f'<span class="unit">{unit}</span></dd></div>'
            for name, value, unit in cards
        )
        hidden = " hidden" if scope != "combined" else ""
        sections.append(
            f'<section data-scope="{scope}" aria-label="{label}"{hidden}>'
            f'<dl class="metrics">{content}</dl></section>'
        )
    result = (
        Path(__file__)
        .with_name("template.html")
        .read_text()
        .replace("ROOT_ID", root)
        .replace("SECTIONS", "\n".join(sections))
    )
    if len(result.encode()) >= 1_000_000:
        raise StatsError("Snapshot exceeds the 1 MB inline display size limit.")
    return result
