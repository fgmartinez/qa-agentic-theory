"""Tests for the two smallest, most load-bearing pieces: the idempotency key
and the corrector.

Both are a handful of lines. Both, if wrong, cause a customer to be refunded
the wrong amount. Line count is a poor proxy for how much testing something
deserves.
"""

import pytest

from app.harness.corrector import NoOpCorrector, ShortfallCorrector
from app.harness.types import (
    ExecutionResult,
    ExecutionStatus,
    HarnessOutcome,
    NextAction,
    RefundCommand,
    TerminalReason,
)


# ---------------------------------------------------------------------------
# Idempotency key
# ---------------------------------------------------------------------------
def test_same_logical_refund_produces_the_same_key():
    a = RefundCommand(case_id="C-1", amount=120.0, attempt=1)
    b = RefundCommand(case_id="C-1", amount=120.0, attempt=7)
    assert a.idempotency_key == b.idempotency_key


def test_key_ignores_attempt_but_not_amount_or_case():
    base = RefundCommand(case_id="C-1", amount=120.0)
    assert base.idempotency_key != RefundCommand("C-1", 120.01).idempotency_key
    assert base.idempotency_key != RefundCommand("C-2", 120.0).idempotency_key


def test_key_is_stable_across_float_representations():
    """``120.0`` and ``120.00`` and ``120.000000001`` must not be three
    different refunds. Formatting to 2dp before hashing is what guarantees it,
    and this test is why that formatting cannot be removed as 'redundant'."""
    assert (
        RefundCommand("C-1", 120.0).idempotency_key
        == RefundCommand("C-1", 120.001).idempotency_key
    )


def test_next_attempt_preserves_the_key_and_increments_the_counter():
    first = RefundCommand(case_id="C-1", amount=120.0)
    second = first.next_attempt()
    assert second.attempt == 2
    assert second.idempotency_key == first.idempotency_key


def test_with_amount_changes_the_key():
    first = RefundCommand(case_id="C-1", amount=120.0)
    corrected = first.with_amount(30.0, attempt=2)
    assert corrected.idempotency_key != first.idempotency_key


# ---------------------------------------------------------------------------
# ShortfallCorrector
# ---------------------------------------------------------------------------
def approved(executed: float | None) -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.APPROVED,
        amount_matches_expected=False,
        state_persisted=True,
        executed_amount=executed,
    )


def test_shortfall_is_the_remainder_not_the_original_amount():
    """The bug this test exists to prevent over-refunds by the settled amount."""
    command = RefundCommand(case_id="C-1", amount=120.0)
    corrected = ShortfallCorrector().correct(command, approved(90.0))

    assert corrected is not None
    assert corrected.amount == 30.0
    assert corrected.attempt == 2


@pytest.mark.parametrize(
    "requested,executed",
    [(120.0, 120.0), (120.0, 150.0)],
)
def test_no_correction_when_nothing_is_owed(requested, executed):
    """Equal needs no fix; an over-refund is a human's problem, not a loop's."""
    command = RefundCommand(case_id="C-1", amount=requested)
    assert ShortfallCorrector().correct(command, approved(executed)) is None


def test_dust_shortfall_is_not_chased():
    command = RefundCommand(case_id="C-1", amount=120.0)
    assert ShortfallCorrector().correct(command, approved(119.999)) is None


def test_missing_evidence_refuses_to_guess():
    command = RefundCommand(case_id="C-1", amount=120.0)
    assert ShortfallCorrector().correct(command, approved(None)) is None


def test_noop_corrector_never_corrects():
    command = RefundCommand(case_id="C-1", amount=120.0)
    assert NoOpCorrector().correct(command, approved(90.0)) is None


# ---------------------------------------------------------------------------
# Outcome helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reason,expected_success",
    [
        (TerminalReason.RESOLVED, True),
        (TerminalReason.ESCALATED_BY_GATEWAY, False),
        (TerminalReason.ESCALATED_BUDGET_EXHAUSTED, False),
        (TerminalReason.ESCALATED_UNCORRECTABLE, False),
    ],
)
def test_only_resolved_counts_as_success(reason, expected_success):
    outcome = HarnessOutcome(
        execution=approved(120.0),
        next_action=NextAction.TERMINATE,
        terminal_reason=reason,
    )
    assert outcome.succeeded is expected_success
    assert outcome.needs_human is not expected_success


def test_execution_result_is_immutable():
    """Evidence must not be editable between observation and resolution."""
    result = approved(90.0)
    with pytest.raises(Exception):
        result.status = ExecutionStatus.REJECTED  # type: ignore[misc]
