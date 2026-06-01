# Codex Maintenance Workspace

## Scope

- This repository stores Codex maintenance tools, tests, runbooks, and templates.
- Do not mirror runtime state from `~/.codex`.
- Treat `~/.codex` as an external target that tools inspect or update deliberately.

## Safety

- Default to read-only inspections for `~/.codex`.
- Never print secrets, session content, auth files, or raw environment files.
- Do not commit generated reports that contain local paths, account identifiers, or sensitive config values unless reviewed.
- Destructive maintenance commands must require an explicit flag and a clear confirmation path.

## Development

- Use `uv` for Python commands.
- Keep production code in `src/codex_maintenance/`.
- Keep tests in `tests/`.
- Run formatting, linting, and tests before declaring code work complete.
- Prefer small CLI commands with explicit output and non-zero exit codes for failed checks.
