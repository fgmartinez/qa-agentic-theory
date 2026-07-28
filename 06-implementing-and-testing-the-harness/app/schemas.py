"""API and decision-layer schemas.

**These are this notebook's own schemas, not a transcription of
``portfolio-risk-evaluator``'s.** That project's real ``TransactionCase`` /
``ReviewDecision`` / ``RuleId`` were not available to read when this was
written, and inventing plausible-looking field names that quietly do not match
production is worse than being explicit about the gap. Treat the models below
as a reference shape to adapt: keep the *structure* (a closed rule enum, a
decision that must cite one, a response that surfaces the harness outcome) and
rename the fields to whatever the trunk project actually uses.

See ``WIRING.md`` in this chapter for the adapter pattern that makes that swap
a single file's worth of work.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RuleId(str, Enum):
    """The **closed** set of rules a decision may cite.

    Closed is the entire point. If the decision layer could return a free-text
    justification, an LLM would happily invent a policy that sounds
    authoritative and does not exist - and nothing downstream could tell the
    difference. Constraining the citation to an enum turns hallucination from
    a subjective judgement ("is this rationale reasonable?") into a membership
    test ("is this string in the enum?") that a machine can fail a build on.

    Chapter 10 maps this control to the EU AI Act traceability requirement;
    Chapter 8 measures how often the model gets it right.
    """

    AUTO_APPROVE_LOW_VALUE = "AUTO_APPROVE_LOW_VALUE"
    REFUND_DUPLICATE_CHARGE = "REFUND_DUPLICATE_CHARGE"
    REFUND_SERVICE_FAILURE = "REFUND_SERVICE_FAILURE"
    ESCALATE_HIGH_VALUE = "ESCALATE_HIGH_VALUE"
    ESCALATE_SUSPECTED_FRAUD = "ESCALATE_SUSPECTED_FRAUD"
    ESCALATE_REPEAT_DISPUTER = "ESCALATE_REPEAT_DISPUTER"
    REJECT_OUTSIDE_WINDOW = "REJECT_OUTSIDE_WINDOW"


class ReviewAction(str, Enum):
    """What the decision layer proposes doing. Note that ``REFUND`` is a
    *proposal* - nothing has moved money at this point."""

    REFUND = "refund"
    REJECT = "reject"
    ESCALATE = "escalate"


class TransactionCase(BaseModel):
    """The input: one disputed transaction to review.

    Field constraints are a control, not decoration. ``amount`` cannot be
    negative because a negative refund is a payment, and an LLM that talks
    itself into ``amount=-500`` should be stopped by the schema long before it
    reaches a payment rail.
    """

    case_id: str = Field(..., min_length=3, max_length=64, examples=["C-4471"])
    amount: float = Field(..., ge=0, le=1_000_000, examples=[120.00])
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    merchant: str = Field(..., min_length=1, max_length=200)
    days_since_transaction: int = Field(..., ge=0, le=3650)
    customer_claim: str = Field(..., min_length=1, max_length=2000)
    prior_disputes: int = Field(default=0, ge=0)
    is_duplicate_charge: bool = False
    fraud_signals: list[str] = Field(default_factory=list)


class ReviewDecision(BaseModel):
    """The decision layer's output - a *proposal*, not an action.

    ``rule_id`` is required and typed. There is no ``other`` member and no
    free-text fallback, on purpose: a model that cannot ground its decision in
    a real rule must fail loudly rather than degrade gracefully into an
    unauditable answer.
    """

    action: ReviewAction
    rule_id: RuleId
    amount: float = Field(default=0.0, ge=0)
    rationale: str = Field(default="", max_length=2000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AttemptView(BaseModel):
    """One loop turn, flattened for the API response."""

    number: int
    requested_amount: float
    idempotency_key: str
    status: str
    executed_amount: float | None
    replayed: bool
    next_action: str


class ReviewResponse(BaseModel):
    """What ``POST /review`` returns.

    The shape encodes Chapter 6's central claim: **the decision alone cannot
    be the whole response once a harness exists.** ``decision`` is what the
    model proposed; ``terminal_reason`` and ``attempts`` are what actually
    happened to it. A caller that only reads ``decision`` gets the proposal;
    a caller that reads ``resolved`` gets the truth.
    """

    case_id: str
    correlation_id: str
    decision: ReviewDecision
    executed: bool = Field(
        ..., description="Whether the harness attempted execution at all."
    )
    resolved: bool = Field(
        ..., description="True only when the loop reached a terminal success."
    )
    terminal_reason: str | None = None
    final_status: str | None = None
    total_executed_amount: float | None = None
    attempts: list[AttemptView] = Field(default_factory=list)
    requires_human_review: bool = False


class HealthResponse(BaseModel):
    status: str
    gateway: str
    decision_engine: str
