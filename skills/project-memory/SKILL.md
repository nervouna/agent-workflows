---
name: project-memory
description: Use when `.codex/project-memory.md` exists, project instructions route to $project-memory, or the user asks to enable durable repository-scoped memory.
---

# Project Memory

Use `.codex/project-memory.md` to carry a selected project's durable context across clones. Keep long-lived constraints, key decisions with necessary rationale, and risks that should guide future work.

## Workflow

1. Resolve the project root. If `.codex/project-memory.md` exists, read it completely before substantial work. Loading is read-only.
2. Use the parts relevant to the current task. Treat the live checkout and canonical project documentation as authoritative, verify claims whose accuracy matters to the task, and label unresolved mismatches as stale or unverified.
3. If the file is absent, report that project memory is not enabled. Create it only when the user asks, after confirming its contents are appropriate for everyone who can read the repository. Fill the template with verified content and add the project route when automatic maintenance is wanted.
4. Update the file when the user asks or the project route authorizes maintenance and the new information meets the criteria below. Maintain the current truth in place, replacing or removing stale statements and linking to repository-relative canonical documentation when useful.
5. Let the file travel through the project's ordinary Git workflow.

## Update Criteria

Include an item only when all three are true:

1. It will affect work across multiple future tasks.
2. It cannot be recovered cheaply from current code or canonical documentation.
3. It is expected to remain valid beyond the current task.

Write for the repository's full audience, using repository-relative references and only verified, project-local, non-sensitive information.

## Memory Template

```markdown
# Project Memory

## Scope

<What this memory covers.>

## Durable Constraints

- <A long-lived constraint.>

## Key Decisions

- <A durable decision and only the rationale future work still needs.>

## Long-Lived Risks

- <A risk that remains relevant across multiple tasks.>
```

Remove placeholder text and omit empty sections during initialization.

## Project Route

When automatic loading and maintenance are wanted, add this section to the applicable project `AGENTS.md`:

```markdown
## Project Memory

- If `.codex/project-memory.md` exists, use `$project-memory` before substantial work and maintain it when durable project context changes.
```
