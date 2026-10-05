"""Snapshot CLI. Standard output is an artifact receipt, never conversation data."""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import StatsError
from .collector import resolve_home, resolve_target, snapshot, timestamp
from .render import render


def main(argv=None):
    parser = argparse.ArgumentParser(prog="session-stats")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("snapshot")
    collect.add_argument(
        "--target", action="append", help="UUID, deep link, or @ Markdown reference"
    )
    collect.add_argument("--host", help="explicit reference host (local only)")
    collect.add_argument("--codex-home", type=Path)
    collect.add_argument("--timezone", default="UTC", help="IANA display timezone")
    collect.add_argument(
        "--output-dir", type=Path, required=True, help="task-owned durable visualization directory"
    )
    collect.add_argument(
        "--at", help="explicit ISO 8601 cutoff for reproducible historical snapshots"
    )
    package = commands.add_parser("package")
    package.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "package":
            from .package import package_plugin

            print(json.dumps({"plugin_path": str(package_plugin(args.output))}))
            return 0
        cutoff = timestamp(args.at) if args.at else datetime.now(UTC)
        if cutoff is None:
            raise StatsError("--at requires an ISO 8601 time with timezone.")
        target = resolve_target(args.target, args.host)
        ZoneInfo(args.timezone)
        data = snapshot(resolve_home(args.codex_home), target, cutoff)
        data["display_timezone"] = args.timezone
        serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        fragment = render(data)
        suffix = hashlib.sha256(serialized.encode()).hexdigest()[:16]
        output = args.output_dir.expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        json_path, html_path = (
            output / f"session-stats-{suffix}.json",
            output / f"session-stats-{suffix}.html",
        )
        # Immutable content-addressed artifacts; do not overwrite an unrelated/symlinked file.
        for path, content in ((json_path, serialized), (html_path, fragment)):
            if path.is_symlink():
                raise StatsError("Refusing a symlinked output file.")
            try:
                with path.open("x", encoding="utf-8") as stream:
                    stream.write(content)
            except FileExistsError:
                if path.read_text() != content:
                    raise StatsError(
                        "Snapshot output already exists with different content."
                    ) from None
        reference = "visualize" + json.dumps({"path": str(html_path)}, ensure_ascii=False) + ""
        print(
            json.dumps(
                {"json_path": str(json_path), "html_path": str(html_path), "reference": reference},
                ensure_ascii=False,
            )
        )
        return 0
    except ZoneInfoNotFoundError:
        print("Display timezone is unavailable.", file=sys.stderr)
    except StatsError as error:
        print(str(error), file=sys.stderr)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, OverflowError):
        # Never print exception text: source data and OS paths can contain private material.
        print(
            "Snapshot could not be produced: unavailable or unsupported local data/output.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
