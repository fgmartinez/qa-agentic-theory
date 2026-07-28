"""The decision layer's contract.

This is the 'Model / Decision' box of the Chapter 5 diagram, expressed as a
Protocol so the rest of the application never learns whether a decision came
from an LLM or from an ``if`` statement.

That indifference is worth more than it first looks. It means:

* the API, the harness, and every test can run with zero model calls;
* an LLM engine can be swapped in without touching a single caller;
* and the two can be compared against the same golden set (Chapter 9),
  because they satisfy the same interface.
"""

from __future__ import annotations

from typing import Protocol

from ..schemas import ReviewDecision, TransactionCase


class DecisionEngine(Protocol):
    """Turn a case into a proposed decision."""

    name: str

    def decide(self, case: TransactionCase) -> ReviewDecision: ...


class DecisionError(RuntimeError):
    """Raised when a decision cannot be produced *safely*.

    Deliberately not a fallback value. A decision engine that returns a
    made-up ``ReviewDecision`` when it fails is indistinguishable, downstream,
    from one that worked - which is how an unparseable model response ends up
    silently approving a refund. Raising forces the caller to choose what a
    failure means, and in ``main.py`` that choice is: escalate to a human.
    """
