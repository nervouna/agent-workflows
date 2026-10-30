# Security

The skills here are instructions that coding agents follow with the user's own permissions: they run shell commands, edit files, handle signing identities and credentials, and merge Git branches. The audit tool runs `git` inside the user's Codex home, next to auth files, sessions and secrets. A skill that leads an agent to expose a credential or take a destructive step it was not asked to take is a security problem, and so is an audit command that reads or prints more than it should.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through GitHub: **Security → Report a vulnerability** on this repository ([direct link](https://github.com/nervouna/agent-workflows/security/advisories/new)). Include the skill or command, what you did, what happened, and the commit you tested. Do not include real credentials or session content.

You will get an answer within a week. Fixes land on `main`; there are no maintained release branches.

## In scope

- Skill instructions that lead an agent to print, log or commit secrets, auth files or session content
- Skill instructions that lead an agent to push, force-update, delete or merge remotely, or take another destructive step, without the user's explicit request
- A way to make `codex-maintenance` read or print secrets, sessions or history, or change anything in the Codex home
- A way for the skill installation payload to include files outside `skills/<name>/`

## Out of scope

- Problems in the Skills CLI, Codex or other agents, or in the tools a skill tells the agent to use
- An agent ignoring a skill's instructions
- Anything that needs prior write access to the user's machine or this repository
