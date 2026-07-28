"""API-level tests, through FastAPI's TestClient.

These are the integration layer of the pyramid for this service: real routing,
real Pydantic validation, real harness, fake payment rail. They answer the
question the unit tests structurally cannot - **does the wiring actually hold
together, and does the response tell the truth about what happened?**
"""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.harness.gateway import (
    InMemoryPaymentGatewayClient,
    PartialAmountPaymentGatewayClient,
    ScriptedPaymentGatewayClient,
)
from app.harness.types import ExecutionResult, ExecutionStatus


@pytest.fixture(autouse=True)
def fresh_gateway():
    """Reset the module-level ledger between tests.

    Module-level state is the pragmatic choice for a walking skeleton, but it
    makes tests order-dependent unless something resets it. Making that reset
    explicit and automatic is cheaper than debugging a suite that passes alone
    and fails together.
    """
    original = main.gateway
    main.gateway = InMemoryPaymentGatewayClient()
    yield main.gateway
    main.gateway = original


@pytest.fixture
def client():
    return TestClient(main.app)


def payload(**overrides) -> dict:
    base = {
        "case_id": "C-4471",
        "amount": 120.0,
        "currency": "EUR",
        "merchant": "Example Store",
        "days_since_transaction": 10,
        "customer_claim": "Charged twice for a single order.",
        "prior_disputes": 0,
        "is_duplicate_charge": True,
        "fraud_signals": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Health and metadata
# ---------------------------------------------------------------------------
def test_health_reports_the_wiring_that_matters(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["decision_engine"] == "rule-based"
    assert "PaymentGatewayClient" in body["gateway"]


def test_rules_endpoint_publishes_the_closed_set(client):
    rules = client.get("/rules").json()["rules"]
    assert "REFUND_DUPLICATE_CHARGE" in rules
    assert "REFUND_GOODWILL_GESTURE" not in rules


# ---------------------------------------------------------------------------
# The happy path, end to end
# ---------------------------------------------------------------------------
def test_duplicate_charge_is_refunded_and_reported_as_resolved(client, fresh_gateway):
    response = client.post("/review", json=payload())
    assert response.status_code == 200

    body = response.json()
    assert body["decision"]["rule_id"] == "REFUND_DUPLICATE_CHARGE"
    assert body["executed"] is True
    assert body["resolved"] is True
    assert body["requires_human_review"] is False
    assert body["total_executed_amount"] == 120.0
    assert fresh_gateway.balance_for("C-4471") == 120.0


def test_response_exposes_the_full_attempt_trail(client):
    body = client.post("/review", json=payload()).json()
    assert len(body["attempts"]) == 1
    attempt = body["attempts"][0]
    assert attempt["number"] == 1
    assert attempt["next_action"] == "terminate"
    assert attempt["idempotency_key"]


# ---------------------------------------------------------------------------
# Chapter 6's central constraint, enforced at the API boundary
# ---------------------------------------------------------------------------
def test_a_refused_refund_does_not_read_as_success(client):
    """The whole point of the chapter, as a single assertion.

    The model proposed a refund. The rail refused. If ``resolved`` were true
    here, the harness would exist, run, and have its output discarded - which
    Chapter 6 argues is worse than having no harness at all.
    """
    main.gateway = ScriptedPaymentGatewayClient(
        ExecutionResult(
            status=ExecutionStatus.REJECTED,
            amount_matches_expected=True,
            state_persisted=True,
        )
    )
    body = client.post("/review", json=payload()).json()

    assert body["decision"]["action"] == "refund"   # the proposal stands
    assert body["resolved"] is False                # the outcome does not
    assert body["requires_human_review"] is True
    assert body["terminal_reason"] == "escalated_by_gateway"


def test_partial_settlement_is_corrected_before_the_response_is_written(client):
    main.gateway = PartialAmountPaymentGatewayClient(cap=90.0)

    body = client.post("/review", json=payload()).json()

    assert body["resolved"] is True
    assert [a["next_action"] for a in body["attempts"]] == ["correct", "terminate"]
    assert body["total_executed_amount"] == 120.0


# ---------------------------------------------------------------------------
# Non-refund decisions
# ---------------------------------------------------------------------------
def test_escalation_does_not_touch_the_payment_rail(client, fresh_gateway):
    body = client.post(
        "/review", json=payload(amount=5000.0, is_duplicate_charge=False)
    ).json()

    assert body["decision"]["rule_id"] == "ESCALATE_HIGH_VALUE"
    assert body["executed"] is False
    assert body["requires_human_review"] is True
    assert fresh_gateway.balance_for("C-4471") is None
    assert fresh_gateway.call_count == 0


def test_rejection_is_resolved_without_execution(client):
    body = client.post(
        "/review",
        json=payload(days_since_transaction=400, is_duplicate_charge=False),
    ).json()

    assert body["decision"]["action"] == "reject"
    assert body["executed"] is False
    assert body["resolved"] is True
    assert body["requires_human_review"] is False


# ---------------------------------------------------------------------------
# Input validation - the schema as a control
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        {"amount": -50.0},                  # negative refund == a payment
        {"amount": 10_000_000.0},           # above the sane ceiling
        {"case_id": "x"},                   # too short to be a real id
        {"days_since_transaction": -1},
        {"currency": "EUROS"},              # not ISO-4217 length
        {"customer_claim": ""},
    ],
)
def test_invalid_input_is_rejected_before_any_decision_is_made(client, bad):
    """422, not a decision. The schema is the first line of defence, and it
    runs before the model or the rules get a chance to be clever."""
    assert client.post("/review", json=payload(**bad)).status_code == 422


def test_unknown_fields_do_not_crash_the_endpoint(client):
    response = client.post("/review", json=payload(injected_field="ignore me"))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------
def test_correlation_id_is_generated_and_echoed(client):
    response = client.post("/review", json=payload())
    cid = response.headers["X-Correlation-ID"]
    assert cid
    assert response.json()["correlation_id"] == cid


def test_caller_supplied_correlation_id_is_preserved(client):
    """A trace that starts upstream must survive this service, or the
    distributed tracing in Chapter 12 has nothing to join on."""
    response = client.post(
        "/review", json=payload(), headers={"X-Correlation-ID": "trace-abc-123"}
    )
    assert response.headers["X-Correlation-ID"] == "trace-abc-123"
    assert response.json()["correlation_id"] == "trace-abc-123"


# ---------------------------------------------------------------------------
# Decision-layer failure
# ---------------------------------------------------------------------------
def test_decision_layer_failure_escalates_instead_of_500ing(client):
    """A model that returns garbage must produce a case a human can pick up,
    not a stack trace and a lost dispute."""

    class BrokenEngine:
        name = "broken"

        def decide(self, case):
            from app.decision.engine import DecisionError

            raise DecisionError("model returned an invented rule")

    original = main.decision_engine
    main.decision_engine = BrokenEngine()
    try:
        response = client.post("/review", json=payload())
        body = response.json()

        assert response.status_code == 200
        assert body["executed"] is False
        assert body["resolved"] is False
        assert body["requires_human_review"] is True
        assert body["terminal_reason"] == "decision_layer_failure"
    finally:
        main.decision_engine = original
