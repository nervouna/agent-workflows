---
name: node-npm-workflow
description: Use when working on Node, npm, npx, React, package manager choice, global package checks, Corepack, or mise-managed Node path issues in the user's macOS development environment.
---

# Node Npm Workflow

## Overview

Use `mise` for Node runtime selection and interactive shell integration. Use `npm` for day-to-day package workflows unless project metadata explicitly requires another package manager.

## Project Orientation

1. Inspect `mise.toml`, `package.json`, lockfiles, README, and npm scripts before choosing commands.
2. Prefer `npm ci` when a lockfile and clean install are appropriate; otherwise use `npm install`.
3. Use `npm run ...` for project scripts and `npm list -g --depth=0` for global package checks.
4. Do not use `npx list -g`; `npx` treats `list` as a package binary.

## Package Manager Boundary

- Do not assume pnpm, Yarn, Bun, Deno, Volta, fnm, or nvm are available.
- Corepack shims may exist, but project metadata decides whether Yarn or pnpm should be activated.
- If Yarn or pnpm is required, verify the requirement from project docs or lockfiles before using it.

## Shell Truth

- In a real interactive zsh TTY, `node`, `npm`, and `npx` should resolve through the active mise Node.
- Non-interactive shells may differ; do not treat them as sole truth for this machine.
- When path behavior matters, verify with `mise current`, `mise which node`, `npm config list -l`, or an interactive `zsh -li` check.

## Development Defaults

- Prefer existing npm scripts over ad hoc commands.
- For non-trivial production changes, use test-first development where the project supports it.
- Keep dependency changes scoped and explain lockfile updates.

## Verification

Run applicable project-local checks, usually:

- `npm run lint`
- `npm test`
- `npm run build`

If a script is absent, blocked, or intentionally skipped, state the reason.
