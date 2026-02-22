"""Platform layer primitives for local orchestration over stateless Core."""

__version__ = "2.4.0"

from .context import condense_discussion_context
from .core_client import CoreClient, CoreClientError, CoreClientHTTPError
from .facade import PlatformFacade
from .mappers import contract_to_finding, finding_to_contract
from .session_state_machine import (
    apply_acceptance,
    apply_discussion_outcome_reason,
    apply_finding_revision,
    apply_re_evaluation_result,
    all_findings_considered,
    apply_discussion_status,
    describe_revision_changes,
    apply_rejection,
    first_unresolved_index,
    is_terminal_status,
    record_discussion_acceptance,
    record_discussion_rejection,
    next_available_index,
    next_index_for_lens,
    prior_outcomes_summary,
    record_ambiguity_answer,
    learning_session_payload,
    restore_learning_session,
)

__all__ = [
    "__version__",
    "CoreClient",
    "CoreClientError",
    "CoreClientHTTPError",
    "PlatformFacade",
    "condense_discussion_context",
    "finding_to_contract",
    "contract_to_finding",
    "is_terminal_status",
    "first_unresolved_index",
    "all_findings_considered",
    "next_available_index",
    "next_index_for_lens",
    "prior_outcomes_summary",
    "apply_discussion_status",
    "apply_discussion_outcome_reason",
    "apply_finding_revision",
    "apply_re_evaluation_result",
    "describe_revision_changes",
    "apply_acceptance",
    "apply_rejection",
    "record_discussion_acceptance",
    "record_discussion_rejection",
    "record_ambiguity_answer",
    "learning_session_payload",
    "restore_learning_session",
]
