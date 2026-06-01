from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_maintenance.audit import audit_codex_home


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="audit local Codex home safety")
    audit_parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path.home() / ".codex",
        help="Codex home directory to inspect",
    )
    audit_parser.add_argument("--json", action="store_true", help="write machine-readable JSON")

    args = parser.parse_args(argv)
    if args.command == "audit":
        report = audit_codex_home(args.codex_home)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            _print_text_report(report)
        return 1 if report["status"] == "fail" else 0
    return 2


def _print_text_report(report: dict[str, object]) -> None:
    print(f"Codex home: {report['codex_home']}")
    print(f"Status: {report['status']}")
    for check in report["checks"]:
        assert isinstance(check, dict)
        print(f"- {check['status']}: {check['name']} ({check['details']})")
