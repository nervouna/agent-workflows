"""Shared workflow names and event contract."""

from __future__ import annotations

from dataclasses import dataclass

STAGES = ("scan", "review", "synthesis", "independent_review")
OBSERVATIONS = frozenset(
    {"SubagentStart", "SubagentStop", "SessionStart", "SessionEnd", "Interrupt", "Stop"}
)


class WorkflowError(ValueError):
    """A requested workflow transition is invalid."""


@dataclass(frozen=True)
class Observation:
    session_id: str
    kind: str
    agent_id: str = ""
    turn_id: str = ""
    source: str = "hook"
    tool_use_id: str | None = None

    def validate(self) -> None:
        if self.kind not in OBSERVATIONS or not self.session_id.strip():
            raise WorkflowError("invalid lifecycle observation")
        if self.kind.startswith("Subagent") and not all(
            value.strip() for value in (self.agent_id, self.turn_id)
        ):
            raise WorkflowError("invalid lifecycle observation")
