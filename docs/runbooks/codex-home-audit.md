# Codex Home Audit Runbook

## Purpose

Use `codex-maintenance audit` to inspect whether `~/.codex` follows the expected local safety boundary.

## V0 Checks

- `~/.codex` exists.
- `~/.codex` is a git repository.
- `core.hooksPath` points to `hooks`.
- `hooks/pre-commit` exists.
- `.gitleaks.toml` exists.
- `.gitignore` uses a whitelist-style baseline.
- Sensitive runtime paths are not tracked by git.

## Sensitive Paths

- `auth.json`
- `history.jsonl`
- `sessions`
- `shell_snapshots`
- `secrets`
