---
name: keep-calm-and-yolo-on
description: >-
  Orchestrate lightweight, reviewed development of a complex repository feature through
  scoped requirements, proportionate planning, serial implementation, P0/P1 review, authorized
  local task commits, and final acceptance. Always use when explicitly invoked, within the requested
  deliverable. Auto-trigger only for current feature design or implementation involving a material
  migration, compatibility-sensitive
  public interface, authentication, privacy, trust boundary, paid or irreversible effect, complex
  concurrency, distributed or offline synchronization, or at least two of: dependent subsystems,
  architectural tradeoffs, three or more coherent commits, or cross-layer or cross-platform tests.
  Future platform intentions alone do not trigger this workflow. Do not auto-trigger for directory
  scaffolding, diagnosis, status, review-only work, routine operations, localized fixes,
  mechanical refactors, or simple UI, configuration, documentation, or dependency changes.
---

# Keep calm and YOLO on

## Scope and authority

First identify the current deliverable and depth: advice, directory scaffold, design, prototype,
or working feature. Show a concrete example of the output and state when it is complete.
Future intentions are context, not current tasks; "continue" preserves the agreed scope.
Agent-proposed additions must be explicit, not silently recast as user requirements.

For advice, feasibility, design, review, or plan-only requests, stop at the requested output;
none authorizes implementation or commits. Directory scaffolding uses a lightweight path:
create the agreed directories and brief documentation, inspect them, and stop. Do not require
implementation subagents, functional tests, or independent code review for directory-only work.
For complex implementation, use the serial task loop and final gate below.

Requirements, architecture, and plan are thinking stages, not three mandatory confirmation
rounds. Existing authorization can cover multiple stages. Resolve repository facts first;
ask only about material unresolved choices or scope/authority changes. Show proposed scope
expansions and their reasons explicitly. Decide low-risk reversible details and honor delegated
choices without asking again. User instructions take precedence over this workflow.

Implementation and local commits each require authorization; preserve authority already given.
Without commit authority, complete authorized implementation and verification without commits.
Do not ask again for each task covered by the accepted plan.
This workflow does not authorize push, base-branch merge, PR changes, deployment,
publication, history rewriting, or branch/worktree deletion.

## Preflight and planning

Use only the stages needed for the current deliverable; the lightweight path needs no plan file.
Read applicable instructions, relevant skills, manifests, and tests. Inspect nearby code,
Git status, branches, worktrees, and relevant history. Pin the feature baseline and required
checks/commit conventions. Preserve unrelated changes; never stage, stash, reset, clean,
overwrite, or move them. Explain the applicable path. For complex implementation, confirm the
required subagent capabilities before promising that workflow; report missing capabilities
without blocking independent authorized inspection or planning.

1. Requirements: establish the current deliverable, depth, observable acceptance, stopping
   condition, non-goals, constraints, and assumptions. Separate user requirements from agent
   proposals. Resolve material ambiguity with a concrete output example, such as a directory
   tree for a scaffold; do not redefine a scaffold as a working product.
2. Architecture: design from existing code. Include material alternatives, boundaries and
   interfaces, data/control flow, and relevant persistence, concurrency, error/recovery,
   compatibility, and verification. Exclude unrelated hardening and generic production
   readiness work. Design only to the accepted depth; resolve material choices before execution.
3. Plan: create one Markdown plan in a dedicated temporary directory; report its absolute
   path. For cross-session resumption, use a verified ignored repository-local directory.
   Record accepted requirements/architecture, implementation and commit authority,
   dependency-ordered cohesive tasks, each task's goal, modules, core changes, checks,
   commit boundary, status/hash, and final checks plus aggregate review scope.
   Each task, module, dependency, and check must serve a current requirement or explain a
   necessary prerequisite. Combine tasks when intermediate commits would be invalid. No
   estimates, staffing, generic risk registers, or release ceremony unless requested.
   Resolve missing execution authority; update statuses, hashes, and evidence as work proceeds.

Before implementation, ablate both the proposed scope and design against the user's current
goals, not merely the agent-written plan. For each element, ask which current acceptance
condition fails without it. Future convenience or architectural completeness alone is
insufficient. Remove unnecessary work and briefly explain material simplifications; do not
add a separate ablation artifact unless requested.

## Serial task loop

Use a dedicated feature branch; prefer an isolated worktree when safely useful, especially
with unrelated dirty work, concurrent user edits, or invasive changes. Only one task may
mutate the source at a time; noninterfering read-only investigation may run in parallel.
The primary agent integrates and commits. Subagents must not stage, commit, stash,
switch branches, merge, clean, or change Git refs.

For each dependency-ready task:

1. Mark in progress and pin its baseline, goal, boundaries, dependencies and acceptance.
   Verify its necessity against the current user goal. Spawn an implementation subagent with
   the task contract, plan, repository path, applicable instructions and checks;
   require implementation/testing without commits.
2. Inspect the full scoped diff, reject unrelated churn, and run focused plus required
   checks. Use a failing regression test first for non-trivial automatable behavior when
   practical; otherwise establish reproducible acceptance before implementation.
3. Self-review, then use a different read-only reviewer. Provide raw baseline/current
   identities, current user request, accepted deliverable depth and non-goals, task contract,
   full scoped diff, surrounding code and check evidence,
   not the implementer's conclusions or an intended verdict.
4. Require GO/NO-GO and substantiate every P0/P1. Verify reviewed scope and evidence,
   and unchanged source, index, refs and expected diff. A stale, malformed, incomplete,
   unverifiable, failed-tool, or state-mutating review is invalid, not GO and not a round.
   On reviewer mutation, preserve changes and stop for inspection; never auto-delete them.
5. For a valid NO-GO, reproduce blockers, send confirmed ones to a repair subagent
   (normally the implementer), and make the smallest complete fix. Reject unsupported
   assertions. Re-run checks and review the entire current task diff. Reuse the reviewer
   for continuity unless scope changed materially, a finding is disputed, or state is
   unreliable, in which case use a fresh reviewer.
6. Only the primary agent may commit, when authorized, after valid GO and all required checks
   pass, with no known P0/P1 and only task-owned changes staged. Use repository conventions,
   record completed status/hash/evidence, and continue. Without commit authority, record the
   verified task state and preserve the diff for final review.

Review scope fit before code quality: should this implementation exist at the accepted depth?
An unsupported scope expansion requires correction before GO; passing tests cannot justify it.
Review findings must not invent requirements. For necessary behavior, retain correctness and
safety checks proportional to actual risk; self-added functionality does not justify expanding
the assignment further.

Review only changed behavior plus necessary context for correctness, acceptance, data
integrity, compatibility, relevant concurrency, recovery and test adequacy.
P0 is rare catastrophic security/privacy compromise, data loss/corruption, or outage.
P1 is unmet acceptance, major/blocking regression or deterministic crash, unsafe migration,
broken required compatibility, serious reliability failure, or missing critical coverage.
P2 is a bounded edge case, noncritical coverage or maintainability issue; fix only when cheap
and in scope, otherwise retain it as follow-up. P3 is optional style/naming/polish.
Do not block on pre-existing issues, intentional behavior, speculation, style, or unrelated
security/dependency/compliance/performance programs. Each P0/P1 needs a stable ID, location
(or justified cross-cutting scope), evidence/failure path, impact, minimum fix and validation.
GO requires no P0/P1 or other blocking evidence and all required checks passing; it does
not promise absence of undiscovered defects.

After the third valid full review still finds substantiated P0/P1, stop without committing
that task. Preserve current work and earlier commits; report blockers, checks and plan status
and ask the user how to proceed. Never dilute severity or checkpoint-commit to force convergence.

If work grows disproportionate to the deliverable, a blocker recurs, or the user reports drift,
recheck scope immediately before more implementation or review. Preserve existing work;
do not delete it without authority. Track recurring blockers across task and aggregate review:
renaming a task or starting aggregate remediation does not reset the three-round limit for
the same unresolved blocker. Do not continue "final cleanup" after a scope correction.

## Final gate and changed scope

After all tasks are verified and committed when authorized, run the remaining applicable
acceptance checks. Reuse current check evidence; repeat or broaden checks only for changed
behavior, failures, or unresolved concerns. Spawn a brand-new, read-only reviewer with no
inherited conversation context for aggregate review
from feature baseline to current HEAD (including the verified uncommitted diff when applicable);
never reuse a task reviewer. Supply the current user request, accepted deliverable depth,
non-goals, contracts, plan, raw diff and actual evidence. Aggregate P0/P1 requires a new remediation
task through the same loop, then another newly spawned clean-context aggregate reviewer.
Apply the recurring-blocker limit above across these rounds.

Stop when the current deliverable, applicable acceptance checks, and required review pass.
Do not start the next product phase, add speculative build hardening, or commission further
reviews without new evidence or an explicit scope change. Installation and runtime acceptance
are required only when part of the current deliverable, not automatically for a scaffold.

Pause on material changes to accepted requirements, architecture, compatibility, migration,
risk, authority or result. Explain evidence and the smallest change, resolve only the affected
decision, update the plan, and resume without reopening settled choices.

If local integration is later requested, use $review-and-merge-branch when available.
Report outcomes, task commits, checks/evidence, resolved blockers and retained P2s,
working-tree state and remote status. Do not claim completion with required failed,
blocked or skipped checks without accepted alternative evidence. Distinguish build,
test, signing, install, runtime/UI acceptance, deployment, publication, merge and push.
