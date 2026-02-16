"""Core-native domain models used by stateless orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CoreFinding:
    """Core-native finding shape independent of legacy runtime types."""

    number: int
    severity: str
    lens: str
    location: str
    line_start: int | None = None
    line_end: int | None = None
    evidence: str = ""
    impact: str = ""
    options: list[str] = field(default_factory=list)
    flagged_by: list[str] = field(default_factory=list)
    ambiguity_type: str | None = None
    stale: bool = False
    status: str = "pending"
    author_response: str = ""
    discussion_turns: list[dict[str, Any]] = field(default_factory=list)
    revision_history: list[dict[str, Any]] = field(default_factory=list)
    outcome_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoreFinding":
        return cls(
            number=data.get("number", 0),
            severity=data.get("severity", "minor"),
            lens=data.get("lens", "unknown"),
            location=data.get("location", ""),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            evidence=data.get("evidence", ""),
            impact=data.get("impact", ""),
            options=list(data.get("options", [])),
            flagged_by=list(data.get("flagged_by", [])),
            ambiguity_type=data.get("ambiguity_type"),
            stale=bool(data.get("stale", False)),
            status=data.get("status", "pending"),
            author_response=data.get("author_response", ""),
            discussion_turns=list(data.get("discussion_turns", [])),
            revision_history=list(data.get("revision_history", [])),
            outcome_reason=data.get("outcome_reason", ""),
        )

    def to_dict(self, *, include_state: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "number": self.number,
            "severity": self.severity,
            "lens": self.lens,
            "location": self.location,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "evidence": self.evidence,
            "impact": self.impact,
            "options": self.options,
            "flagged_by": self.flagged_by,
            "ambiguity_type": self.ambiguity_type,
            "stale": self.stale,
        }
        if include_state:
            payload.update(
                {
                    "status": self.status,
                    "author_response": self.author_response,
                    "discussion_turns": self.discussion_turns,
                    "revision_history": self.revision_history,
                    "outcome_reason": self.outcome_reason,
                }
            )
        return payload