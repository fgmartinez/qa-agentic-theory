"""Payment gateway boundary.

Everything the harness is allowed to affect in the outside world goes
through PaymentGatewayClient. The LLM decision layer never imports
this module directly - only ReviewHarness (service.py) does. That is
what makes the boundary auditable: one chokepoint, one place to log,
rate-limit, or roll back.
"""
from typing import Protocol

from .types import ExecutionResult, ExecutionStatus


class PaymentGatewayClient(Protocol):
    """The real contract. A production adapter (Stripe, an internal
    gateway, whatever the FinTech client's actual rail is) implements
    this exact interface - nothing about the harness changes when the
    fake below is swapped out for it."""

    def issue_refund(self, case_id: str, amount: float) -> ExecutionResult: ...


class InMemoryPaymentGatewayClient:
    """Walking-skeleton fake: real interface, in-memory backend, always
    succeeds. This is what makes /review runnable end-to-end today
    without a real payment integration - not a mock that gets thrown
    away later, a fake that gets replaced by a real implementation of
    the same Protocol."""

    def __init__(self) -> None:
        self._ledger: dict[str, float] = {}

    def issue_refund(self, case_id: str, amount: float) -> ExecutionResult:
        self._ledger[case_id] = amount
        return ExecutionResult(
            status=ExecutionStatus.APPROVED,
            amount_matches_expected=True,
            state_persisted=True,
        )

    def balance_for(self, case_id: str) -> float | None:
        """Test/debug helper - not part of the Protocol."""
        return self._ledger.get(case_id)


class ScriptedPaymentGatewayClient:
    """Test double for exercising the resolver's non-happy paths
    (timeout, rejection, amount mismatch) without touching a real
    gateway. Kept distinct from InMemoryPaymentGatewayClient on
    purpose: that one is a *fake* standing in for production traffic;
    this one is a *stub* that exists only to script a scenario for a
    specific test.
    """

    def __init__(self, scripted_result: ExecutionResult) -> None:
        self._scripted_result = scripted_result

    def issue_refund(self, case_id: str, amount: float) -> ExecutionResult:
        return self._scripted_result
