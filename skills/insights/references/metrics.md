# Metric Definitions

Read this reference before interpreting `metrics.json`. The collector uses a half-open interval: activity at `start` is included and activity at `end` is excluded. ISO dates are interpreted as local midnight in the requested IANA timezone; timestamps with offsets identify exact instants.

## Population and units

- A **root conversation** is a user-visible Codex thread without a parent thread. Root conversations are the population for per-conversation distributions.
- A **subagent conversation** has a parent thread. It is reported separately and does not inflate root-conversation averages.
- An **active conversation** has at least one turn in the window. A **new conversation** was created in the window.
- A **turn** is the app-server turn record, not an inferred exchange or task fragment. A **message** is a normalized user or assistant message within an in-window root turn.
- Activity time comes from turn timestamps. Conversation span is the difference between the earliest and latest in-window turn; it is not working time or latency.

`turns_per_conversation`, `messages_per_conversation`, and `conversation_spans_seconds` describe active root conversations. Each contains raw `values`, sample `count`, arithmetic `mean`, `median`, and linearly interpolated `p25`, `p75`, and `p90`. Empty non-token samples report zero; unavailable token samples report `null` so absence cannot be mistaken for zero.

## Activity distributions

All activity buckets use the requested timezone:

- `activity.by_hour`: in-window root turns grouped by local hour `00` through `23`.
- `activity.day_parts`: `late_night` 00:00-05:59, `morning` 06:00-11:59, `afternoon` 12:00-17:59, and `evening` 18:00-23:59.
- `activity.weekday_weekend`: Monday-Friday versus Saturday-Sunday.
- `calendar.by_date`, `calendar.by_weekday`, and `calendar.active_days`: local-date distributions of in-window root turns.

These distributions describe when turns occurred. They do not measure uninterrupted work, productivity, sleep, or response latency.

## Other deterministic dimensions

- `totals`: in-window turns and normalized user/assistant messages across active roots.
- `message_roles`: user and assistant message counts.
- `projects`: active roots grouped by the basename of their working directory; complete local paths are not exposed here.
- `sources`: active roots grouped by normalized Codex source.
- `tools`: normalized tool-call counts inside in-window root turns.
- `turn_statuses`: app-server status values for those turns.
- `conversations.subagents_active`: child conversations with an in-window turn.
- `long_tail`: the share of all turns or messages contributed by the largest `ceil(10%)` of active roots. With very small samples this can mean a single conversation, so interpret it with the sample count.

Tool names, statuses, sources, and item types may evolve. Unknown values are retained or reported in collection coverage rather than silently assigned a familiar meaning.

## Token scope and coverage

Historical per-turn token usage is not assumed available. When the window ends at collection time, the collector reads the latest cumulative usage groups for **new root conversations** only. This avoids attributing an older conversation's lifetime usage to the current window.

- `tokens.cohort` identifies this population as `new_root_conversations`.
- `tokens.totals` separates input, cached input, net-new input, output, and total tokens when supplied.
- `tokens.per_conversation` and `tokens.top_10_percent_share` use only conversations with complete total-token data.
- `tokens.models` and `tokens.reasoning_efforts` count reported usage groups, not conversations or turns.
- `tokens.coverage.<field>` gives `available`, `eligible`, and `ratio`. Always state material gaps near a token conclusion.
- `tokens.window_status == current_cumulative` means cumulative usage was eligible for the current window. `unavailable_historical_cumulative_only` means the requested historical window cannot be partitioned reliably; token values remain unavailable rather than estimated.

Never infer missing token counts from characters, messages, model names, prices, or current context limits. Never add cumulative snapshots together.

## Interpretation guardrails

Metrics establish distribution, not cause. High volume can reflect ambition, complexity, careful verification, or friction. Low volume can reflect efficiency, trivial scope, abandonment, or missing history. Read the conversations before explaining a pattern, cite the coverage and sample size that matter, and let unsupported interpretations remain open questions.
