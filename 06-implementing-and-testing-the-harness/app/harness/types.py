"""Core data types for the review harness.

These types are deliberately independent from the decision-layer schemas
(``TransactionCase``, ``ReviewDecision``, ``RuleId`` in ``app/schemas.py``).
The harness only needs to know *what to execute* and *what came back* - not
how the decision was reasoned about. That separation is what lets the whole
harness be unit tested without an LLM anywhere in the picture.

Read this file first: every other module in ``app/harness/`` is written in
the vocabulary defined here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class ExecutionStatus(str, Enum):
    """What the payment system reported back - the raw signal, before any
    interpretation.

    Maps to the 'Signals / Observation' box in the harness diagram
    (Chapter 5). These are *observations*, not conclusions: ``TIMEOUT`` means
    "we did not get an answer", which is emphatically not the same as
    "the refund did not happen".
    """

    APPROVED = "approved"
    """The gateway confirmed the operation went through."""

    REJECTED = "rejected"
    """The gateway actively refused. A definite 'no', not an absence of answer."""

    PENDING = "pending"
    """Accepted but not settled. The outcome is genuinely not known yet."""

    TIMEOUT = "timeout"
    """No answer within the deadline. The operation may or may not have happened -
    this ambiguity is the entire reason idempotency keys exist."""


@dataclass(frozen=True)
class RefundCommand:
    """The concrete instruction handed to the gateway.

    ``idempotency_key`` is derived from the *logical intent* (case + amount),
    deliberately **not** from the attempt number. That is what makes a retry
    safe: attempt 1 and attempt 2 of the same refund carry the same key, so a
    correctly-implemented gateway performs the effect once and replays the
    stored result the second time. If the key included the attempt number,
    every retry would be a fresh operation and a timeout-then-retry would
    double-refund the customer.

    A ``CORRECT`` action changes the amount, which changes the key - correctly,
    because refunding a different amount *is* a different logical operation.
    """

    case_id: str
    amount: float
    attempt: int = 1

    @property
    def idempotency_key(self) -> str:
        """Stable across retries of the same logical refund; different when the
        amount changes."""
        raw = f"{self.case_id}|{self.amount:.2f}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def with_amount(self, amount: float, attempt: int) -> RefundCommand:
        """Produce the corrected command for a ``CORRECT`` action."""
        return RefundCommand(case_id=self.case_id, amount=amount, attempt=attempt)

    def next_attempt(self) -> RefundCommand:
        """Produce the same command again for a ``RETRY`` action - same key."""
        return RefundCommand(
            case_id=self.case_id, amount=self.amount, attempt=self.attempt + 1
        )


@dataclass(frozen=True)
class ExecutionResult:
    """What actually happened when the harness executed a decision.

    This is *evidence*. It comes from the system the harness called, never
    from the model's own account of what it thinks happened. Frozen on
    purpose: nothing downstream should be able to quietly adjust an
    observation before the resolver sees it.

    The optional fields carry the detail needed for correction and audit;
    they default so that the minimal three-field construction used in
    Chapter 6's early examples still works unchanged.
    """

    status: ExecutionStatus
    amount_matches_expected: bool
    state_persisted: bool
    executed_amount: float | None = None
    gateway_reference: str | None = None
    detail: str | None = None
    replayed: bool = False
    """True when the gateway recognised the idempotency key and returned a
    stored result instead of performing the effect again."""


class NextAction(str, Enum):
    """The resolver's verdict on what happens next.

    Deliberately not another LLM call - a deterministic state machine, so this
    step stays predictable even when the original decision wasn't.
    """

    TERMINATE = "terminate"
    """Done. The decision executed and the world reflects it."""

    CORRECT = "correct"
    """It executed, but not as asked. Adjust the parameters and go again."""

    RETRY = "retry"
    """No verdict yet (transient failure). Same parameters, go again."""

    ESCALATE = "escalate"
    """Stop and hand to a human. The harness must not decide this one alone."""


class TerminalReason(str, Enum):
    """*Why* the loop stopped - a different question from *what* the last
    action was, and the one an auditor actually asks.

    ``ESCALATED_BUDGET_EXHAUSTED`` in particular earns its own value: a run
    that escalates because it ran out of attempts is operationally very
    different from one that escalates because the gateway refused, even though
    both end in ``NextAction.ESCALATE``.
    """

    RESOLVED = "resolved"
    ESCALATED_BY_GATEWAY = "escalated_by_gateway"
    ESCALATED_BUDGET_EXHAUSTED = "escalated_budget_exhausted"
    ESCALATED_UNCORRECTABLE = "escalated_uncorrectable"


@dataclass(frozen=True)
class Attempt:
    """One full turn of the loop: what was sent, what came back, what the
    resolver made of it.

    The sequence of these is the audit trail. 'The refund succeeded' is a weak
    claim; 'attempt 1 timed out, attempt 2 replayed the same idempotency key
    and returned approved with state persisted' is a defensible one.
    """

    number: int
    command: RefundCommand
    execution: ExecutionResult
    next_action: NextAction


@dataclass(frozen=True)
class HarnessOutcome:
    """Everything the harness produced for one decision.

    ``execution`` and ``next_action`` describe the *final* state, so callers
    that only care about the verdict can read those two fields and ignore the
    rest. ``attempts`` and ``terminal_reason`` are what get persisted for
    audit - the pairing a DORA-style operational-resilience review actually
    asks to see.
    """

    execution: ExecutionResult
    next_action: NextAction
    terminal_reason: TerminalReason
    attempts: tuple[Attempt, ...] = field(default_factory=tuple)

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def succeeded(self) -> bool:
        return self.terminal_reason is TerminalReason.RESOLVED

    @property
    def needs_human(self) -> bool:
        return not self.succeeded
