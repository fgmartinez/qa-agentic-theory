"""Decision-engine tests.

Notice what these are: ordinary, fast, deterministic unit tests of business
logic. No model, no judge, no threshold, no flake. That is the argument for
keeping a rule-based engine in the codebase - the policy itself stays testable
in the classical sense, and only the *replacement* of that policy by a model
needs the statistical machinery of Chapter 8.
"""

import pytest

from app.decision.rules import RuleBasedDecisionEngine
from app.schemas import ReviewAction, RuleId, TransactionCase

engine = RuleBasedDecisionEngine()


def case(**overrides) -> TransactionCase:
    """A clean, mid-value, in-window case. Each test perturbs one field, so
    the assertion is unambiguously about that field."""
    defaults = dict(
        case_id="C-0001",
        amount=100.0,
        currency="EUR",
        merchant="Example Store",
        days_since_transaction=10,
        customer_claim="Item never arrived.",
        prior_disputes=0,
        is_duplicate_charge=False,
        fraud_signals=[],
    )
    defaults.update(overrides)
    return TransactionCase(**defaults)


@pytest.mark.parametrize(
    "overrides,expected_action,expected_rule",
    [
        ({}, ReviewAction.REFUND, RuleId.REFUND_SERVICE_FAILURE),
        (
            {"amount": 10.0},
            ReviewAction.REFUND,
            RuleId.AUTO_APPROVE_LOW_VALUE,
        ),
        (
            {"is_duplicate_charge": True},
            ReviewAction.REFUND,
            RuleId.REFUND_DUPLICATE_CHARGE,
        ),
        (
            {"amount": 900.0},
            ReviewAction.ESCALATE,
            RuleId.ESCALATE_HIGH_VALUE,
        ),
        (
            {"days_since_transaction": 400},
            ReviewAction.REJECT,
            RuleId.REJECT_OUTSIDE_WINDOW,
        ),
        (
            {"prior_disputes": 9},
            ReviewAction.ESCALATE,
            RuleId.ESCALATE_REPEAT_DISPUTER,
        ),
        (
            {"fraud_signals": ["velocity", "mismatched_bin"]},
            ReviewAction.ESCALATE,
            RuleId.ESCALATE_SUSPECTED_FRAUD,
        ),
    ],
)
def test_each_rule_fires_on_its_own_trigger(overrides, expected_action, expected_rule):
    decision = engine.decide(case(**overrides))
    assert decision.action is expected_action
    assert decision.rule_id is expected_rule


# ---------------------------------------------------------------------------
# Precedence - the part that actually breaks in review
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "overrides,expected_rule",
    [
        # Fraud beats a tiny amount: never auto-approve a flagged case.
        (
            {"amount": 5.0, "fraud_signals": ["velocity"]},
            RuleId.ESCALATE_SUSPECTED_FRAUD,
        ),
        # Fraud beats high value.
        (
            {"amount": 5000.0, "fraud_signals": ["velocity"]},
            RuleId.ESCALATE_SUSPECTED_FRAUD,
        ),
        # Out-of-window beats high value: reject, don't waste a human on it.
        (
            {"amount": 5000.0, "days_since_transaction": 400},
            RuleId.REJECT_OUTSIDE_WINDOW,
        ),
        # Repeat disputer beats a duplicate-charge refund.
        (
            {"prior_disputes": 9, "is_duplicate_charge": True},
            RuleId.ESCALATE_REPEAT_DISPUTER,
        ),
        # High value beats a duplicate-charge refund.
        (
            {"amount": 900.0, "is_duplicate_charge": True},
            RuleId.ESCALATE_HIGH_VALUE,
        ),
    ],
)
def test_rule_precedence_when_several_conditions_match(overrides, expected_rule):
    assert engine.decide(case(**overrides)).rule_id is expected_rule


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "amount,expected_rule",
    [
        (25.0, RuleId.AUTO_APPROVE_LOW_VALUE),   # at the threshold: inclusive
        (25.01, RuleId.REFUND_SERVICE_FAILURE),  # just over
        (500.0, RuleId.REFUND_SERVICE_FAILURE),  # at the ceiling: not yet high
        (500.01, RuleId.ESCALATE_HIGH_VALUE),    # just over
    ],
)
def test_amount_thresholds_are_inclusive_where_documented(amount, expected_rule):
    assert engine.decide(case(amount=amount)).rule_id is expected_rule


@pytest.mark.parametrize(
    "days,expected_rule",
    [
        (180, RuleId.REFUND_SERVICE_FAILURE),  # last day inside the window
        (181, RuleId.REJECT_OUTSIDE_WINDOW),   # first day outside
    ],
)
def test_refund_window_boundary(days, expected_rule):
    assert engine.decide(case(days_since_transaction=days)).rule_id is expected_rule


# ---------------------------------------------------------------------------
# Invariants that must hold for every case
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"amount": 0.0},
        {"amount": 5000.0},
        {"days_since_transaction": 0},
        {"days_since_transaction": 3650},
        {"prior_disputes": 100},
        {"fraud_signals": ["a", "b", "c"]},
        {"is_duplicate_charge": True, "amount": 24.0},
    ],
)
def test_every_decision_is_grounded_and_coherent(overrides):
    """Two invariants, checked across the input space.

    1. The cited rule is always a real member of the closed enum.
    2. A non-refund never carries money.

    Invariant 2 matters more than it looks: an escalation with ``amount=120``
    is the kind of thing a downstream service happily executes.
    """
    decision = engine.decide(case(**overrides))
    assert decision.rule_id in set(RuleId)
    if decision.action is not ReviewAction.REFUND:
        assert decision.amount == 0.0


def test_refund_amount_always_matches_the_case_amount():
    for amount in (1.0, 24.99, 25.0, 100.0, 499.99):
        decision = engine.decide(case(amount=amount))
        if decision.action is ReviewAction.REFUND:
            assert decision.amount == amount


def test_engine_is_deterministic():
    """Same input, same output - twenty times.

    Trivially true here, and that is the point: it is the property the
    LLM-backed engine cannot promise, and the reason Chapter 8 exists.
    """
    fixed = case(amount=310.0, customer_claim="Charged twice for one order.")
    decisions = {engine.decide(fixed).model_dump_json() for _ in range(20)}
    assert len(decisions) == 1
