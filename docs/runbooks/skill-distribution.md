# Native skill installation and publication

Use the upstream [Skills CLI](https://github.com/vercel-labs/skills), not a repository-specific
installer. Public payloads live in `skills/<name>/`; `skills/README.md` is a human catalog, not an
index. Installing a skill neither installs its toolchain nor grants agent capabilities or account
access. See the catalog for prerequisites.

## Offline repository checks

From the checkout, with Python and uv available:

```sh
uv run --frozen pytest
uv run --frozen ruff format --check .
uv run --frozen ruff check .
git diff --check
```

Tests cover public names, frontmatter, catalog links, self-contained payloads and bundled MIT
licenses. They do not emulate upstream discovery or replace a real installation check.

## Isolated native smoke check

Use a POSIX-compatible shell, Node/npm and Git. With mise, resolve the selected runtime with
`skill_node_bin=$(dirname "$(mise which node)")`, then enter
`PATH="$skill_node_bin:$PATH" sh`. Merely using `mise exec -- sh` can leave another Node first in
the inherited PATH. This changes only the child shell's PATH, not global configuration.
Start at the checkout root. These commands create only
task-specific temporary project destinations, npm cache and CLI state; they do not install global
skills. Do not redefine `HOME`, `home` or `CODEX_HOME` to simulate another user.

```sh
set -eu
skill_source=$(pwd -P)
smoke_root=$(mktemp -d)
single_target=$(mktemp -d)
all_target=$(mktemp -d)

# Empty child environments omit credentials and internal-discovery overrides.
# Distinct config paths avoid npm's double-loading error for identical configs.
smoke_env() {
  env -i PATH="$PATH" TMPDIR="$smoke_root" \
    XDG_STATE_HOME="$smoke_root/state" \
    DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 \
    npm_config_cache="$smoke_root/npm-cache" \
    npm_config_userconfig=/dev/null \
    npm_config_globalconfig="$smoke_root/no-global.npmrc" "$@"
}

# Resolve once, then pin the same released version for every check.
skills_version=$(smoke_env npm view skills version)
smoke_env npm view "skills@$skills_version" engines
command -v node
command -v npm
node --version
npm --version
smoke_env npx --yes "skills@$skills_version" --help
```

Before continuing, check that Node satisfies the reported `engines` constraint and inspect that
release's help/implementation if behavior has changed. Do not proceed if disabling telemetry or
redirecting CLI state is no longer supported. Continue in the same shell:

```sh
smoke_env npx --yes "skills@$skills_version" add "$skill_source" --list
smoke_env env INSTALL_INTERNAL_SKILLS=1 \
  npx --yes "skills@$skills_version" add "$skill_source" --list

(cd "$single_target" && smoke_env npx --yes "skills@$skills_version" \
  add "$skill_source" --skill app-icon-design -a codex --yes)
(cd "$all_target" && smoke_env npx --yes "skills@$skills_version" \
  add "$skill_source" --skill '*' -a codex --yes)
```

Record the version, commands, exit statuses and temporary paths in local evidence, not in README
snapshots. After the initial download,
`npx --offline --yes "skills@$skills_version" ...` can reuse the isolated cache.

Default discovery must list exactly the eight names below. With `INSTALL_INTERNAL_SKILLS=1`, it
must additionally list `maintain-codex-agents`. Internal metadata is only a default filter: an
explicit named request can also select the internal skill without the override. It is not access
control and the source will remain publicly readable.

Verify complete installed payloads, not just command success. In the same shell, check exact names,
reject links, and compare all files including `LICENSE`, `SKILL.md`, `agents/openai.yaml` and
supporting resources. Every command below must succeed:

```sh
public_names='app-icon-design apple-signing-workflow keep-calm-and-yolo-on
mcp-secrets-and-local-config node-npm-workflow project-memory python-workflow
review-and-merge-branch'
installed_names() {
  find "$1/.agents/skills" -mindepth 1 -maxdepth 1 -exec basename {} \; | sort
}
test "$(installed_names "$single_target")" = app-icon-design
test "$(installed_names "$all_target")" = "$(printf '%s\n' $public_names | sort)"
test -z "$(find "$single_target/.agents" "$all_target/.agents" -type l -print)"
diff -r "$skill_source/skills/app-icon-design" \
  "$single_target/.agents/skills/app-icon-design"
for skill_name in $public_names; do
  diff -r "$skill_source/skills/$skill_name" "$all_target/.agents/skills/$skill_name"
done
```

Keep the temporary artifacts until review finishes. Verify repository status and source hashes
before/after smoke checks and ensure the real user skills directory was not modified. This proves
local project installation only, not a global installation, anonymous remote access, another
computer's runtime capabilities, or successful skill execution.

## Publication boundary

Before making the repository public:

1. Review tracked content and reachable Git history for secrets, personal paths, account
   identifiers, author email addresses and third-party licensing. Use redacted scans such as
   `gitleaks git --redact --no-banner --log-opts=--all .` and inspect non-secret disclosure classes
   separately. Clean scans do not prove anonymity; current-file cleanup does not erase history.
2. Resolve disclosure decisions with the owner. Do not publish raw findings, credentials or
   generated local reports. History rewriting requires separate explicit authorization.
3. Obtain explicit authorization for integration, push, remote rename and visibility change.
   Preserve the Python package/module/CLI names when renaming the remote to
   `nervouna/agent-workflows`; the local checkout directory does not need to move.
4. Once the approved commit is available at that public remote, repeat the isolated tests with
   `nervouna/agent-workflows` as the CLI source, without credentials. Compare installed payloads
   with the approved commit and record the resolved remote revision. Test on another computer
   before claiming cross-machine acceptance.

For normal Codex use, `-a codex` installs to the current project's `.agents/skills/`; adding `-g`
uses `~/.agents/skills/`. A global install may overwrite same-named skills and is not part of the
isolated smoke check above. Do not use `--all` as a substitute for the explicit public skill
selection `--skill '*'`. Consumers do not need uv or this repository's development dependencies.
