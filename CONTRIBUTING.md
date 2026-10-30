# Contributing

agent-workflows is a personal project, but bug reports and fixes are welcome.

## Issues

- **Bugs:** use the bug report form. Name the skill or command, the agent and its version, what happened and what you expected. Do not paste secrets, auth files or session content.
- **Security problems:** report them privately, see [SECURITY.md](SECURITY.md).
- **Ideas and new skills:** open an issue to discuss it first. The project stays small on purpose, so not every idea will fit.

## How the project is developed

`AGENTS.md` holds the rules coding agents follow in this repository; they apply to human contributions too. In short:

- Treat `~/.codex` as an external target. Inspect it read-only by default, and never print secrets, session content, auth files or raw environment files.
- Destructive maintenance commands need an explicit flag and a clear confirmation path.
- Use `uv` for Python. Production code goes in `src/codex_maintenance/`, tests in `tests/`.
- Don't commit generated reports that contain local paths, account identifiers or sensitive config values.
- Before calling work done, these pass:

  ```sh
  uv run pytest
  uv run ruff format --check .
  uv run ruff check .
  ```

A public skill is a self-contained directory `skills/<name>/` with `SKILL.md`, `agents/openai.yaml` and a copy of the MIT `LICENSE`, contains no symlinks, and is listed in [skills/README.md](skills/README.md) and in `PUBLIC_SKILLS` in `tests/test_skill_distribution.py`. The tests check this. `hooks/pre-commit` runs `gitleaks` on staged changes.

## Pull requests

Describe the problem, what you changed, and the commands you ran with their results. For a skill change, say which agent you tried it with. Keep one change per pull request.
