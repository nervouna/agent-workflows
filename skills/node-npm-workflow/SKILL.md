---
name: node-npm-workflow
description: Use when working on Node, npm, npx, React, package manager choice, global package checks, Corepack, or Node path issues in the user's macOS development environment.
---

# Node Npm Workflow

## Overview

Run Node work natively on macOS. Homebrew owns the runtime (currently `node@24`, the selected LTS line), with its bundled npm/npx. Use npm unless project metadata requires another package manager. Do not assume mise, devbox, or a container runtime is installed. Inspect another machine's setup before applying these local defaults.

## Project Orientation

1. Inspect `package.json` (`engines` and `packageManager`), lockfiles, runtime version files, README, and scripts before choosing commands. Respect existing project configuration.
2. Prefer `npm ci` when a lockfile and clean install are appropriate; otherwise use `npm install`.
3. Use `npm run ...` for project scripts and `npm list -g --depth=0` for global package checks.
4. Do not use `npx list -g`; `npx` treats `list` as a package binary.
5. Keep project dependencies in local `node_modules`. Use `npx`/`npm exec` for one-off package commands, recognizing that missing packages may be downloaded; follow project-pinned versions where available.

## Package Manager Boundary

- Do not assume pnpm, Yarn, Bun, Deno, Volta, fnm, or nvm are available.
- Corepack is available in the current setup, but its presence does not mean Yarn or pnpm is installed or activated. Project metadata decides which manager/version is needed; verify availability before use.
- If Yarn or pnpm is required, verify the requirement from project docs or lockfiles before using it.
- If the project's Node requirement differs from the host, identify a compatible runtime setup within the authorized scope. Do not rewrite its engine requirement or replace the host runtime merely to make an install pass.

## Global Tools and State

- For requested persistent CLI tools, `npm install -g <tool>` uses the user-owned prefix, normally `~/.local/share/npm`, with commands in its `bin` directory. Do not use sudo. Verify the effective prefix with `npm config get prefix` before installation.
- Configuration defaults to `~/.config/npm`, cache to `~/.cache/npm`, logs to `~/.local/state/npm/logs`, and REPL history to `~/.local/state/node`. Honor explicit overrides and avoid recreating `~/.npm` or a home-root `.npmrc`.
- npmrc files can hold authentication data. Inspect only the needed non-secret settings, never dump full config files or environments.
- Caches are disposable; configuration, history, and global packages persist. Remove requested global tools with `npm uninstall -g <tool>` rather than deleting the prefix as cache.

## Shell Truth

- When path behavior matters, check `command -v node npm npx corepack`, versions, `node -p process.execPath`, and the effective npm prefix.
- Zsh startup config supplies the Homebrew runtime and user-global command paths. Compare the failing shell or GUI process with a fresh Zsh session instead of assuming identical PATHs.
- Leave application-bundled Node runtimes intact; they are not evidence that project tooling uses the same runtime.

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
