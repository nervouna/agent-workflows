# Report Style

Write a personal retrospective that feels as if it came from a perceptive collaborator who remembers the work, not from an audit template. Match the user's language. Prefer a few developed observations over exhaustive coverage.

## Shape

Open with a short, specific impression of the period. Let two to four titled passages carry the main argument in connected prose. Weave numbers into those passages only when they sharpen the point; the rendered report already presents the fixed distributions.

Use concrete moments from the history as evidence without reproducing whole exchanges. Include counterexamples when they materially change the conclusion. A small surprising fact is welcome when it is supported by the metrics or history and reveals something useful rather than merely sounding clever.

End naturally. If a change is worth trying, offer no more than three actions, each small enough to test in later work. Zero actions and “nothing new this period” are legitimate outcomes.

## Voice

- Favor paragraphs over stacked bullets, scorecards, and repeated labeled blocks.
- Use direct, varied sentences. Avoid recurring constructions such as “不是……而是……”, “真正的问题是……”, “这意味着……”, or their English equivalents.
- Do not mechanically split every observation into fact, judgment, hypothesis, limitation, and implication. Express uncertainty where it actually belongs.
- Give headings substantive names that state the observation. Avoid placeholders such as “Key Finding 1”, “Efficiency Analysis”, or “Summary”.
- Avoid management-consulting filler, motivational praise, synthetic drama, and claims to know the user's intent beyond the evidence.
- Do not narrate every chart. Select the few relationships that deserve interpretation.

Exact quantities must come from `metrics.json`. Use natural approximations only as prose around those facts, never as replacements for coverage or sample sizes. Describe elapsed spans as spans, tool calls as calls, and tokens as the documented token cohort; do not rename them as time spent, effort, productivity, or cost.

The renderer supports plain paragraphs, `#` through `###` headings, and simple `-` or `*` lists. Do not rely on raw HTML, Markdown links, tables, bold, or other rich Markdown in the analysis body.
