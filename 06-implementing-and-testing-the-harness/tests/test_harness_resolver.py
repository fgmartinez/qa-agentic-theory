"""Resolver tests.

The resolver is a pure function over a small input space, so these tests do
something most test suites cannot: cover it **exhaustively**. 4 statuses x 2
booleans x 2 booleans = 16 combinations, and one test below walks all 16.
No sampling, no "representative case" hand-waving.

That exhaustiveness is the payoff for keeping the recovery logic pure and
LLM-free in the first place.
"""

import itertools

import pytest

from app.harness.resolver import resolve_next_action
from app.harness.types import ExecutionResult, ExecutionStatus, NextAction


@pytest.mark.parametrize(
    "status,amount_matches,persisted,expected",
    [
        # Transient failure -> retry, not silent success.
        (ExecutionStatus.TIMEOUT, False, False, NextAction.RETRY),
        # A timeout stays a retry even if the rest of the payload looks fine:
        # absence of an answer is not evidence of success.
        (ExecutionStatus.TIMEOUT, True, True, NextAction.RETRY),
        # Gateway actively refused -> a human looks at it.
        (ExecutionStatus.REJECTED, True, True, NextAction.ESCALATE),
        # Executed but not what was asked -> correct upstream, don't trust it.
        (ExecutionStatus.APPROVED, False, True, NextAction.CORRECT),
        # The happy path -> done.
        (ExecutionStatus.APPROVED, True, True, NextAction.TERMINATE),
        # Approved but nothing persisted: the rail says yes, our system has no
        # record. That disagreement is not something to resolve automatically.
        (ExecutionStatus.APPROVED, True, False, NextAction.ESCALATE),
        # Unexpected / unmatched combination -> fail safe.
        (ExecutionStatus.PENDING, True, False, NextAction.ESCALATE),
        (ExecutionStatus.PENDING, True, True, NextAction.ESCALATE),
    ],
)
def test_resolver_covers_every_branch(status, amount_matches, persisted, expected):
    result = ExecutionResult(
        status=status,
        amount_matches_expected=amount_matches,
        state_persisted=persisted,
    )
    assert resolve_next_action(result) == expected


def test_amount_mismatch_outranks_persistence_on_an_approved_call():
    """Pins branch *order*, not just branch coverage.

    An approved-but-wrong-amount result also satisfies the TERMINATE branch's
    ``state_persisted`` condition, so it matches two branches. This test fails
    loudly if someone reorders the ``if`` statements and quietly turns a
    partial refund into a success.
    """
    result = ExecutionResult(
        status=ExecutionStatus.APPROVED,
        amount_matches_expected=False,
        state_persisted=True,
        executed_amount=90.0,
    )
    assert resolve_next_action(result) is NextAction.CORRECT


def test_no_input_combination_is_unhandled():
    """The exhaustive sweep: all 16 inputs return a valid NextAction, none raise."""
    seen = set()
    for status, matches, persisted in itertools.product(
        ExecutionStatus, [True, False], [True, False]
    ):
        action = resolve_next_action(
            ExecutionResult(
                status=status,
                amount_matches_expected=matches,
                state_persisted=persisted,
            )
        )
        assert isinstance(action, NextAction)
        seen.add((status, matches, persisted))
    assert len(seen) == 16


def test_only_a_fully_clean_approval_can_terminate():
    """A safety invariant stated as a property rather than a table row.

    Nothing except APPROVED + amount match + persisted state may produce
    TERMINATE. This keeps holding if someone adds a fifth ``ExecutionStatus``
    later and forgets to add a row to the table above - which is exactly the
    kind of omission a table-driven test cannot catch on its own.
    """
    for status, matches, persisted in itertools.product(
        ExecutionStatus, [True, False], [True, False]
    ):
        action = resolve_next_action(
            ExecutionResult(
                status=status,
                amount_matches_expected=matches,
                state_persisted=persisted,
            )
        )
        if action is NextAction.TERMINATE:
            assert status is ExecutionStatus.APPROVED
            assert matches is True
            assert persisted is True
