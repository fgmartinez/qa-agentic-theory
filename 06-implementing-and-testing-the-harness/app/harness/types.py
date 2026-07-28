"""Core data types for the review harness.

These types are deliberately independent from the LLM-facing schemas
(TransactionCase, ReviewDecision, RuleId) that already live in the
project. The harness only needs a case id and an amount to act on -
it does not need to know how the decision was reasoned about, only
what to execute and what came back.
"""
from dataclasses import dataclass
from enum import Enum


class ExecutionStatus(str, Enum):
    """What the payment system reported back - the raw signal, before
    any interpretation. Maps to the 'Signals / Observation' box in the
    harness diagram: 'approved, rejected, or pending'."""

    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ExecutionResult:
    """What actually happened when the harness executed a decision.
    This is evidence - it comes from the system the harness called,
    never from the model's own account of what it thinks happened."""

    status: ExecutionStatus
    amount_matches_expected: bool
    state_persisted: bool


class NextAction(str, Enum):
    """The resolver's verdict. Deliberately not another LLM call - a
    deterministic state machine, so this step stays predictable even
    when the original decision wasn't."""

    TERMINATE = "terminate"
    CORRECT = "correct"
    RETRY = "retry"
    ESCALATE = "escalate"
