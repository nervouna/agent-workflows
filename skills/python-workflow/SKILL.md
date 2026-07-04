---
name: python-workflow
description: Use when working on Python projects or tools, choosing interpreters or dependencies, resolving python, pip, pytest, ruff, uv, or mise path issues, or using FastAPI, Polars, or LangChain in the user's macOS development environment.
---

# Python Workflow

## Overview

Use `mise` for Python interpreter selection and interactive shell integration. Use `uv` for dependency locking, virtualenvs, package workflows, `uv tool`, and one-off `uvx` execution.

## Project Orientation

1. Inspect project metadata before choosing commands: `mise.toml`, `pyproject.toml`, `uv.lock`, README, and local scripts.
2. Prefer `uv sync` for dependencies, `uv run ...` for project tools and tests, and `uvx ...` for one-off tools.
3. Avoid global `pip install`; do not assume `pytest`, `ruff`, or app CLIs are globally installed.
4. Prefer project-local configuration over machine-global assumptions.

## Shell Truth

- In a real interactive zsh TTY, `python`, `python3`, `pip`, and `pip3` should resolve through mise shims.
- Non-interactive shells may show Homebrew fallbacks; do not treat that as sole truth for this machine.
- When interpreter resolution matters, verify with `mise current`, `mise which python`, or an interactive `zsh -li` check.

## Development Defaults

- Prefer concise readable code and explicit error handling.
- For non-trivial production changes, use test-first development: failing test, implementation, refactor.
- Verify external API or library support before depending on it, especially for FastAPI, Polars, and LangChain changes.

## Verification

Run the applicable project-local checks from metadata, usually:

- `uv run ruff check ...`
- `uv run pytest`
- documented app health checks or CLI smoke tests

If formatting, linting, or tests are absent or blocked, state that explicitly instead of implying completion.
