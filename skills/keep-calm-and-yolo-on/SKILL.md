---
name: keep-calm-and-yolo-on
description: >-
  Orchestrate lightweight, reviewed development of a complex repository feature through
  requirements, architecture, an executable plan, serial implementation, P0/P1 review, authorized
  local task commits, and final verification. Always use when explicitly invoked. Auto-trigger only
  for feature design or implementation involving a material migration, compatibility-sensitive
  public interface, authentication, privacy, trust boundary, paid or irreversible effect, complex
  concurrency, distributed or offline synchronization, or at least two of: dependent subsystems,
  architectural tradeoffs, three or more coherent commits, or cross-layer or cross-platform tests.
  Do not auto-trigger for diagnosis, status, review-only work, routine operations, localized fixes,
  mechanical refactors, or simple UI, configuration, documentation, or dependency changes.
---

# Keep calm and YOLO on

## Outcome Contract

Run a lightweight complex-feature workflow that prevents architectural drift and known serious
defects without turning development into a general audit. Use only three routine confirmation gate
types: the requirements contract, the architecture design, and the executable plan. Combine the
last two only when no material architecture decision remains or the user explicitly requests fewer
checkpoints. Material-change reapproval and circuit-breaker escalation are exceptional returns to
the user, not additional routine gates.

Enter the execution phase only when implementation and local task commits are authorized by the
originating request or by an executable plan that states that delivery boundary and is approved by
the user. If implementation is authorized but local commits are not, resolve that material choice
before plan approval; if the user declines, do not enter this skill's commit loop. Once authorized,
do not request confirmation for each task. For read-only, feasibility, design, review, or plan-only
requests, stop at the requested deliverable. Pause whenever the target, scope, architecture, risk,
authority, or intended result changes materially.

Keep remote and integration actions separate. Do not push, merge into a base branch, open or merge
a pull request, delete branches or worktrees, deploy, publish, or rewrite history unless the user
explicitly requests that action.

## Preflight

1. Read every applicable `AGENTS.md`, repository guide, relevant skill, build manifest, and test
   entry point.
2. Inspect the current implementation, nearby tests, Git status, branch, worktrees, and recent
   relevant history before asking questions or proposing architecture.
3. Explain briefly why this workflow triggered. Do not use it merely because a mechanical change
   touches many files.
4. Preserve all pre-existing changes. Do not stage, commit, stash, reset, clean, overwrite, or move
   unrelated work.
5. Identify the feature baseline and the repository's required verification and commit conventions.
   If safe task commits are impossible, surface that as a material blocker before plan approval.
6. Record whether implementation and local task commits are authorized. Resolve missing authority
   before plan approval only when execution is requested. Confirm that implementation and
   independent-review subagents are available before promising the development loop; otherwise
   report the capability blocker.

## Question Interface

Ask one material decision per interaction and follow the host environment's interaction rules. Use
structured user input when it is available and appropriate, with a recommendation and concise
tradeoffs. Otherwise ask one concise free-form question.

## Phase 1: Clarify Material Requirements

Resolve facts from the repository before asking the user. Follow the question interface, do not
bundle independent decisions into a compound question, and ask only when the answer could
materially change one or more of:

- observable product behavior or acceptance criteria
- scope, non-goals, or compatibility promises
- architecture, persisted data, public interfaces, or migration behavior
- privacy, trust boundaries, paid calls, or irreversible side effects
- performance targets, platform support, or failure and recovery semantics

Do not ask about low-risk, reversible implementation choices. Decide those using repository
conventions and record the decision. When the user delegates a choice, record the delegation and
make the choice instead of asking again.

When no material ambiguity remains, present a concise requirements contract containing:

- objective and user-visible outcome
- acceptance criteria and required evidence
- in-scope behavior and explicit non-goals
- constraints, compatibility, and migration expectations
- accepted decisions and low-risk implementation assumptions
- unresolved material questions, which must be empty

Request confirmation of the contract before designing the solution. Do not edit production code in
this phase.

## Phase 2: Design the Architecture

Design from the verified current implementation rather than from a generic greenfield pattern.
Present:

- current architecture and constraints relevant to the feature
- recommended design and only the material alternatives and tradeoffs
- module boundaries, interfaces, data flow, and control flow
- persistence, migration, compatibility, concurrency, error, and recovery behavior when relevant
- verification strategy and explicit functional boundaries
- excluded work that would add complexity without helping the accepted outcome

Avoid option matrices for minor implementation choices. Do not add generic security hardening,
compliance work, dependency audits, observability programs, rollout machinery, or production
readiness gates unless the feature crosses that boundary, the repository requires it, or the user
asks for it.

Request confirmation of the architecture. Iterate on material feedback, then freeze the accepted
design as the basis for planning.

## Phase 3: Write the Executable Plan

Create a dedicated temporary directory, preferably with `mktemp -d`, and write one Markdown plan
file there. Report its absolute path. If cross-session resumption is required, use a
repository-local ignored temporary directory instead and verify that it is ignored before writing.

Use this document structure:

```markdown
# <Feature> Implementation Plan

## Accepted requirements
<Concise snapshot of the confirmed requirements contract>

## Accepted architecture
<Concise snapshot of the confirmed design and boundaries>

## Delivery boundary
- Implementation: <authorized | not authorized | not requested>
- Local task commits: <authorized | not authorized | not requested>

## Verification strategy
<Focused checks per task plus final integration or end-to-end evidence>

## Task graph

### T1: <High-cohesion task name>
- Goal:
- Dependencies:
- Affected modules:
- Core implementation:
- Tests and acceptance evidence:
- Commit boundary:
- Status: pending
- Commit: pending

## Final feature gate
- Required repository checks:
- Integration or end-to-end acceptance:
- Aggregate review scope:
```

Decompose work into high-cohesion, low-coupling tasks with explicit dependencies. Each task must be
independently verifiable and safe to commit without breaking the repository. Combine tasks when an
intermediate commit would be invalid or would require unfinished future work to satisfy its own
contract. Order tasks by dependency.

Do not add estimates, staffing assignments, RACI tables, generic risk registers, or release
ceremony unless requested. Present the plan to the user and request confirmation. Do not begin
development before approval.

After approval, update task status and commit hashes in the plan as work proceeds. Change the
accepted requirements or architecture only through the material-change procedure below.

## Phase 4: Execute One Task at a Time

Enter this phase only when the approved plan authorizes implementation and local task commits.

Use one mutable task at a time. Read-only investigation or test discovery may run in parallel when
it cannot interfere with the working tree. For a Git repository, use a dedicated feature branch and
prefer an isolated worktree when it can be created safely, especially when the existing worktree is
dirty, the user is working in parallel, or the change is invasive.

The primary agent is the integrator and owns every commit. Implementation, repair, and review
subagents must not stage, commit, stash, switch branches, merge, clean, or alter Git refs.

For each task:

1. Mark it `in_progress`, pin the current task baseline, and restate its goal, dependencies,
   boundaries, tests, and acceptance evidence.
2. Spawn an implementation subagent with the task contract, plan path, repository path, applicable
   instructions, and required checks. Instruct it to implement and test only this task without
   committing.
3. Inspect the resulting status and full scoped diff. Reject unrelated churn. Run the minimum
   sufficient focused checks and repository-required checks. Use a failing regression test first
   for non-trivial automatable logic when practical; otherwise define reproducible acceptance
   evidence before implementation.
4. Perform a focused integrator self-review, then spawn a different, read-only reviewer. Pass raw
   facts: repository and worktree paths, baseline and current identities, task contract, scoped
   diff, relevant surrounding code, and actual check results. Do not pass the implementer's
   conclusions or tell the reviewer what verdict to reach.
5. Require a structured `GO` or `NO-GO` verdict with every substantiated P0/P1 finding and optional
   non-blocking notes. Validate the review target and evidence before accepting the verdict.
   Verify that the reviewer left the source, index, refs, and expected task diff unchanged. If it
   mutated relevant state, invalidate the verdict, preserve the unexpected changes, and stop for
   inspection rather than deleting them automatically.
6. On `NO-GO`, reproduce or otherwise substantiate each blocker. Send confirmed findings to a
   repair subagent, normally the original implementer for continuity, and require the smallest
   complete fix plus focused regression evidence. Do not modify correct code merely to satisfy an
   unsupported assertion.
7. Re-run applicable checks and obtain another valid review of the complete current task diff, not
   only the previously reported findings. Reuse the read-only reviewer when continuity saves time;
   use a fresh reviewer when the scope changed materially, a finding is disputed, or reviewer state
   is unreliable.
8. Commit only after the latest valid verdict is `GO`, all required task checks pass, no known
   substantiated P0/P1 remains in scope, and the staged set contains only task-owned changes. The
   primary agent creates one local commit using repository conventions.
9. Mark the task `completed`, record the commit hash and verification evidence in the plan, and
   proceed to the next dependency-ready task.

## Review Contract

Review changed behavior and enough surrounding code to evaluate the task's acceptance criteria,
correctness, data integrity, compatibility, relevant concurrency, error and recovery paths, and
test adequacy. Keep the review risk-proportionate.

Do not treat pre-existing problems, intentional behavior, speculative concerns, style preferences,
generic hardening, or ordinary maintainability suggestions as blockers. Do not broaden a task
review into a general security, dependency, compliance, performance, or production-readiness audit
unless the changed behavior or accepted plan requires it.

Use these severities:

- `P0`: likely security or privacy compromise, unrecoverable data loss or corruption, widespread
  outage, or another catastrophic consequence. Treat P0 as rare.
- `P1`: unmet acceptance criteria, user-blocking or major correctness regression, deterministic
  crash, unsafe migration, broken required compatibility or contract, serious reliability failure,
  or failed critical regression coverage that makes the task uncommittable.
- `P2`: bounded edge case, non-critical test gap, or substantiated maintainability problem. Fix it
  when low-cost and in scope; otherwise record it as non-blocking follow-up.
- `P3`: naming, style, preference, or optional polish. Do not block on it.

Require each P0/P1 finding to include:

- stable identifier and concise title
- exact file and line, or a justified cross-cutting scope
- reproducible evidence or a concrete failure path
- user or system impact
- minimum acceptable fix
- validation that proves the fix

Return `GO` only when no P0/P1 finding or other blocking evidence remains and all required checks
pass. Return `NO-GO` otherwise. This gate excludes known, substantiated blockers in the reviewed
scope; it does not claim that undiscovered defects cannot exist.

## Three-Round Circuit Breaker

Count only valid full review verdicts. A stale target, incomplete scope, malformed response, tool
failure, or unverifiable evidence invalidates the review and does not consume a round.

If the third valid review still reports a substantiated P0 or P1:

1. Stop autonomous execution of the current task.
2. Do not commit the current task.
3. Preserve its working changes and all earlier accepted task commits.
4. Report the remaining blockers, evidence, checks, and plan status.
5. Ask the user whether to revise the design, split the task, continue manually, or stop.

Do not weaken severity, hide findings, or create a checkpoint commit merely to force convergence.

## Final Feature Gate

After every planned task is committed:

1. Run the plan's final repository, integration, and end-to-end checks against the complete feature.
2. Spawn a brand-new, clean-context, read-only reviewer for the aggregate feature diff from the
   pinned feature baseline through the current head. Pass the accepted contracts, plan, raw diff,
   and actual verification evidence.
3. If the aggregate review finds P0/P1 issues, create a remediation task and run it through the same
   implementation, review, circuit-breaker, and commit loop. Obtain a fresh aggregate review after
   remediation.
4. If the user later requests local integration, use `$review-and-merge-branch` when available
   instead of embedding merge machinery in this workflow.
5. Report the final requirements and architecture outcome, task commits, checks and evidence,
   resolved blockers, retained P2 notes, working-tree state, and explicit remote status.

Do not call the feature complete when a required check failed, is blocked, or was skipped without
accepted alternative evidence. Report build, test, signing, installation, runtime, UI acceptance,
deployment, publication, merge, and push as separate states whenever they apply.

## Material-Change Procedure

Pause execution when implementation reveals that an accepted requirement, architecture boundary,
migration, compatibility promise, risk, authority, or intended result must change. Explain the new
evidence and the smallest proposed contract or design change. Return to the affected confirmation
gate, update the plan after approval, and then resume without reopening unrelated settled choices.
