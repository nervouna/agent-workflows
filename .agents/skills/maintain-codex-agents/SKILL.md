---
name: maintain-codex-agents
description: Use when editing ~/.codex/AGENTS.md from the codex-maintenance repository, deciding whether user-level Codex guidance belongs in AGENTS.md or a reusable skill, compressing global instructions, or deploying repository-managed personal skills into ~/.agents/skills.
metadata:
  internal: true
---

# Maintain Codex Agents

## Core Principle

Keep `~/.codex/AGENTS.md` as a compact always-on instruction index. Put durable global rules there only when they must affect nearly every Codex task; move task-specific workflows into skills.

## Initial Inspection

1. Read `~/.codex/AGENTS.md` and find any existing content for the requested topic.
2. Run `wc -w ~/.codex/AGENTS.md`.
3. Inspect `git -C ~/.codex status --short` and `git -C ~/.codex diff -- AGENTS.md`; ignore unrelated `~/.codex` changes unless the task requires them.
4. Search this repository's `skills/` and `.agents/skills/` for an existing skill that already owns the topic.

## Decision Gates

Keep content in `~/.codex/AGENTS.md` when it is:

- language, communication, or style guidance that should apply everywhere
- hard safety or verification rules
- universal Git or workflow constraints
- a one-line reference to a skill, such as `Use $python-workflow ...`

Extract or update a skill when the topic:

- exceeds about 60-80 words in `AGENTS.md`
- needs three or more steps, commands, exceptions, or examples
- applies only to a specific toolchain, product area, security setup, or maintenance workflow
- would push `AGENTS.md` above about 400 words
- is useful enough to reuse, but not universal enough to load every turn

Treat `<= 350` words as healthy, `351-399` as warning range, and `>= 400` as a hard prompt to compress or extract unless the new content is a global hard rule.

## Skill Placement

- Repository-level maintenance workflows belong in `$REPO_ROOT/.agents/skills/<skill-name>`.
- User-level reusable skills maintained by this repository belong in `$REPO_ROOT/skills/<skill-name>` and are deployed with symlinks from `~/.agents/skills/<skill-name>`.
- Do not deploy repository-only maintenance skills into user-level skill directories.
- Avoid `~/.codex/skills` for new user skills; current Codex discovery uses `~/.agents/skills`.

## Extraction Workflow

1. Create or update the skill source under this repository.
2. Replace detailed `~/.codex/AGENTS.md` content with a short `$skill-name` reference.
3. For user-level skills, ensure `~/.agents/skills/<skill-name>` is a symlink to this repository's source.
4. Remove stale duplicate `~/.codex/skills/<skill-name>` entries only after confirming they are symlinks for the same skill, not real directories or unrelated files.
5. Keep `~/.codex` as an external target; do not broaden its Git whitelist or touch runtime state unless explicitly requested.

## Verification

Run the relevant checks before declaring completion:

- `quick_validate.py <skill-dir>` for each changed skill
- `test -L ~/.agents/skills/<skill-name>` and `readlink ~/.agents/skills/<skill-name>` for user-level skill deployment
- `wc -w ~/.codex/AGENTS.md`
- `git diff --check`, and `git diff --cached --check` when changes are staged
- `git status --short --untracked-files=all`

For commits in this repository, keep staged changes scoped and run the required pre-commit review gate.
