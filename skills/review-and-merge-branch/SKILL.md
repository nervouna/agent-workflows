---
name: review-and-merge-branch
description: Use when Codex must autonomously review a committed local Git branch against main or another base branch, obtain a clean-context GO or NO-GO merge verdict, fix every substantiated P0/P1 blocker, repeat independent review rounds, and merge locally after a fresh GO using fast-forward when possible or a reviewed merge commit when branches diverge. Do not use for a review-only request, uncommitted changes, or an implicitly authorized push, remote PR merge, rebase, force update, branch deletion, or worktree cleanup.
---

# Review and Merge Branch

## Outcome Contract

Act as the integrator. Delegate each merge decision to a newly spawned, read-only reviewer with no parent conversation turns. Integrate the exact reviewed candidate into the exact reviewed base only when the latest valid verdict is `GO`. Fast-forward when possible; when branches diverge, review the exact prospective merge tree before creating a merge commit.

Keep the operation local unless the user explicitly requests a remote action. Do not push, remotely merge a PR, rebase, force-update, delete a branch, or remove a worktree as an implied part of this workflow.

## Reuse Existing Capabilities

- Use Codex's native subagent capability. Spawn a new agent with zero forked parent turns for every review round (`fork_turns: "none"` when that control is available).
- Read and follow applicable `AGENTS.md` files and repository verification or release skills. Reuse their commands and acceptance rules instead of inventing parallel policy.
- Use built-in `/review` or `codex review --base` for a user-requested one-shot review. Do not nest another Codex review inside the clean reviewer for this loop.
- Use an installed GitHub skill only when the user explicitly requests PR comments, a remote merge, or another GitHub mutation. A local `GO` does not authorize those actions.
- If no clean-context subagent capability is available, stop as `BLOCKED`. Do not substitute a parent-context self-review and call it independent.

## Preflight

1. Resolve the repository root and read all applicable instructions.
2. Resolve the candidate from the user's explicit ref, otherwise the current local branch.
3. Resolve the base from the user's explicit ref, otherwise local `main`. If local `main` does not exist, use the unambiguous local branch named by `refs/remotes/origin/HEAD`; ask only if the base remains ambiguous.
4. Inspect `git worktree list --porcelain`. For every worktree that owns the candidate or base, record its absolute top-level path, worktree-specific absolute Git directory and index path, common Git directory, checked-out full ref or detached state, `HEAD`, index tree, tracked/untracked status, and ignored-path inventory. Preserve and report pre-existing files instead of staging, committing, stashing, cleaning, or overwriting them. Run every worktree-local Git command with `git -C EXACT_WORKTREE`; never rely on the integrator's current directory.
5. Derive unambiguous local `BASE_BRANCH` and `CANDIDATE_BRANCH` names from their `refs/heads/...` refs; use these short names only as `git switch` operands, then verify the resulting full symbolic ref. Choose a clean `REVIEW_WORKTREE` that materializes the candidate. Prefer an existing worktree attached to the candidate; otherwise, only when the current worktree is clean and can be moved safely, run `git -C REVIEW_WORKTREE switch --no-overwrite-ignore CANDIDATE_BRANCH`. Require its symbolic `HEAD` to equal `CANDIDATE_FULL_REF`, its `HEAD` to equal `CANDIDATE_SHA`, and its index tree to equal `CANDIDATE_SHA^{tree}`. If no safe review worktree exists, stop as `BLOCKED` rather than creating or repurposing another worktree implicitly.
6. Choose a clean `INTEGRATION_WORKTREE`. Prefer a distinct worktree already attached to the base. Otherwise designate `REVIEW_WORKTREE` and record that it must be switched from the candidate to the base after fast-forward review or before constructing a provisional merge. Pin all of its worktree identities from step 4. Never force a checkout or create, remove, or repurpose another worktree implicitly.
7. Require distinct local branch refs, a committed candidate, and clean review and integration worktrees before the first review. Reject sparse checkouts and any skip-worktree or assume-unchanged index entries rather than normalizing their flags. Record the fully qualified refs, their SHAs, both worktree identities, status snapshots, and ignored paths or directory/file collisions with every tree a switch or integration would write. Any collision is `BLOCKED`; use `--no-overwrite-ignore` as an additional guard on every switch or merge.
8. Require `git merge-base --all BASE_SHA CANDIDATE_SHA` to resolve at least one best common ancestor and record every result. If none exists, stop as `BLOCKED`; do not merge unrelated histories.
9. Classify the integration without rewriting history: if the candidate is already an ancestor of the base, it is already integrated; if the base is an ancestor of the candidate, use `fast-forward`; otherwise use `merge-commit`.
10. Record the base's configured upstream ref and its locally known SHA, or their absence. If that upstream is ahead of the base, stop as `BLOCKED` instead of pulling. Do not claim remote freshness without an authorized fetch.
11. Discover required checks from repository instructions, package metadata, CI configuration, hooks, and relevant skills. Separate required checks from optional diagnostics.

If the candidate is already reachable from the base, report it as already integrated after verifying the clean state. Do not create an empty merge.

## Independent Review Loop

For each round:

1. Refresh and pin both full refs and SHAs, every best merge base, integration mode, configured upstream ref, its locally known SHA and ancestry, the full worktree topology, both worktree identity sets, their symbolic `HEAD` states, index trees, status, and ignored-collision snapshots.
2. For `fast-forward`, require `REVIEW_WORKTREE` to remain attached to `CANDIDATE_FULL_REF` at `CANDIDATE_SHA`, clean, and with `git -C REVIEW_WORKTREE write-tree` equal to `CANDIDATE_SHA^{tree}`. Run all required checks in that exact worktree and review `BASE_SHA...CANDIDATE_SHA`; do not create a provisional merge.
3. For `merge-commit`, use `git -C INTEGRATION_WORKTREE switch --no-overwrite-ignore BASE_BRANCH` when a switch is needed, then verify every pinned worktree identity, full symbolic `HEAD`, `HEAD=BASE_SHA`, clean status, index tree `BASE_SHA^{tree}`, and absence of ignored collisions. Detach it at `BASE_SHA` with `git -C INTEGRATION_WORKTREE switch --detach --no-overwrite-ignore BASE_SHA`, re-verify detached `HEAD`, the index tree, clean status, worktree topology, and still-unchanged refs before running `git -C INTEGRATION_WORKTREE merge --no-ff --no-commit --no-overwrite-ignore CANDIDATE_SHA`.
4. If the provisional merge command fails for any reason, record its output and `git -C INTEGRATION_WORKTREE ls-files -u`, restore the integration worktree with the restoration procedure below, and stop as `BLOCKED`; do not resolve conflicts or add `--allow-unrelated-histories` implicitly. Otherwise require `HEAD` to equal `BASE_SHA`, `MERGE_HEAD` to equal `CANDIDATE_SHA`, `git -C INTEGRATION_WORKTREE ls-files -u` to be empty, and record the prospective tree with `git -C INTEGRATION_WORKTREE write-tree` plus the in-progress merge status.
5. Spawn a brand-new reviewer. Never reuse, follow up, or send earlier findings to a reviewer from a previous round.
6. Pass only raw task facts: repository path, fully qualified refs and pinned SHAs, every best merge base, integration mode, exact review and integration worktree paths and Git directories, review target, user acceptance criteria, applicable instruction paths, and discovered verification commands. For `merge-commit`, also pass the prospective tree SHA. Do not pass the integrator's conclusions or earlier verdicts.
7. Instruct the reviewer to remain read-only and return exactly the JSON contract below. For `fast-forward`, run Git commands in `REVIEW_WORKTREE`, verify that it materializes the pinned candidate, then inspect the complete branch diff plus relevant surrounding code. For `merge-commit`, run Git commands in `INTEGRATION_WORKTREE`, verify the detached `HEAD`, `MERGE_HEAD`, and index tree identities, inspect `git diff BASE_SHA TREE_SHA`, and inspect both sides since every best merge base.
8. Wait for the reviewer to finish. Reject malformed, stale, internally inconsistent, or non-JSON output as an invalid review, never as `GO`.
9. Compare both exact worktrees' full identity sets, status, ignored collisions, refs, `HEAD`, and, when applicable, `MERGE_HEAD` and index tree with the expected review-state snapshot. If the reviewer changed relevant state, invalidate the verdict, preserve the changes for inspection, and stop rather than deleting them automatically.
10. Accept `GO` only when the reported refs, SHAs, merge bases, integration mode, worktree identities, and prospective tree when applicable match; both finding arrays are empty; every required check passed; and no blocking evidence remains.
11. On `NO-GO`, restore the integration worktree, remediate every substantiated P0/P1 finding on the candidate, verify and commit only the remediation, then begin a new round with a new reviewer and new SHAs.

Continue until a valid `GO` or a genuine blocker prevents safe progress. Do not impose an arbitrary round limit, and do not weaken severity to force convergence.

Whenever canceling a provisional merge, first re-verify the pinned worktree identity. If `MERGE_HEAD` exists, require `git -C INTEGRATION_WORKTREE merge --abort` to succeed. If `MERGE_HEAD` is already absent, require clean tracked/untracked state and check exact-tree ignored and directory/file collisions before returning to the pinned base tree with `git -C INTEGRATION_WORKTREE switch --detach --no-overwrite-ignore BASE_SHA`; otherwise remain detached and stop. Stay detached while verifying `HEAD=BASE_SHA`, index tree `BASE_SHA^{tree}`, absent `MERGE_HEAD`, clean status, preserved ignored paths, unchanged refs and upstream snapshot, and unchanged worktree ownership. Only then may `git -C INTEGRATION_WORKTREE switch --no-overwrite-ignore BASE_BRANCH` reattach the base, followed by the same checks including symbolic `HEAD=BASE_FULL_REF`. If a ref or ownership drifted, remain detached and stop. Treat any nonzero merge, commit, abort, switch, or verification result as an incomplete transaction; preserve the state, stop as `BLOCKED`, and perform no further Git mutation.

## Reviewer Prompt and Output Contract

Give every clean reviewer this role and rules:

```text
Act as the independent final merge-gate reviewer. Work read-only: do not edit,
stage, commit, merge, switch branches, stash, clean, or alter Git refs. Read the
applicable AGENTS.md and repository documentation. In fast-forward mode, inspect
the full pinned diff BASE_SHA...CANDIDATE_SHA. In merge-commit mode, inspect the
actual staged prospective merge tree in the exact supplied worktree against BASE_SHA,
verify HEAD, MERGE_HEAD, and the index tree identities, inspect both branch histories
since their merge base, and enough surrounding code to evaluate interactions. Evaluate
behavior, correctness, security, data integrity, compatibility, concurrency, error
paths, and test adequacy. Run only risk-proportionate checks that do not mutate
source or external systems. Enumerate every substantiated P0 and P1 finding; do not
cap the count. Flag only discrete, actionable defects introduced by the reviewed
integration and demonstrated from the code or checks. Do not flag pre-existing
problems, intentional behavior, speculative concerns, or style nits. Return exactly
one JSON object and no Markdown fences or extra text.
```

Use these severity definitions:

- `P0`: likely security compromise, unrecoverable data loss or corruption, severe privacy breach, widespread outage, or another catastrophic merge consequence.
- `P1`: user-blocking or major correctness regression, broken required behavior, serious reliability or compatibility failure, unsafe migration, or missing critical regression coverage that makes the changed production behavior unmergeable.
- Do not promote style, preference, speculative hardening, or ordinary maintainability concerns to P1. Put non-blocking observations in `non_blocking_notes`.

Require this complete JSON shape:

```json
{
  "verdict": "GO",
  "base_ref": "refs/heads/main",
  "base_sha": "40-hex SHA",
  "candidate_ref": "refs/heads/feature/example",
  "candidate_sha": "40-hex SHA",
  "merge_base_shas": ["40-hex SHA"],
  "integration_mode": "fast-forward",
  "review_worktree": "/absolute/repository/worktree/path",
  "review_worktree_git_dir": "/absolute/worktree-specific/git/dir",
  "integration_worktree": "/absolute/repository/worktree/path",
  "integration_worktree_git_dir": "/absolute/worktree-specific/git/dir",
  "prospective_tree_sha": null,
  "reviewed_tree_sha": "40-hex SHA",
  "reviewed_range": "BASE_SHA...CANDIDATE_SHA",
  "p0_findings": [],
  "p1_findings": [],
  "checks": [
    {
      "name": "project test suite",
      "command": "exact command or null",
      "worktree": "/absolute/repository/worktree/path",
      "tested_sha": "40-hex SHA",
      "tested_tree_sha": "40-hex SHA",
      "status": "passed",
      "evidence": "concise observed result"
    }
  ],
  "blocking_evidence": [],
  "non_blocking_notes": [],
  "summary": "concise merge-gate rationale"
}
```

Each finding must use this shape:

```json
{
  "id": "P1-1",
  "title": "imperative, specific title",
  "location": {
    "path": "repository-relative/path",
    "line": 123
  },
  "evidence": "reproducible evidence from the pinned revision",
  "impact": "why this blocks merge",
  "required_fix": "minimum acceptable correction",
  "validation": "how to prove the correction"
}
```

Allow `location.line` to be `null` only for a genuinely cross-cutting finding. Allow `integration_mode` values `fast-forward` or `merge-commit`, and check status values `passed`, `failed`, `blocked`, or `skipped`. Require every ref, merge-base SHA, path, and Git-directory field to match the supplied values exactly. Require `reviewed_tree_sha` and every required check's `worktree`, `tested_sha`, and `tested_tree_sha` to identify the exact materialized target: the candidate commit and its tree for fast-forward, or `tested_sha: null` and the prospective tree for merge-commit. Require `prospective_tree_sha` to be `null` for fast-forward and the exact 40-hex reviewed tree for merge-commit. In merge-commit mode, describe `reviewed_range` as `BASE_SHA -> prospective tree TREE_SHA`. Require `verdict: "NO-GO"` when either finding array is non-empty, a required check failed or is blocked, the review scope is incomplete, or the pinned revision, tested tree, worktree identity, or prospective tree cannot be verified. Require `verdict: "GO"` only when both finding arrays and `blocking_evidence` are empty and all required checks passed.

## Remediation

1. Reproduce or otherwise substantiate each finding before editing. Do not change correct code merely to satisfy an unsupported assertion.
2. Implement the smallest complete fix for every confirmed P0/P1. Avoid unrelated P2/P3 cleanup.
3. Add or update a regression test first for non-trivial production logic when practical. Otherwise define reproducible acceptance evidence before the edit.
4. Run all applicable focused and repository-required checks. Report each as passed, failed, blocked, or skipped.
5. Review the scoped remediation diff for correctness, avoidable complexity, unrelated churn, verification gaps, and secret exposure.
6. Restore and verify the integration worktree before editing or committing candidate remediation. Ensure `REVIEW_WORKTREE` is clean and attached to `CANDIDATE_FULL_REF` at the pinned candidate, using `git -C REVIEW_WORKTREE switch --no-overwrite-ignore CANDIDATE_BRANCH` when the shared worktree must move back from the base. Stage exact intended paths and commit the remediation using repository conventions. Never include pre-existing or reviewer-created changes.
7. If a finding is unsupported, retain concise evidence for the final report and request a new blind review of the raw current revision. Do not prime the new reviewer with the disputed finding.

## Final Merge Gate

Immediately before merging, verify all of the following again:

- the latest verdict is a valid `GO`
- the current base and candidate SHAs exactly match the verdict
- the configured upstream ref, locally known SHA, and ancestry still match the review snapshot, and the upstream is not ahead of the base
- the integration mode still matches the pinned ancestry
- the rescanned worktree topology and both exact worktree identity sets, refs, and Git states match the reviewed snapshot
- every required check is passing
- no P0/P1 or blocking evidence remains
- the destination base worktree was clean before integration

If any item changed, invalidate the verdict and start a fresh review round.

For `fast-forward`, require `REVIEW_WORKTREE` to remain attached to the candidate at `CANDIDATE_SHA`, clean, and with the tested candidate index tree. If `INTEGRATION_WORKTREE` is the same path, use `git -C INTEGRATION_WORKTREE switch --no-overwrite-ignore BASE_BRANCH`; otherwise require it to remain attached to the base. Re-verify every pinned worktree identity, symbolic `HEAD=BASE_FULL_REF`, `HEAD=BASE_SHA`, index tree `BASE_SHA^{tree}`, clean status, refs, upstream snapshot, worktree topology, and ignored collisions. Immediately recheck `CANDIDATE_FULL_REF=CANDIDATE_SHA`, then run `git -C INTEGRATION_WORKTREE merge --ff-only --no-overwrite-ignore CANDIDATE_SHA`. If fast-forward fails, preserve the state, invalidate the verdict, and reclassify from fresh SHAs rather than falling through blindly. On success require the base and worktree `HEAD` to equal `CANDIDATE_SHA`, the candidate ref to remain pinned, and the resulting index tree and worktree to be clean.

For `merge-commit`, require the same detached provisional merge to remain active in the pinned integration worktree with `HEAD=BASE_SHA`, `MERGE_HEAD=CANDIDATE_SHA`, no unmerged paths, and the reviewed prospective tree. Run every required check and configured commit gate with `git -C INTEGRATION_WORKTREE` or the repository's equivalent worktree-scoped command against that exact merge result, then immediately re-pin the refs, upstream snapshot, full worktree identity, topology, detached `HEAD`, `MERGE_HEAD`, status, ignored collisions, and index tree.

Create the merge commit with normal repository hooks using `git -C INTEGRATION_WORKTREE commit --no-edit` while still detached, so the base ref remains untouched. If commit creation fails, use the restoration procedure and stop as `BLOCKED`. Before advancing the base, require the detached commit to have exactly two parents in order, `BASE_SHA` then `CANDIDATE_SHA`, and the reviewed prospective tree as its tree. Run every required check again against this actual detached merge commit, including checks that inspect `HEAD`, parents, ancestry, or version metadata; bind each result to `MERGE_COMMIT_SHA` and the reviewed tree. Then re-verify both branch refs and the upstream snapshot, every commit identity, clean status, and that no worktree is attached to `BASE_FULL_REF`. If any check fails, do not move the base ref; use the restoration procedure and stop as `BLOCKED`.

Immediately recheck those identities, then use one `git -C INTEGRATION_WORKTREE update-ref --stdin` transaction to verify `CANDIDATE_FULL_REF=CANDIDATE_SHA` and the upstream ref/SHA when present while updating `BASE_FULL_REF` from exactly `BASE_SHA` to `MERGE_COMMIT_SHA`. The base update's expected-old value is its compare-and-swap guard. This is a guarded fast-forward to a verified descendant, never a force update. If the transaction fails, do not retry with a force; use the restoration procedure and start a fresh review only if restoration proves the original state.

A successful ref transaction is the integration commit point: never roll the base back afterward. Re-scan worktree ownership, then run `git -C INTEGRATION_WORKTREE switch --no-overwrite-ignore BASE_BRANCH`; because detached `HEAD`, the updated base, and the index tree already identify the same verified merge commit, this operation only reattaches the worktree. Whether it succeeds or returns nonzero, inspect and report the exact final ref, symbolic `HEAD`, worktree, index, ignored paths, and hook outcome. If attachment is incomplete, preserve the detached worktree at `MERGE_COMMIT_SHA` and report the successful base integration separately from the blocked post-integration attachment; do not invoke the pre-commit restoration procedure or undo the merged base.

After integrating, verify the resulting base SHA and a clean destination worktree. Do not push or delete the candidate branch or worktree unless explicitly requested.

## Final Report

Report:

- final `GO` or `NO-GO`, or `BLOCKED` for an orchestration/preflight failure
- base and candidate refs plus reviewed SHAs
- review round count
- every P0/P1 found and how it was resolved, with invalid findings identified separately
- checks run and their statuses
- integration mode, local merge result, and resulting base SHA
- merge commit SHA, parents, and tree when merge-commit mode was used
- integration worktree path and restoration status
- explicit remote status: not pushed or remotely merged unless separately authorized
- retained branch/worktree state
