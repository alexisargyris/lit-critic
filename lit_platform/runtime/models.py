"""
Data structures and exceptions for the lit-critic system.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLMClient

from .config import DEFAULT_MODEL, AVAILABLE_MODELS


class CoordinatorError(Exception):
    """Raised when the coordinator fails to produce valid output after all retries."""

    def __init__(self, message: str, raw_output: str = "", attempts: int = 0):
        super().__init__(message)
        self.raw_output = raw_output
        self.attempts = attempts


@dataclass
class LearningData:
    """Tracks learning during a session."""
    project_name: str = "Unknown"
    review_count: int = 0
    preferences: list[dict] = field(default_factory=list)      # Findings rejected as non-problems
    blind_spots: list[dict] = field(default_factory=list)      # Recurring issues author accepts
    resolutions: list[dict] = field(default_factory=list)      # How author typically fixes things
    ambiguity_intentional: list[dict] = field(default_factory=list)
    ambiguity_accidental: list[dict] = field(default_factory=list)
    
    # Session tracking
    session_rejections: list[dict] = field(default_factory=list)
    session_acceptances: list[dict] = field(default_factory=list)
    session_ambiguity_answers: list[dict] = field(default_factory=list)


@dataclass
class Finding:
    """A single editorial finding."""
    number: int
    severity: str  # critical, major, minor
    lens: str      # prose, structure, logic, clarity, continuity
    location: str
    line_start: Optional[int] = None   # First line of the issue (1-based), from lens output
    line_end: Optional[int] = None     # Last line of the issue (1-based), from lens output
    evidence: str = ""
    impact: str = ""
    options: list[str] = field(default_factory=list)
    flagged_by: list[str] = field(default_factory=list)
    ambiguity_type: Optional[str] = None
    stale: bool = False                # True when the finding's text region was edited by the author
    
    # Discussion state
    status: str = "pending"  # pending, accepted, rejected, revised, withdrawn, escalated, discussed
    author_response: str = ""
    discussion_turns: list[dict] = field(default_factory=list)   # [{role: "user"/"assistant", content: "..."}]
    revision_history: list[dict] = field(default_factory=list)   # Previous versions of this finding
    outcome_reason: str = ""                                     # Why/how the finding was resolved
    
    def to_dict(self, include_state: bool = False) -> dict:
        """Convert finding to dictionary. If include_state=True, includes discussion state."""
        result = {
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
            result["status"] = self.status
            result["author_response"] = self.author_response
            result["discussion_turns"] = self.discussion_turns
            result["revision_history"] = self.revision_history
            result["outcome_reason"] = self.outcome_reason
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        """Create Finding from dictionary."""
        finding = cls(
            number=data.get("number", 0),
            severity=data.get("severity", "minor"),
            lens=data.get("lens", "unknown"),
            location=data.get("location", ""),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            evidence=data.get("evidence", ""),
            impact=data.get("impact", ""),
            options=data.get("options", []),
            flagged_by=data.get("flagged_by", []),
            ambiguity_type=data.get("ambiguity_type"),
            stale=data.get("stale", False),
        )
        finding.status = data.get("status", "pending")
        finding.author_response = data.get("author_response", "")
        finding.discussion_turns = data.get("discussion_turns", [])
        finding.revision_history = data.get("revision_history", [])
        finding.outcome_reason = data.get("outcome_reason", "")
        return finding


@dataclass
class LensResult:
    """Output from a single lens analysis."""
    lens_name: str
    findings: list[dict]
    raw_output: str
    error: Optional[str] = None


@dataclass 
class SessionState:
    """Full state for a review session.

    The ``db_conn`` and ``session_id`` fields tie the in-memory state to the
    SQLite database so that every mutation can be auto-saved.  When
    ``db_conn`` is ``None`` (e.g. in tests), auto-save is silently skipped.
    
    Dual-LLM support: The ``discussion_model`` and ``discussion_client`` fields
    allow using a different (typically cheaper/faster) model for discussion
    than for analysis. When ``discussion_model`` is ``None``, the analysis
    model/client is used for both.
    """
    client: "LLMClient"
    scene_content: str
    scene_path: str
    project_path: Path
    indexes: dict[str, str]
    findings: list[Finding] = field(default_factory=list)
    glossary_issues: list[str] = field(default_factory=list)
    learning: LearningData = field(default_factory=LearningData)
    discussion_history: list[dict] = field(default_factory=list)
    model: str = field(default_factory=lambda: DEFAULT_MODEL)
    discussion_model: Optional[str] = None  # None = use analysis model
    discussion_client: Optional["LLMClient"] = None  # None = use analysis client
    db_conn: Optional[sqlite3.Connection] = field(default=None, repr=False)
    session_id: Optional[int] = None

    @property
    def model_id(self) -> str:
        """Full API model identifier (e.g. 'claude-sonnet-4-5-20250929' or 'gpt-4o')."""
        return AVAILABLE_MODELS[self.model]["id"]

    @property
    def model_provider(self) -> str:
        """Provider name (e.g. 'anthropic' or 'openai')."""
        return AVAILABLE_MODELS[self.model]["provider"]

    @property
    def model_max_tokens(self) -> int:
        """Max tokens for the selected model."""
        return AVAILABLE_MODELS[self.model]["max_tokens"]

    @property
    def model_label(self) -> str:
        """Human-readable label for the selected model."""
        return AVAILABLE_MODELS[self.model]["label"]

    @property
    def discussion_model_id(self) -> str:
        """Full API model identifier for discussion (falls back to analysis model if not set)."""
        model = self.discussion_model or self.model
        return AVAILABLE_MODELS[model]["id"]

    @property
    def discussion_model_provider(self) -> str:
        """Provider name for discussion model (falls back to analysis model if not set)."""
        model = self.discussion_model or self.model
        return AVAILABLE_MODELS[model]["provider"]

    @property
    def discussion_model_label(self) -> str:
        """Human-readable label for discussion model (falls back to analysis model if not set)."""
        model = self.discussion_model or self.model
        return AVAILABLE_MODELS[model]["label"]

    @property
    def effective_discussion_client(self) -> "LLMClient":
        """The LLM client to use for discussion (falls back to analysis client if not set)."""
        return self.discussion_client or self.client
