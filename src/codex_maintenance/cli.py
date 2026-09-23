from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_maintenance.audit import audit_codex_home
from codex_maintenance.workflow import WorkflowError, WorkflowStore
from codex_maintenance.workflow.collector import register_run, unregister_run
from codex_maintenance.workflow.package import package_plugin
from codex_maintenance.workflow.server import close, export_report, monitor_url, serve


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

    package_parser = subparsers.add_parser("package-plugin", help="copy workflow plugin payload")
    package_parser.add_argument("--output", type=Path, help="new plugin directory")

    workflow_parser = subparsers.add_parser("workflow", help="manage a local workflow run")
    workflow_parser.add_argument("--db", type=Path, required=True, help="run SQLite database")
    workflow_commands = workflow_parser.add_subparsers(dest="action", required=True)
    start = workflow_commands.add_parser("start")
    start.add_argument("--session-id", required=True)
    start.add_argument("--plugin-data", type=Path)
    register = workflow_commands.add_parser("register")
    register.add_argument("run_id")
    register.add_argument("--plugin-data", type=Path, required=True)
    unregister = workflow_commands.add_parser("unregister")
    unregister.add_argument("run_id")
    unregister.add_argument("--plugin-data", type=Path, required=True)
    task = workflow_commands.add_parser("task")
    task.add_argument("run_id")
    task.add_argument("stage")
    task.add_argument("name")
    attempt = workflow_commands.add_parser("attempt")
    attempt.add_argument("task_id")
    bind = workflow_commands.add_parser("bind")
    bind.add_argument("attempt_id")
    bind.add_argument("agent_id")
    bind.add_argument("--turn-id")
    returned = workflow_commands.add_parser("returned")
    returned.add_argument("attempt_id")
    interrupted = workflow_commands.add_parser("interrupt")
    interrupted.add_argument("attempt_id")
    submit = workflow_commands.add_parser("submit")
    submit.add_argument("task_id")
    submit.add_argument("report", type=Path)
    accept = workflow_commands.add_parser("accept")
    accept.add_argument("task_id")
    accept.add_argument("version", type=int)
    rework = workflow_commands.add_parser("rework")
    rework.add_argument("task_id")
    revision = workflow_commands.add_parser("revision")
    revision.add_argument("review_task_id")
    revision.add_argument("synthesis_task_id")
    revision.add_argument("review_version", type=int)
    advance = workflow_commands.add_parser("advance")
    advance.add_argument("run_id")
    finish = workflow_commands.add_parser("finish")
    finish.add_argument("run_id")
    finish.add_argument("--plugin-data", type=Path)
    status = workflow_commands.add_parser("status")
    status.add_argument("run_id")
    server = workflow_commands.add_parser("serve")
    server.add_argument("run_id")
    server.add_argument("--port", type=int, default=0)
    server.add_argument("--plugin-data", type=Path)
    closing = workflow_commands.add_parser("close")
    closing.add_argument("run_id")
    url = workflow_commands.add_parser("url")
    url.add_argument("run_id")
    export = workflow_commands.add_parser("export")
    export.add_argument("run_id")
    export.add_argument("task_id")
    export.add_argument("version", type=int)
    export.add_argument("output", type=Path)
    observation = workflow_commands.add_parser("observe")
    observation.add_argument("session_id")
    observation.add_argument("kind")
    observation.add_argument("agent_id", nargs="?", default="")
    observation.add_argument("turn_id", nargs="?", default="")

    args = parser.parse_args(argv)
    if args.command == "audit":
        report = audit_codex_home(args.codex_home)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            _print_text_report(report)
        return 1 if report["status"] == "fail" else 0
    if args.command == "package-plugin":
        print(package_plugin(args.output))
        return 0
    if args.command == "workflow":
        try:
            return _run_workflow(args)
        except (WorkflowError, OSError, UnicodeError) as error:
            parser.error(str(error))
    return 2


def _run_workflow(args: argparse.Namespace) -> int:
    store = WorkflowStore(args.db)
    action = args.action
    result: object = None
    if action == "start":
        result = store.start_run(args.session_id)
        if args.plugin_data:
            register_run(args.plugin_data, args.db, result)
    elif action == "register":
        register_run(args.plugin_data, args.db, args.run_id)
    elif action == "unregister":
        unregister_run(args.plugin_data, args.run_id)
    elif action == "task":
        result = store.create_task(args.run_id, args.stage, args.name)
    elif action == "attempt":
        result = store.begin_attempt(args.task_id)
    elif action == "bind":
        store.bind_attempt(args.attempt_id, args.agent_id, args.turn_id)
    elif action == "returned":
        store.mark_returned(args.attempt_id)
    elif action == "interrupt":
        store.interrupt_attempt(args.attempt_id)
    elif action == "submit":
        result = store.submit_report_file(args.task_id, args.report)
    elif action == "accept":
        store.accept_report(args.task_id, args.version)
    elif action == "rework":
        store.rework_task(args.task_id)
    elif action == "revision":
        result = store.request_revision(
            args.review_task_id, args.synthesis_task_id, args.review_version
        )
    elif action == "advance":
        result = store.advance_stage(args.run_id)
    elif action == "finish":
        store.finish_run(args.run_id)
        if args.plugin_data:
            unregister_run(args.plugin_data, args.run_id)
    elif action == "status":
        result = store.snapshot(args.run_id)
    elif action == "serve":
        serve(args.db, args.run_id, args.port, args.plugin_data)
    elif action == "close":
        result = close(args.db, args.run_id)
    elif action == "url":
        result = monitor_url(args.db, args.run_id)
    elif action == "export":
        export_report(args.db, args.run_id, args.task_id, args.version, args.output)
    elif action == "observe":
        result = store.ingest_observation(args.session_id, args.kind, args.agent_id, args.turn_id)
    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _print_text_report(report: dict[str, object]) -> None:
    print(f"Codex home: {report['codex_home']}")
    print(f"Status: {report['status']}")
    for check in report["checks"]:
        assert isinstance(check, dict)
        print(f"- {check['status']}: {check['name']} ({check['details']})")
