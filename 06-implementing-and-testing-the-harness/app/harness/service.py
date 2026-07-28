"""The harness itself: the object that turns a proposed decision into an
executed, observed, resolved outcome.

``ReviewHarness`` is the only thing in the codebase allowed to hold a
``PaymentGatewayClient``. The decision layer calls ``ReviewHarness``; it never
calls the gateway directly.

**This module is where the loop lives**, and the loop is the whole reason the
harness is not just a function call. Chapter 5 defines autonomy as::

    AUTONOMY = ACT + OBSERVE + CORRECT

A single ``execute -> resolve -> return`` pass implements ACT and OBSERVE and
then throws CORRECT away: it can *report* that a retry is needed without ever
retrying, which is a strictly worse position than not having a harness at all,
because it looks tested and defensible while the recovery path has never once
executed. ``run()`` below is CORRECT, made real.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .corrector import Corrector, ShortfallCorrector
from .gateway import PaymentGatewayClient
from .resolver import resolve_next_action
from .types import (
    Attempt,
    ExecutionResult,
    HarnessOutcome,
    NextAction,
    RefundCommand,
    TerminalReason,
)

logger = logging.getLogger("harness")

__all__ = ["ReviewHarness", "HarnessOutcome", "ExecutionResult", "NextAction"]


class ReviewHarness:
    """Executes one refund decision to a terminal state.

    Parameters
    ----------
    gateway:
        The only outward-facing dependency. Anything satisfying the Protocol
        works - fake, stub, or a real payment rail.
    corrector:
        How to close an amount gap when the rail executed something other than
        what was asked. Defaults to ``ShortfallCorrector``.
    max_attempts:
        Hard ceiling on loop turns. **Not optional in spirit** - an agent loop
        without a budget is an unbounded spend of money and time against a
        production system. When the budget runs out the harness escalates; it
        never gives up quietly.
    backoff_base_seconds:
        Delay before a retry, multiplied by the attempt number (linear
        backoff). Set to ``0`` to disable.
    sleeper:
        Injected so tests can assert on backoff without actually waiting.
        Production leaves it as ``time.sleep``.
    """

    def __init__(
        self,
        gateway: PaymentGatewayClient,
        corrector: Corrector | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._gateway = gateway
        self._corrector = corrector or ShortfallCorrector()
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleeper

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------
    def run(self, case_id: str, amount: float) -> HarnessOutcome:
        """ACT -> OBSERVE -> RESOLVE, repeating until a terminal state.

        Every exit path is explicit. There is no path out of this method that
        returns 'probably fine'.
        """
        command = RefundCommand(case_id=case_id, amount=amount, attempt=1)
        attempts: list[Attempt] = []

        for turn in range(1, self._max_attempts + 1):
            # --- ACT --------------------------------------------------
            execution = self._gateway.issue_refund(command)

            # --- OBSERVE / RESOLVE ------------------------------------
            next_action = resolve_next_action(execution)
            attempts.append(
                Attempt(
                    number=turn,
                    command=command,
                    execution=execution,
                    next_action=next_action,
                )
            )
            logger.info(
                "harness.attempt",
                extra={
                    "case_id": case_id,
                    "attempt": turn,
                    "requested_amount": command.amount,
                    "idempotency_key": command.idempotency_key,
                    "status": execution.status.value,
                    "executed_amount": execution.executed_amount,
                    "replayed": execution.replayed,
                    "next_action": next_action.value,
                },
            )

            # --- DECIDE WHAT HAPPENS NEXT -----------------------------
            if next_action is NextAction.TERMINATE:
                return self._finish(attempts, TerminalReason.RESOLVED)

            if next_action is NextAction.ESCALATE:
                return self._finish(attempts, TerminalReason.ESCALATED_BY_GATEWAY)

            if next_action is NextAction.RETRY:
                # Same idempotency key by construction - this is what makes
                # retrying a possibly-completed refund safe.
                command = command.next_attempt()
                if turn < self._max_attempts:
                    # Wait *between* tries, never after the last one: sleeping
                    # before a retry that will never happen is pure latency.
                    self._backoff(turn)
                continue

            if next_action is NextAction.CORRECT:
                corrected = self._corrector.correct(command, execution)
                if corrected is None:
                    # The corrector looked at the gap and declined to close
                    # it. That is a legitimate answer, and it means a human.
                    return self._finish(
                        attempts, TerminalReason.ESCALATED_UNCORRECTABLE
                    )
                command = corrected
                continue

        # Budget exhausted. Note this is a *distinct* terminal reason from a
        # gateway refusal even though both end in ESCALATE - an on-call
        # engineer needs to tell "the rail said no" apart from "we never got
        # an answer in three tries".
        return self._finish(attempts, TerminalReason.ESCALATED_BUDGET_EXHAUSTED)

    # ------------------------------------------------------------------
    # Backwards-compatible entry point
    # ------------------------------------------------------------------
    def execute_refund_decision(self, case_id: str, amount: float) -> HarnessOutcome:
        """Alias for :meth:`run`, kept because earlier chapters call it by
        this name."""
        return self.run(case_id=case_id, amount=amount)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _backoff(self, turn: int) -> None:
        if self._backoff_base_seconds > 0:
            self._sleep(self._backoff_base_seconds * turn)

    @staticmethod
    def _finish(attempts: list[Attempt], reason: TerminalReason) -> HarnessOutcome:
        last = attempts[-1]
        final_action = (
            NextAction.TERMINATE
            if reason is TerminalReason.RESOLVED
            else NextAction.ESCALATE
        )
        return HarnessOutcome(
            execution=last.execution,
            next_action=final_action,
            terminal_reason=reason,
            attempts=tuple(attempts),
        )
