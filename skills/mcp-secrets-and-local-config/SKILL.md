---
name: mcp-secrets-and-local-config
description: Use when setting up MCP servers, connectors, API keys, local .env files, 1Password op flows, ~/.codex/secrets wrappers, or config changes that could expose credentials, auth files, account identifiers, or secret-bearing environment variables.
---

# MCP Secrets and Local Config

## Overview

Handle local configuration without exposing credentials. Prefer scoped environment files, 1Password retrieval, and local wrappers over tracked config or broad shell environment changes.

## Hard Rules

- Never print, log, paste, commit, or diff secrets.
- Never put API keys, credentials, auth tokens, or secret-bearing env values in tracked config, docs, AGENTS files, or launchd-wide environment.
- Prefer env vars over hardcoding. Prefer `.env` files for local config, gitignored by default.

## Workflow

1. Identify required variable names from primary docs or existing config without displaying values.
2. Ensure the destination is gitignored before creating or editing any secret-bearing file.
3. For Codex MCP server keys, store values in `~/.codex/secrets/<server>.env` and point config to a local wrapper.
4. Use `op read`, `op run`, or equivalent 1Password flows when available; do not echo retrieved values.
5. For project-local config, use `.env` and commit only templates such as `.env.example` with variable names and non-secret placeholders.
6. Verify with command exit status and redacted output. Do not use `cat`, `printenv`, or shell tracing on secret-bearing files.

## Config Boundaries

- Use tracked config for command shape, wrapper paths, and non-secret defaults only.
- Keep raw secrets in gitignored local files or password-manager-backed commands.
- Avoid broad launchd or shell-profile exports unless the user explicitly chooses that tradeoff.
- Treat `~/.codex` as an external target unless working directly in that config repository.

## Review Before Completion

Before declaring setup complete, confirm:

- secret file paths are ignored or outside tracked repos
- tracked diffs contain no secrets, tokens, local account identifiers, or raw env dumps
- the configured command can start or validate without printing secret values
