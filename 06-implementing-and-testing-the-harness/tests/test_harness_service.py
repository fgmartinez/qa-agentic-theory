from app.harness.gateway import InMemoryPaymentGatewayClient, ScriptedPaymentGatewayClient
from app.harness.service import ReviewHarness
from app.harness.types import ExecutionResult, ExecutionStatus, NextAction


def test_happy_path_terminates_and_persists_to_the_fake_ledger():
    gateway = InMemoryPaymentGatewayClient()
    harness = ReviewHarness(gateway=gateway)

    outcome = harness.execute_refund_decision(case_id="C-4471", amount=120.0)

    assert outcome.next_action == NextAction.TERMINATE
    assert outcome.execution.status == ExecutionStatus.APPROVED
    assert gateway.balance_for("C-4471") == 120.0


def test_gateway_timeout_triggers_retry_not_silent_success():
    scripted_timeout = ExecutionResult(
        status=ExecutionStatus.TIMEOUT,
        amount_matches_expected=False,
        state_persisted=False,
    )
    harness = ReviewHarness(gateway=ScriptedPaymentGatewayClient(scripted_timeout))

    outcome = harness.execute_refund_decision(case_id="C-9002", amount=50.0)

    assert outcome.next_action == NextAction.RETRY


def test_gateway_rejection_escalates_to_a_human():
    scripted_rejection = ExecutionResult(
        status=ExecutionStatus.REJECTED,
        amount_matches_expected=True,
        state_persisted=True,
    )
    harness = ReviewHarness(gateway=ScriptedPaymentGatewayClient(scripted_rejection))

    outcome = harness.execute_refund_decision(case_id="C-1187", amount=75.0)

    assert outcome.next_action == NextAction.ESCALATE
