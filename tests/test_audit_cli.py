import json
import subprocess
import sys
from pathlib import Path

import pytest


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.DEVNULL)


def git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def clean_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    init_git_repo(codex_home)
    (codex_home / ".gitignore").write_text(
        "*\n!/.gitignore\n!/AGENTS.md\n!/config.toml\n!/rules/\n",
        encoding="utf-8",
    )
    (codex_home / ".gitleaks.toml").write_text("[allowlist]\n", encoding="utf-8")
    hooks_dir = codex_home / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    git(codex_home, "config", "core.hooksPath", "hooks")
    return codex_home


def run_audit(codex_home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_maintenance",
            "audit",
            "--codex-home",
            str(codex_home),
            "--json",
        ],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
    )


def test_audit_reports_clean_codex_home(clean_codex_home: Path) -> None:
    result = run_audit(clean_codex_home)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert all(check["status"] == "pass" for check in report["checks"])


@pytest.mark.parametrize(
    ("condition", "expected_check"),
    [
        ("wrong-hooks", "tracked-hooks-path"),
        ("missing-hook", "pre-commit-hook"),
        ("missing-scanner-config", "gitleaks-config"),
        ("bad-ignore", "whitelist-gitignore"),
    ],
)
def test_audit_rejects_broken_safety_boundary(
    clean_codex_home: Path, condition: str, expected_check: str
) -> None:
    if condition == "wrong-hooks":
        git(clean_codex_home, "config", "core.hooksPath", "other-hooks")
    elif condition == "missing-hook":
        (clean_codex_home / "hooks/pre-commit").unlink()
    elif condition == "missing-scanner-config":
        (clean_codex_home / ".gitleaks.toml").unlink()
    else:
        (clean_codex_home / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    result = run_audit(clean_codex_home)
    assert result.returncode == 1
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["status"] == "fail"
    failed = [check for check in report["checks"] if check["status"] == "fail"]
    assert len(failed) == 1
    assert failed[0]["name"] == expected_check
    assert failed[0]["details"]


def test_audit_fails_when_sensitive_runtime_file_is_tracked(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    init_git_repo(codex_home)
    (codex_home / ".gitignore").write_text("*\n!/.gitignore\n", encoding="utf-8")
    (codex_home / "auth.json").write_text('{"token":"redacted"}\n', encoding="utf-8")
    git(codex_home, "add", "--force", "auth.json")

    result = run_audit(codex_home)

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "fail"
    assert {
        "name": "sensitive-paths-untracked",
        "status": "fail",
        "details": "tracked sensitive paths: auth.json",
    } in report["checks"]


def test_audit_reports_missing_codex_home_without_traceback(tmp_path: Path) -> None:
    codex_home = tmp_path / "missing-codex-home"

    result = run_audit(codex_home)

    assert result.returncode == 1
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["status"] == "fail"
    assert {
        "name": "codex-home-exists",
        "status": "fail",
        "details": "directory is missing",
    } in report["checks"]
