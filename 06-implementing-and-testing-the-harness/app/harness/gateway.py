"""Payment gateway boundary - the only door to the outside world.

Everything the harness is allowed to affect beyond its own process goes
through ``PaymentGatewayClient``. The decision layer never imports this
module; only ``ReviewHarness`` (``service.py``) holds one. That single
chokepoint is what makes the boundary auditable: one place to log, one place
to rate-limit, one place to roll back, one place to point at in a code review
when asked "what stops the model touching a real payment rail?"

Five implementations live here, and the distinction between them is the point:

=============================  ======  ====================================
Class                          Kind    Exists because
=============================  ======  ====================================
InMemoryPaymentGatewayClient   fake    the walking skeleton has to actually run
ScriptedPaymentGatewayClient   stub    a test needs one specific observation
SequencedPaymentGatewayClient  stub    a test needs a specific *sequence*
FlakyPaymentGatewayClient      fake    the loop needs a realistic transient fault
PartialAmountPaymentGateway…   fake    CORRECT needs a reason to exist
=============================  ======  ====================================
"""

from __future__ import annotations

from typing import Protocol

from .types import ExecutionResult, ExecutionStatus, RefundCommand


class PaymentGatewayClient(Protocol):
    """The real contract.

    A production adapter (Stripe, Adyen, an internal rail - whatever the
    client actually uses) implements this exact method. Nothing else in the
    harness changes when the fake below is swapped for it: that is the whole
    return on defining the boundary as a Protocol rather than letting the
    service reach for a concrete class.
    """

    def issue_refund(self, command: RefundCommand) -> ExecutionResult:
        """Attempt the refund described by ``command``.

        Implementations **must** honour ``command.idempotency_key``: a second
        call carrying a key already seen must not perform the effect twice.
        """
        ...


class InMemoryPaymentGatewayClient:
    """Walking-skeleton fake: real interface, in-memory backend, honest
    idempotency.

    Not a mock that gets thrown away later - a fake that gets replaced by a
    real implementation of the same Protocol. It is what makes ``POST /review``
    runnable end-to-end today with no payment integration at all.

    It implements idempotency for real, because a fake that ignored the
    idempotency key would let the retry tests pass while the production
    adapter double-refunds. A fake should be *weaker* than production, never
    *more forgiving* - a fake that is more permissive than the real thing
    manufactures green tests for broken code.
    """

    def __init__(self) -> None:
        self._ledger: dict[str, float] = {}
        self._by_key: dict[str, ExecutionResult] = {}
        self.call_count: int = 0

    def issue_refund(self, command: RefundCommand) -> ExecutionResult:
        self.call_count += 1

        previous = self._by_key.get(command.idempotency_key)
        if previous is not None:
            # Same logical operation, already performed. Replay the stored
            # result; do NOT touch the ledger again.
            return ExecutionResult(
                status=previous.status,
                amount_matches_expected=previous.amount_matches_expected,
                state_persisted=previous.state_persisted,
                executed_amount=previous.executed_amount,
                gateway_reference=previous.gateway_reference,
                detail="replayed from idempotency key",
                replayed=True,
            )

        self._ledger[command.case_id] = (
            self._ledger.get(command.case_id, 0.0) + command.amount
        )
        result = ExecutionResult(
            status=ExecutionStatus.APPROVED,
            amount_matches_expected=True,
            state_persisted=True,
            executed_amount=command.amount,
            gateway_reference=f"gw_{command.idempotency_key}",
        )
        self._by_key[command.idempotency_key] = result
        return result

    def balance_for(self, case_id: str) -> float | None:
        """Test/debug helper - deliberately not part of the Protocol, so no
        production code can come to depend on it."""
        return self._ledger.get(case_id)


class ScriptedPaymentGatewayClient:
    """Test double that always returns one scripted observation.

    Kept distinct from ``InMemoryPaymentGatewayClient`` on purpose: that one
    is a *fake* standing in for production traffic; this is a *stub* that
    exists only to force a specific state (``TIMEOUT``, ``REJECTED``, an
    amount mismatch) that would be slow or impossible to trigger reliably
    against the fake.
    """

    def __init__(self, scripted_result: ExecutionResult) -> None:
        self._scripted_result = scripted_result
        self.commands: list[RefundCommand] = []

    def issue_refund(self, command: RefundCommand) -> ExecutionResult:
        self.commands.append(command)
        return self._scripted_result


class SequencedPaymentGatewayClient:
    """Returns a different scripted observation per call, in order.

    This is the double that makes *loop* behaviour testable: "time out twice,
    then approve" is a sequence, and you cannot express it with a stub that
    always answers the same thing. The last entry repeats if the loop runs
    longer than the script.
    """

    def __init__(self, results: list[ExecutionResult]) -> None:
        if not results:
            raise ValueError("SequencedPaymentGatewayClient needs at least one result")
        self._results = results
        self.commands: list[RefundCommand] = []

    def issue_refund(self, command: RefundCommand) -> ExecutionResult:
        index = min(len(self.commands), len(self._results) - 1)
        self.commands.append(command)
        return self._results[index]


class FlakyPaymentGatewayClient:
    """Times out for the first ``fail_times`` calls, then behaves like the
    in-memory fake.

    Models the realistic transient fault the ``RETRY`` branch exists for. Used
    in the loop tests to prove the harness recovers on its own rather than
    escalating a fault that would have cleared by itself.
    """

    def __init__(self, fail_times: int = 1) -> None:
        self._fail_times = fail_times
        self._inner = InMemoryPaymentGatewayClient()
        self.call_count: int = 0

    def issue_refund(self, command: RefundCommand) -> ExecutionResult:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                amount_matches_expected=False,
                state_persisted=False,
                detail=f"simulated transient timeout (call {self.call_count})",
            )
        return self._inner.issue_refund(command)

    def balance_for(self, case_id: str) -> float | None:
        return self._inner.balance_for(case_id)


class PartialAmountPaymentGatewayClient:
    """Approves, but only up to a cap - the ``CORRECT`` branch's reason to exist.

    A real rail does this: a partial refund, because the original capture was
    only partially settled. The operation *succeeded*, so it is not a retry
    case; it just did not do what was asked. The harness has to notice the gap
    and act on it rather than reporting success.
    """

    def __init__(self, cap: float) -> None:
        self._cap = cap
        self._inner = InMemoryPaymentGatewayClient()

    def issue_refund(self, command: RefundCommand) -> ExecutionResult:
        capped = min(command.amount, self._cap)
        inner_command = RefundCommand(
            case_id=command.case_id, amount=capped, attempt=command.attempt
        )
        result = self._inner.issue_refund(inner_command)
        return ExecutionResult(
            status=result.status,
            amount_matches_expected=capped == command.amount,
            state_persisted=result.state_persisted,
            executed_amount=capped,
            gateway_reference=result.gateway_reference,
            detail=None if capped == command.amount else f"capped at {self._cap:.2f}",
            replayed=result.replayed,
        )

    def balance_for(self, case_id: str) -> float | None:
        return self._inner.balance_for(case_id)
