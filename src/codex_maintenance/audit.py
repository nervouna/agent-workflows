from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

SENSITIVE_PATHS = ("auth.json", "history.jsonl", "sessions", "shell_snapshots", "secrets")


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: str

    @classmethod
    def pass_(cls, name: str, details: str = "ok") -> Check:
        return cls(name=name, status="pass", details=details)

    @classmethod
    def fail(cls, name: str, details: str) -> Check:
        return cls(name=name, status="fail", details=details)

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "details": self.details}


def audit_codex_home(codex_home: Path) -> dict[str, object]:
    codex_home = codex_home.expanduser()
    exists_check = _check_exists(codex_home)
    checks = [exists_check]
    if exists_check.status == "pass":
        checks.extend(
            [
                _check_git_repo(codex_home),
                _check_hooks_path(codex_home),
                _check_file_exists(codex_home / "hooks" / "pre-commit", "pre-commit-hook"),
                _check_file_exists(codex_home / ".gitleaks.toml", "gitleaks-config"),
                _check_whitelist_gitignore(codex_home / ".gitignore"),
                _check_sensitive_paths_untracked(codex_home),
            ]
        )
    status = "fail" if any(check.status == "fail" for check in checks) else "pass"
    return {
        "codex_home": str(codex_home),
        "status": status,
        "checks": [check.to_dict() for check in checks],
    }


def _check_exists(codex_home: Path) -> Check:
    if codex_home.is_dir():
        return Check.pass_("codex-home-exists", "directory exists")
    return Check.fail("codex-home-exists", "directory is missing")


def _check_git_repo(codex_home: Path) -> Check:
    if not codex_home.is_dir():
        return Check.fail("git-repository", "codex home is missing")
    result = _run_git(codex_home, "rev-parse", "--is-inside-work-tree")
    if result.returncode == 0 and result.stdout.strip() == "true":
        return Check.pass_("git-repository", "git repository detected")
    return Check.fail("git-repository", "not a git repository")


def _check_hooks_path(codex_home: Path) -> Check:
    result = _run_git(codex_home, "config", "--get", "core.hooksPath")
    value = result.stdout.strip()
    if result.returncode == 0 and value == "hooks":
        return Check.pass_("tracked-hooks-path", "core.hooksPath=hooks")
    if value:
        return Check.fail("tracked-hooks-path", f"core.hooksPath={value}")
    return Check.fail("tracked-hooks-path", "core.hooksPath is not set")


def _check_file_exists(path: Path, name: str) -> Check:
    if path.is_file():
        return Check.pass_(name, f"{path.name} exists")
    return Check.fail(name, f"{path.name} is missing")


def _check_whitelist_gitignore(path: Path) -> Check:
    if not path.is_file():
        return Check.fail("whitelist-gitignore", ".gitignore is missing")
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if lines and lines[0] == "*" and any(line.startswith("!") for line in lines[1:]):
        return Check.pass_("whitelist-gitignore", "whitelist baseline detected")
    return Check.fail("whitelist-gitignore", "expected leading '*' plus whitelist exceptions")


def _check_sensitive_paths_untracked(codex_home: Path) -> Check:
    result = _run_git(codex_home, "ls-files", "--", *SENSITIVE_PATHS)
    if result.returncode != 0:
        return Check.fail("sensitive-paths-untracked", "could not inspect tracked files")
    tracked = sorted(line for line in result.stdout.splitlines() if line)
    if tracked:
        return Check.fail(
            "sensitive-paths-untracked",
            f"tracked sensitive paths: {', '.join(tracked)}",
        )
    return Check.pass_("sensitive-paths-untracked", "no sensitive paths tracked")


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
