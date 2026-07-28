"""The ``CORRECT`` branch's missing half.

The resolver can *say* "correct this", but saying it is useless unless
something knows **how**. That is this module.

Correction is kept separate from the resolver for the same reason the
resolver is kept separate from the model: the resolver answers a
classification question (what kind of situation is this?) and the corrector
answers an arithmetic one (what should we send instead?). Fusing them
produces a function that is hard to test and easy to get subtly wrong.

Like the resolver, this is pure and deterministic. A corrector that called an
LLM to decide the new amount would reintroduce exactly the unpredictability
the harness exists to contain.
"""

from __future__ import annotations

from typing import Protocol

from .types import ExecutionResult, RefundCommand


class Corrector(Protocol):
    """Given what was asked and what actually happened, produce the next
    command - or ``None`` if this gap cannot be closed automatically."""

    def correct(
        self, command: RefundCommand, result: ExecutionResult
    ) -> RefundCommand | None: ...


class ShortfallCorrector:
    """Closes a partial-settlement gap by issuing the remainder.

    If 120.00 was requested and the rail only settled 90.00, the correction is
    a second refund for the outstanding 30.00 - not a re-send of the original
    120.00, which would over-refund by 90.00.

    Returns ``None`` (meaning "escalate, I cannot fix this") in three cases,
    each of which is a real failure mode rather than a defensive nicety:

    * **The gateway executed more than requested.** An over-refund is not
      something to paper over with more automation; a human needs to know.
    * **The shortfall is below the dust threshold.** Chasing a 0.004 remainder
      generates gateway calls forever and is worth less than the API call.
    * **The gateway did not report what it executed.** Without
      ``executed_amount`` there is nothing to compute a remainder from, and
      guessing is precisely the behaviour the harness is built to prevent.
    """

    def __init__(self, dust_threshold: float = 0.01) -> None:
        self._dust_threshold = dust_threshold

    def correct(
        self, command: RefundCommand, result: ExecutionResult
    ) -> RefundCommand | None:
        if result.executed_amount is None:
            # No evidence of what actually happened - refuse to guess.
            return None

        shortfall = round(command.amount - result.executed_amount, 2)

        if shortfall <= 0:
            # Executed the same or more than asked. Equal should not have
            # reached the corrector at all; more is an over-refund and is a
            # human's problem, not a loop's.
            return None

        if shortfall < self._dust_threshold:
            return None

        return RefundCommand(
            case_id=command.case_id,
            amount=shortfall,
            attempt=command.attempt + 1,
        )


class NoOpCorrector:
    """Never corrects - every ``CORRECT`` verdict becomes an escalation.

    The honest default for a system that has not yet decided what automatic
    correction should mean in its domain. Escalating a correctable case is a
    cost; silently mis-correcting one is an incident. Start here, and move to
    ``ShortfallCorrector`` when the domain rule is actually settled.
    """

    def correct(
        self, command: RefundCommand, result: ExecutionResult
    ) -> RefundCommand | None:
        return None
