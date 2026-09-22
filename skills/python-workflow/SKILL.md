---
name: python-workflow
description: Use when working on Python projects or tools, choosing interpreters or dependencies, resolving python, pip, pytest, ruff, or uv path issues, or using FastAPI, Polars, or LangChain in the user's macOS development environment.
---

# Python Workflow

## Overview

Run Python work natively on macOS. Homebrew owns the interpreter (currently `python@3.14`); `uv` owns project environments, dependencies, and isolated tools. Do not assume mise, devbox, or a container runtime is installed. Inspect another machine's setup before applying these local defaults.

## Project Orientation

1. Inspect `pyproject.toml` (`requires-python`), `.python-version`, `uv.lock`, README, and local scripts before choosing commands. Respect an existing project's runtime configuration.
2. Prefer `uv sync` for dependencies, `uv add <package>` for declared dependencies, and `uv run ...` for project tools and tests. Use the project's documented frozen/locked mode when lockfile changes are out of scope.
3. For a project without uv metadata, use `uv venv` and `uv pip install <package>` as appropriate. Keep dependencies in the project environment.
4. Use `uvx ...` for one-off tools and `uv tool install <tool>` for requested persistent commands. Do not assume pytest, ruff, or other CLIs are globally installed.
5. Preserve Homebrew's externally-managed Python protection. Do not use global pip installs, `sudo pip`, or `--break-system-packages` as a workaround.

## Interpreter Boundary

- The local shell defaults to `UV_PYTHON_DOWNLOADS=never` and `UV_PYTHON_PREFERENCE=only-system`. Preserve explicit overrides; do not silently download a second interpreter or restore retired runtime managers.
- If the project cannot use the installed Python, identify the required version and choose an explicit compatible interpreter/setup within the authorized scope. Do not relax `requires-python` just to fit the host.
- An old `.venv` may point to a removed interpreter after environment migration. Verify its interpreter and rebuild only that disposable project environment when appropriate; preserve manifests and lockfiles.

## Shell Truth

- Check `command -v python python3 pip pip3 uv uvx`, versions, and `uv python find --system` when interpreter resolution matters. For project execution, inspect `sys.executable` through `uv run`.
- Zsh startup config supplies the Homebrew paths; an activated virtual environment retains precedence in nested shells. Compare the failing shell or GUI process with a fresh Zsh session instead of assuming identical PATHs.
- GUI applications launched from the Dock may need an explicit interpreter setting. Leave macOS and application-bundled Python runtimes intact.

## State and Cleanup

Honor configured paths and explicit overrides. Local defaults keep pip/uv configuration under `~/.config`, caches under `~/.cache`, Python history under `~/.local/state/python`, and isolated uv tools under `~/.local/share/uv/tools` with command links in `~/.local/bin`. Do not recreate legacy home-root state directories.

Caches are disposable; configuration, history, and installed tools persist. Use `uv tool uninstall <tool>` for requested tool removal rather than deleting its data as cache. Never dump configuration or environment contents that may contain credentials.

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
