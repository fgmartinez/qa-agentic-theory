"""Harness loop tests - the ones that would have been impossible before the
loop existed.

The single-pass harness in this chapter's first version could only be asked
"given this observation, what verdict?". These tests ask the harder question:
**"given this sequence of observations, what did the system actually do to the
customer's money?"** That question is what separates a testable agent from a
demo.
"""

from app.harness.corrector import NoOpCorrector
from app.harness.gateway import (
    FlakyPaymentGatewayClient,
    InMemoryPaymentGatewayClient,
    PartialAmountPaymentGatewayClient,
    ScriptedPaymentGatewayClient,
    SequencedPaymentGatewayClient,
)
from app.harness.service import ReviewHarness
from app.harness.types import (
    ExecutionResult,
    ExecutionStatus,
    NextAction,
    RefundCommand,
    TerminalReason,
)

APPROVED = ExecutionResult(
    status=ExecutionStatus.APPROVED,
    amount_matches_expected=True,
    state_persisted=True,
    executed_amount=120.0,
)
TIMEOUT = ExecutionResult(
    status=ExecutionStatus.TIMEOUT,
    amount_matches_expected=False,
    state_persisted=False,
)
REJECTED = ExecutionResult(
    status=ExecutionStatus.REJECTED,
    amount_matches_expected=True,
    state_persisted=True,
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_happy_path_terminates_and_persists_to_the_fake_ledger():
    gateway = InMemoryPaymentGatewayClient()
    harness = ReviewHarness(gateway=gateway)

    outcome = harness.run(case_id="C-4471", amount=120.0)

    assert outcome.next_action is NextAction.TERMINATE
    assert outcome.terminal_reason is TerminalReason.RESOLVED
    assert outcome.succeeded is True
    assert outcome.attempt_count == 1
    assert gateway.balance_for("C-4471") == 120.0


# ---------------------------------------------------------------------------
# RETRY - the loop recovering on its own
# ---------------------------------------------------------------------------
def test_transient_timeout_is_retried_and_then_succeeds():
    """The behaviour the old single-pass harness could only *recommend*."""
    gateway = FlakyPaymentGatewayClient(fail_times=1)
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    outcome = harness.run(case_id="C-9002", amount=50.0)

    assert outcome.succeeded is True
    assert outcome.attempt_count == 2
    assert [a.next_action for a in outcome.attempts] == [
        NextAction.RETRY,
        NextAction.TERMINATE,
    ]
    assert gateway.balance_for("C-9002") == 50.0


def test_retry_reuses_the_same_idempotency_key():
    """The property that makes retrying a refund safe at all.

    If this assertion ever fails, the harness is capable of double-refunding a
    customer on a transient timeout - the exact incident the retry branch was
    supposed to prevent.
    """
    gateway = SequencedPaymentGatewayClient([TIMEOUT, TIMEOUT, APPROVED])
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    harness.run(case_id="C-5150", amount=120.0)

    keys = {c.idempotency_key for c in gateway.commands}
    assert len(gateway.commands) == 3
    assert len(keys) == 1, "a retry must not mint a new idempotency key"


def test_idempotent_gateway_does_not_double_charge_on_replay():
    """End-to-end proof, at the ledger rather than at the key."""
    gateway = InMemoryPaymentGatewayClient()
    harness = ReviewHarness(gateway=gateway)

    harness.run(case_id="C-7001", amount=80.0)
    second = harness.run(case_id="C-7001", amount=80.0)

    assert gateway.call_count == 2
    assert second.execution.replayed is True
    assert gateway.balance_for("C-7001") == 80.0, "the effect happened exactly once"


def test_budget_exhaustion_escalates_with_its_own_terminal_reason():
    """Running out of attempts is not the same failure as a refusal."""
    gateway = ScriptedPaymentGatewayClient(TIMEOUT)
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    outcome = harness.run(case_id="C-3003", amount=10.0)

    assert outcome.attempt_count == 3
    assert outcome.terminal_reason is TerminalReason.ESCALATED_BUDGET_EXHAUSTED
    assert outcome.next_action is NextAction.ESCALATE
    assert outcome.needs_human is True


def test_backoff_delays_grow_and_are_not_applied_after_the_final_attempt():
    delays: list[float] = []
    harness = ReviewHarness(
        gateway=ScriptedPaymentGatewayClient(TIMEOUT),
        max_attempts=3,
        backoff_base_seconds=0.5,
        sleeper=delays.append,
    )

    harness.run(case_id="C-4004", amount=10.0)

    # Two sleeps for three attempts: you wait *between* tries, not after the
    # last one. A harness that sleeps after the final attempt burns latency
    # for nothing.
    assert delays == [0.5, 1.0]


# ---------------------------------------------------------------------------
# ESCALATE - stopping deliberately
# ---------------------------------------------------------------------------
def test_gateway_rejection_escalates_to_a_human_without_retrying():
    gateway = ScriptedPaymentGatewayClient(REJECTED)
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    outcome = harness.run(case_id="C-1187", amount=75.0)

    assert outcome.terminal_reason is TerminalReason.ESCALATED_BY_GATEWAY
    assert outcome.attempt_count == 1, "a definite 'no' must not be retried"


# ---------------------------------------------------------------------------
# CORRECT - the branch that had no implementation at all before
# ---------------------------------------------------------------------------
def test_partial_settlement_is_corrected_by_refunding_the_shortfall():
    """120 requested, rail caps at 90, harness issues the missing 30."""
    gateway = PartialAmountPaymentGatewayClient(cap=90.0)
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    outcome = harness.run(case_id="C-6006", amount=120.0)

    assert outcome.succeeded is True
    assert outcome.attempt_count == 2
    assert [a.next_action for a in outcome.attempts] == [
        NextAction.CORRECT,
        NextAction.TERMINATE,
    ]
    assert [a.command.amount for a in outcome.attempts] == [120.0, 30.0]
    assert gateway.balance_for("C-6006") == 120.0, "customer made whole, exactly once"


def test_correction_changes_the_idempotency_key():
    """The mirror image of the retry test.

    A retry must reuse the key; a correction must *not*, because refunding a
    different amount is a genuinely different operation. Sharing a key here
    would make the gateway replay the original partial refund and the
    shortfall would never be paid.
    """
    gateway = PartialAmountPaymentGatewayClient(cap=90.0)
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    outcome = harness.run(case_id="C-6007", amount=120.0)

    keys = [a.command.idempotency_key for a in outcome.attempts]
    assert len(set(keys)) == 2


def test_uncorrectable_gap_escalates_rather_than_guessing():
    """No ``executed_amount`` means no evidence to compute a remainder from."""
    mismatch_without_evidence = ExecutionResult(
        status=ExecutionStatus.APPROVED,
        amount_matches_expected=False,
        state_persisted=True,
        executed_amount=None,
    )
    harness = ReviewHarness(
        gateway=ScriptedPaymentGatewayClient(mismatch_without_evidence),
        max_attempts=3,
    )

    outcome = harness.run(case_id="C-8008", amount=100.0)

    assert outcome.terminal_reason is TerminalReason.ESCALATED_UNCORRECTABLE
    assert outcome.attempt_count == 1


def test_noop_corrector_turns_every_correction_into_an_escalation():
    """The conservative default is honoured rather than silently overridden."""
    harness = ReviewHarness(
        gateway=PartialAmountPaymentGatewayClient(cap=90.0),
        corrector=NoOpCorrector(),
        max_attempts=3,
    )

    outcome = harness.run(case_id="C-9009", amount=120.0)

    assert outcome.terminal_reason is TerminalReason.ESCALATED_UNCORRECTABLE
    assert outcome.needs_human is True


# ---------------------------------------------------------------------------
# Structural guarantees
# ---------------------------------------------------------------------------
def test_every_run_records_a_complete_audit_trail():
    gateway = SequencedPaymentGatewayClient([TIMEOUT, APPROVED])
    harness = ReviewHarness(gateway=gateway, max_attempts=3)

    outcome = harness.run(case_id="C-2002", amount=120.0)

    assert [a.number for a in outcome.attempts] == [1, 2]
    for attempt in outcome.attempts:
        assert isinstance(attempt.command, RefundCommand)
        assert attempt.execution is not None
        assert attempt.next_action in set(NextAction)


def test_max_attempts_below_one_is_rejected_at_construction():
    import pytest

    with pytest.raises(ValueError):
        ReviewHarness(gateway=InMemoryPaymentGatewayClient(), max_attempts=0)


def test_legacy_entry_point_still_works():
    """``execute_refund_decision`` is what earlier chapters call. It must keep
    working, now with loop semantics behind it."""
    harness = ReviewHarness(gateway=FlakyPaymentGatewayClient(fail_times=1))

    outcome = harness.execute_refund_decision(case_id="C-1010", amount=25.0)

    assert outcome.succeeded is True
    assert outcome.attempt_count == 2
