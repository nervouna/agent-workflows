"""Transactional business state and observed lifecycle events."""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codex_maintenance.workflow.model import STAGES, Observation, WorkflowError


def _id() -> str:
    return str(uuid.uuid4())


class WorkflowStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, stage INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'active', created_at REAL NOT NULL,
                    finished_at REAL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    stage INTEGER NOT NULL, name TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued',
                    accepted_version INTEGER, created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tasks_run_stage ON tasks(run_id, stage);
                CREATE TABLE IF NOT EXISTS review_basis (
                    review_task_id TEXT NOT NULL REFERENCES tasks(id),
                    synthesis_task_id TEXT NOT NULL REFERENCES tasks(id),
                    synthesis_version INTEGER NOT NULL,
                    PRIMARY KEY(review_task_id, synthesis_task_id)
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    review_task_id TEXT NOT NULL REFERENCES tasks(id),
                    review_version INTEGER NOT NULL,
                    synthesis_task_id TEXT NOT NULL REFERENCES tasks(id),
                    synthesis_version INTEGER NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                    number INTEGER NOT NULL, agent_id TEXT, turn_id TEXT,
                    returned INTEGER NOT NULL DEFAULT 0, observed_start INTEGER NOT NULL DEFAULT 0,
                    observed_stop INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
                    UNIQUE(task_id, number)
                );
                CREATE INDEX IF NOT EXISTS attempts_agent_turn ON attempts(agent_id, turn_id);
                CREATE TABLE IF NOT EXISTS reports (
                    task_id TEXT NOT NULL REFERENCES tasks(id), version INTEGER NOT NULL,
                    attempt_id TEXT NOT NULL REFERENCES attempts(id), path TEXT, content TEXT,
                    sha256 TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(task_id, version)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'hook', session_id TEXT NOT NULL,
                    kind TEXT NOT NULL, agent_id TEXT, turn_id TEXT,
                    tool_use_id TEXT, received_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS observations_lookup
                    ON observations(session_id, agent_id, turn_id, kind);
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _required(db: sqlite3.Connection, table: str, entity_id: str) -> sqlite3.Row:
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (entity_id,)).fetchone()
        if row is None:
            raise WorkflowError(f"unknown {table[:-1]}: {entity_id}")
        return row

    def start_run(self, session_id: str) -> str:
        if not session_id.strip():
            raise WorkflowError("session_id is required")
        run_id = _id()
        with self._write() as db:
            db.execute(
                "INSERT INTO runs(id, session_id, created_at) VALUES(?,?,?)",
                (run_id, session_id, time.time()),
            )
        return run_id

    def create_task(self, run_id: str, stage: str, name: str) -> str:
        if stage not in STAGES or not name.strip():
            raise WorkflowError("valid stage and nonempty task name are required")
        task_id = _id()
        with self._write() as db:
            run = self._required(db, "runs", run_id)
            if run["state"] != "active" or STAGES[run["stage"]] != stage:
                raise WorkflowError("task stage must be the current active stage")
            db.execute(
                "INSERT INTO tasks(id,run_id,stage,name,created_at) VALUES(?,?,?,?,?)",
                (task_id, run_id, run["stage"], name, time.time()),
            )
            if stage == "independent_review":
                synthesis = db.execute(
                    "SELECT * FROM tasks WHERE run_id=? AND stage=?",
                    (run_id, STAGES.index("synthesis")),
                ).fetchall()
                if not synthesis:
                    raise WorkflowError("independent review needs accepted synthesis")
                for item in synthesis:
                    if item["state"] != "accepted" or item["accepted_version"] is None:
                        raise WorkflowError("independent review needs accepted synthesis")
                    db.execute(
                        """INSERT INTO review_basis(
                            review_task_id,synthesis_task_id,synthesis_version
                        ) VALUES(?,?,?)""",
                        (task_id, item["id"], item["accepted_version"]),
                    )
        return task_id

    def begin_attempt(self, task_id: str) -> str:
        attempt_id = _id()
        with self._write() as db:
            task = self._required(db, "tasks", task_id)
            run = self._required(db, "runs", task["run_id"])
            if run["state"] != "active" or task["stage"] != run["stage"]:
                raise WorkflowError("task is outside the current active stage")
            previous = db.execute(
                "SELECT MAX(number) AS n FROM attempts WHERE task_id=?", (task_id,)
            ).fetchone()["n"]
            if previous and task["state"] != "rework":
                raise WorkflowError("rework must be requested before another attempt")
            db.execute(
                "INSERT INTO attempts(id,task_id,number,created_at) VALUES(?,?,?,?)",
                (attempt_id, task_id, (previous or 0) + 1, time.time()),
            )
            db.execute(
                "UPDATE tasks SET state='running', accepted_version=NULL WHERE id=?", (task_id,)
            )
        return attempt_id

    def bind_attempt(self, attempt_id: str, agent_id: str, turn_id: str | None = None) -> None:
        if not agent_id.strip() or (turn_id is not None and not turn_id.strip()):
            raise WorkflowError("agent_id and optional turn_id must be nonempty")
        with self._write() as db:
            attempt = self._required(db, "attempts", attempt_id)
            if attempt["agent_id"] and attempt["agent_id"] != agent_id:
                raise WorkflowError("attempt already bound to another agent")
            if attempt["turn_id"] and turn_id and attempt["turn_id"] != turn_id:
                raise WorkflowError("attempt already bound to another turn")
            task = self._required(db, "tasks", attempt["task_id"])
            run = self._required(db, "runs", task["run_id"])
            if run["state"] != "active":
                raise WorkflowError("run is not active")
            if turn_id is None and attempt["number"] == 1:
                starts = db.execute(
                    """SELECT DISTINCT turn_id FROM observations WHERE session_id=? AND agent_id=?
                    AND kind='SubagentStart'""",
                    (run["session_id"], agent_id),
                ).fetchall()
                if len(starts) == 1:
                    turn_id = starts[0]["turn_id"]
                elif len(starts) > 1:
                    raise WorkflowError("multiple agent turns require explicit turn_id")
            final_turn = turn_id or attempt["turn_id"]
            collision = (
                db.execute(
                    """SELECT a.id FROM attempts a JOIN tasks t ON t.id=a.task_id
                JOIN runs r ON r.id=t.run_id
                WHERE r.session_id=? AND a.agent_id=? AND a.turn_id=? AND a.id<>?""",
                    (run["session_id"], agent_id, final_turn, attempt_id),
                ).fetchone()
                if final_turn
                else None
            )
            if collision:
                raise WorkflowError("agent turn is already bound in this run")
            db.execute(
                "UPDATE attempts SET agent_id=?, turn_id=? WHERE id=?",
                (agent_id, final_turn, attempt_id),
            )
            if final_turn:
                self._replay(db, attempt_id, run["session_id"], agent_id, final_turn)

    @staticmethod
    def _replay(
        db: sqlite3.Connection, attempt_id: str, session_id: str, agent_id: str, turn_id: str
    ) -> None:
        kinds = {
            row["kind"]
            for row in db.execute(
                """SELECT DISTINCT kind FROM observations
                WHERE session_id=? AND agent_id=? AND turn_id=?""",
                (session_id, agent_id, turn_id),
            )
        }
        db.execute(
            "UPDATE attempts SET observed_start=?, observed_stop=? WHERE id=?",
            (int("SubagentStart" in kinds), int("SubagentStop" in kinds), attempt_id),
        )

    def ingest_observation(
        self,
        session_id: str,
        kind: str,
        agent_id: str = "",
        turn_id: str = "",
        *,
        source: str = "hook",
        tool_use_id: str | None = None,
    ) -> bool:
        Observation(session_id, kind, agent_id, turn_id, source, tool_use_id).validate()
        with self._write() as db:
            active = db.execute(
                "SELECT 1 FROM runs WHERE session_id=? AND state='active' LIMIT 1",
                (session_id,),
            ).fetchone()
            if not active:
                return False
            db.execute(
                """INSERT INTO observations(
                    id,source,session_id,kind,agent_id,turn_id,tool_use_id,received_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (_id(), source, session_id, kind, agent_id, turn_id, tool_use_id, time.time()),
            )
            if kind.startswith("Subagent"):
                if kind == "SubagentStart":
                    candidates = db.execute(
                        """SELECT a.id FROM attempts a JOIN tasks t ON t.id=a.task_id
                        JOIN runs r ON r.id=t.run_id
                        WHERE r.session_id=? AND r.state='active' AND a.agent_id=?
                        AND a.turn_id IS NULL AND a.number=1 AND a.returned=0""",
                        (session_id, agent_id),
                    ).fetchall()
                    already_bound = db.execute(
                        """SELECT 1 FROM attempts a JOIN tasks t ON t.id=a.task_id
                        JOIN runs r ON r.id=t.run_id
                        WHERE r.session_id=? AND a.agent_id=? AND a.turn_id=? LIMIT 1""",
                        (session_id, agent_id, turn_id),
                    ).fetchone()
                    if len(candidates) == 1 and not already_bound:
                        db.execute(
                            "UPDATE attempts SET turn_id=? WHERE id=?",
                            (turn_id, candidates[0]["id"]),
                        )
                column = "observed_start" if kind == "SubagentStart" else "observed_stop"
                db.execute(
                    f"""UPDATE attempts SET {column}=1
                    WHERE agent_id=? AND turn_id=? AND id IN (
                        SELECT a.id FROM attempts a JOIN tasks t ON t.id=a.task_id
                        JOIN runs r ON r.id=t.run_id
                        WHERE r.session_id=? AND r.state='active')""",
                    (agent_id, turn_id, session_id),
                )
            return True

    def mark_returned(self, attempt_id: str) -> None:
        with self._write() as db:
            attempt = self._required(db, "attempts", attempt_id)
            task = self._required(db, "tasks", attempt["task_id"])
            run = self._required(db, "runs", task["run_id"])
            if run["state"] != "active" or run["stage"] != task["stage"]:
                raise WorkflowError("attempt is outside active stage")
            latest = db.execute(
                "SELECT id FROM attempts WHERE task_id=? ORDER BY number DESC LIMIT 1",
                (task["id"],),
            ).fetchone()["id"]
            if attempt_id != latest:
                raise WorkflowError("only the latest attempt can return")
            if not attempt["agent_id"]:
                raise WorkflowError("attempt must be bound to an agent before return")
            if attempt["returned"]:
                return
            db.execute("UPDATE attempts SET returned=1 WHERE id=?", (attempt_id,))
            db.execute("UPDATE tasks SET state='returned' WHERE id=?", (task["id"],))

    def _submit(self, task_id: str, content: str, path: str | None) -> int:
        if not content.strip():
            raise WorkflowError("report must contain non-whitespace text")
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self._write() as db:
            task = self._required(db, "tasks", task_id)
            run = self._required(db, "runs", task["run_id"])
            if run["state"] != "active" or run["stage"] != task["stage"]:
                raise WorkflowError("task is outside active stage")
            attempt = db.execute(
                "SELECT * FROM attempts WHERE task_id=? ORDER BY number DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if not attempt or not attempt["returned"]:
                raise WorkflowError("latest attempt has not returned")
            version = db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM reports WHERE task_id=?", (task_id,)
            ).fetchone()[0]
            db.execute(
                """INSERT INTO reports(task_id,version,attempt_id,path,content,sha256,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    task_id,
                    version,
                    attempt["id"],
                    path,
                    content,
                    digest,
                    time.time(),
                ),
            )
            db.execute(
                "UPDATE tasks SET state='submitted',accepted_version=NULL WHERE id=?", (task_id,)
            )
            return version

    def submit_report(self, task_id: str, content: str) -> int:
        return self._submit(task_id, content, None)

    def submit_report_file(self, task_id: str, path: Path | str) -> int:
        report = Path(path).resolve(strict=True)
        if not report.is_file():
            raise WorkflowError("report path must be a file")
        return self._submit(task_id, report.read_text(encoding="utf-8"), str(report))

    @staticmethod
    def _report_valid(report: sqlite3.Row) -> bool:
        content = report["content"]
        if not content or not content.strip():
            return False
        if hashlib.sha256(content.encode()).hexdigest() != report["sha256"]:
            return False
        if not report["path"]:
            return True
        try:
            live_content = Path(report["path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
        return hashlib.sha256(live_content.encode()).hexdigest() == report["sha256"]

    def get_report(self, run_id: str, task_id: str, version: int) -> dict[str, object]:
        with self._connection() as db:
            task = self._required(db, "tasks", task_id)
            if task["run_id"] != run_id:
                raise WorkflowError("report is outside the requested run")
            report = db.execute(
                "SELECT * FROM reports WHERE task_id=? AND version=?", (task_id, version)
            ).fetchone()
            if not report:
                raise WorkflowError("unknown report version")
            content = report["content"]
            if not content or hashlib.sha256(content.encode()).hexdigest() != report["sha256"]:
                raise WorkflowError("stored report content is invalid")
            return dict(report)

    def accept_report(self, task_id: str, version: int) -> None:
        with self._write() as db:
            task = self._required(db, "tasks", task_id)
            if task["state"] not in {"submitted", "accepted"}:
                raise WorkflowError("task has no submitted report")
            latest = db.execute(
                "SELECT * FROM reports WHERE task_id=? ORDER BY version DESC LIMIT 1", (task_id,)
            ).fetchone()
            if not latest or latest["version"] != version or not self._report_valid(latest):
                raise WorkflowError("only an unchanged latest report can be accepted")
            db.execute(
                "UPDATE tasks SET accepted_version=?,state='accepted' WHERE id=?",
                (version, task_id),
            )

    def rework_task(self, task_id: str) -> None:
        with self._write() as db:
            task = self._required(db, "tasks", task_id)
            run = self._required(db, "runs", task["run_id"])
            if run["state"] != "active" or task["stage"] != run["stage"]:
                raise WorkflowError("task is outside active stage")
            if task["state"] not in {"returned", "submitted", "accepted"}:
                raise WorkflowError("task is not ready for rework")
            db.execute(
                "UPDATE tasks SET state='rework',accepted_version=NULL WHERE id=?", (task_id,)
            )

    def request_revision(
        self, review_task_id: str, synthesis_task_id: str, review_version: int
    ) -> str:
        revision_id = _id()
        with self._write() as db:
            review = self._required(db, "tasks", review_task_id)
            synthesis = self._required(db, "tasks", synthesis_task_id)
            run = self._required(db, "runs", review["run_id"])
            if (
                run["state"] != "active"
                or run["stage"] != STAGES.index("independent_review")
                or review["stage"] != run["stage"]
                or review["state"] != "submitted"
                or synthesis["run_id"] != run["id"]
                or synthesis["stage"] != STAGES.index("synthesis")
                or synthesis["state"] != "accepted"
            ):
                raise WorkflowError("revision requires submitted review and accepted synthesis")
            current_reviews = db.execute(
                """SELECT COUNT(*) FROM tasks WHERE run_id=? AND stage=?
                AND state<>'revision_requested'""",
                (run["id"], run["stage"]),
            ).fetchone()[0]
            if current_reviews != 1:
                raise WorkflowError("revision requires one current independent review task")
            report = db.execute(
                "SELECT * FROM reports WHERE task_id=? ORDER BY version DESC LIMIT 1",
                (review_task_id,),
            ).fetchone()
            if not report or report["version"] != review_version or not self._report_valid(report):
                raise WorkflowError("revision requires an unchanged latest review report")
            basis = db.execute(
                """SELECT synthesis_version FROM review_basis
                WHERE review_task_id=? AND synthesis_task_id=?""",
                (review_task_id, synthesis_task_id),
            ).fetchone()
            if not basis or basis["synthesis_version"] != synthesis["accepted_version"]:
                raise WorkflowError("review basis does not match current synthesis")
            db.execute(
                """INSERT INTO revisions(
                    id,run_id,review_task_id,review_version,
                    synthesis_task_id,synthesis_version,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    revision_id,
                    run["id"],
                    review_task_id,
                    review_version,
                    synthesis_task_id,
                    synthesis["accepted_version"],
                    time.time(),
                ),
            )
            db.execute(
                "UPDATE tasks SET state='revision_requested',accepted_version=NULL WHERE id=?",
                (review_task_id,),
            )
            db.execute(
                "UPDATE tasks SET state='rework',accepted_version=NULL WHERE id=?",
                (synthesis_task_id,),
            )
            db.execute("UPDATE runs SET stage=? WHERE id=?", (STAGES.index("synthesis"), run["id"]))
        return revision_id

    def advance_stage(self, run_id: str) -> str:
        with self._write() as db:
            run = self._required(db, "runs", run_id)
            if run["state"] != "active" or run["stage"] >= len(STAGES) - 1:
                raise WorkflowError("run cannot advance")
            self._require_accepted_stage(db, run_id, run["stage"])
            next_stage = run["stage"] + 1
            db.execute("UPDATE runs SET stage=? WHERE id=?", (next_stage, run_id))
            return STAGES[next_stage]

    def _require_accepted_stage(self, db: sqlite3.Connection, run_id: str, stage: int) -> None:
        tasks = db.execute(
            """SELECT * FROM tasks WHERE run_id=? AND stage=?
            AND (stage<>? OR state<>'revision_requested')""",
            (run_id, stage, STAGES.index("independent_review")),
        ).fetchall()
        if not tasks:
            raise WorkflowError("stage has no tasks")
        for task in tasks:
            if task["state"] != "accepted" or task["accepted_version"] is None:
                raise WorkflowError("all stage tasks need accepted reports")
            latest = db.execute(
                "SELECT * FROM reports WHERE task_id=? ORDER BY version DESC LIMIT 1",
                (task["id"],),
            ).fetchone()
            if (
                not latest
                or latest["version"] != task["accepted_version"]
                or not self._report_valid(latest)
            ):
                raise WorkflowError("accepted report changed or is not latest")

    def finish_run(self, run_id: str) -> None:
        with self._write() as db:
            run = self._required(db, "runs", run_id)
            if run["state"] == "finished":
                return
            if run["stage"] != len(STAGES) - 1:
                raise WorkflowError("run has not reached independent review")
            for stage in range(len(STAGES)):
                self._require_accepted_stage(db, run_id, stage)
            current_synthesis = {
                row["id"]: row["accepted_version"]
                for row in db.execute(
                    "SELECT id,accepted_version FROM tasks WHERE run_id=? AND stage=?",
                    (run_id, STAGES.index("synthesis")),
                )
            }
            current_reviews = db.execute(
                """SELECT id FROM tasks WHERE run_id=? AND stage=?
                AND state='accepted'""",
                (run_id, STAGES.index("independent_review")),
            ).fetchall()
            for review in current_reviews:
                basis = {
                    row["synthesis_task_id"]: row["synthesis_version"]
                    for row in db.execute(
                        """SELECT synthesis_task_id,synthesis_version FROM review_basis
                        WHERE review_task_id=?""",
                        (review["id"],),
                    )
                }
                if basis != current_synthesis:
                    raise WorkflowError("independent review does not cover latest synthesis")
            db.execute(
                "UPDATE runs SET state='finished',finished_at=? WHERE id=?", (time.time(), run_id)
            )

    def snapshot(self, run_id: str) -> dict[str, object]:
        with self._connection() as db:
            run = self._required(db, "runs", run_id)
            tasks = []
            for task in db.execute(
                "SELECT * FROM tasks WHERE run_id=? ORDER BY created_at,id", (run_id,)
            ):
                attempts = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM attempts WHERE task_id=? ORDER BY number", (task["id"],)
                    )
                ]
                for attempt in attempts:
                    for field in ("returned", "observed_start", "observed_stop"):
                        attempt[field] = bool(attempt[field])
                reports = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM reports WHERE task_id=? ORDER BY version", (task["id"],)
                    )
                ]
                # Report text is deliberately not part of the status snapshot.
                for report in reports:
                    report.pop("content")
                    persisted = db.execute(
                        "SELECT * FROM reports WHERE task_id=? AND version=?",
                        (task["id"], report["version"]),
                    ).fetchone()
                    report["valid"] = self._report_valid(persisted)
                item = dict(task)
                item["stage"] = STAGES[task["stage"]]
                item["attempts"] = attempts
                item["reports"] = reports
                item["acceptance_valid"] = bool(
                    item["accepted_version"]
                    and reports
                    and reports[-1]["version"] == item["accepted_version"]
                    and reports[-1]["valid"]
                )
                tasks.append(item)
            activity = db.execute(
                """SELECT COUNT(*) AS count, MAX(received_at) AS last_at
                FROM observations WHERE session_id=?""",
                (run["session_id"],),
            ).fetchone()
            revisions = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM revisions WHERE run_id=? ORDER BY created_at,id", (run_id,)
                )
            ]
            return {
                "id": run["id"],
                "session_id": run["session_id"],
                "stage": STAGES[run["stage"]],
                "stages": list(STAGES),
                "state": run["state"],
                "created_at": run["created_at"],
                "finished_at": run["finished_at"],
                "tasks": tasks,
                "revisions": revisions,
                "observations": activity["count"],
                "last_observation_at": activity["last_at"],
            }
