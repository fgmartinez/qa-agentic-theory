"""The harness itself: the object that turns a proposed decision into
an executed, observed, resolved outcome.

ReviewHarness is the only thing in the codebase allowed to hold a
PaymentGatewayClient. The LLM/decision layer calls ReviewHarness; it
never calls the gateway directly.
"""
from dataclasses import dataclass

from .gateway import PaymentGatewayClient
from .resolver import resolve_next_action
from .types import ExecutionResult, NextAction


@dataclass(frozen=True)
class HarnessOutcome:
    """Everything the harness produced for one decision: the raw
    evidence (execution) and the deterministic verdict on what happens
    next (next_action). Both should be persisted alongside the
    original ReviewDecision for audit - this pairing is what a DORA-
    style resilience/traceability review will actually ask to see."""

    execution: ExecutionResult
    next_action: NextAction


class ReviewHarness:
    def __init__(self, gateway: PaymentGatewayClient) -> None:
        self._gateway = gateway

    def execute_refund_decision(self, case_id: str, amount: float) -> HarnessOutcome:
        execution = self._gateway.issue_refund(case_id=case_id, amount=amount)
        next_action = resolve_next_action(execution)
        return HarnessOutcome(execution=execution, next_action=next_action)
