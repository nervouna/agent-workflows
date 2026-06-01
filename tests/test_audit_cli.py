import json
import subprocess
import sys
from pathlib import Path


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


def test_audit_reports_clean_codex_home(tmp_path: Path) -> None:
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

    result = subprocess.run(
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

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert all(check["status"] == "pass" for check in report["checks"])


def test_audit_fails_when_sensitive_runtime_file_is_tracked(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    init_git_repo(codex_home)
    (codex_home / ".gitignore").write_text("*\n!/.gitignore\n", encoding="utf-8")
    (codex_home / "auth.json").write_text('{"token":"redacted"}\n', encoding="utf-8")
    git(codex_home, "add", "--force", "auth.json")

    result = subprocess.run(
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

    result = subprocess.run(
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

    assert result.returncode == 1
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["status"] == "fail"
    assert {
        "name": "codex-home-exists",
        "status": "fail",
        "details": "directory is missing",
    } in report["checks"]
