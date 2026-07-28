"""Runnable tour of the harness - no server, no model, no network.

    python demo.py

Prints one scenario per behaviour the harness has, with the full attempt trail
for each. Reading the output next to Chapter 6 is the fastest way to see the
loop actually loop, rather than taking the chapter's word for it.
"""

from app.decision.rules import RuleBasedDecisionEngine
from app.harness import (
    FlakyPaymentGatewayClient,
    InMemoryPaymentGatewayClient,
    PartialAmountPaymentGatewayClient,
    ReviewHarness,
    ScriptedPaymentGatewayClient,
)
from app.harness.types import ExecutionResult, ExecutionStatus
from app.schemas import TransactionCase

LINE = "=" * 72


def show(title: str, gateway, amount: float = 120.0, case_id: str = "C-4471") -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")
    outcome = ReviewHarness(gateway=gateway, max_attempts=3).run(
        case_id=case_id, amount=amount
    )
    for attempt in outcome.attempts:
        print(
            f"  attempt {attempt.number}: "
            f"requested {attempt.command.amount:>7.2f} "
            f"key={attempt.command.idempotency_key} "
            f"-> {attempt.execution.status.value:<8} "
            f"executed={attempt.execution.executed_amount} "
            f"replayed={attempt.execution.replayed} "
            f"=> {attempt.next_action.value.upper()}"
        )
    print(f"  TERMINAL: {outcome.terminal_reason.value}")
    print(f"  resolved={outcome.succeeded}  needs_human={outcome.needs_human}")
    if hasattr(gateway, "balance_for"):
        print(f"  ledger[{case_id}] = {gateway.balance_for(case_id)}")


def main() -> None:
    show("1. HAPPY PATH - one attempt, terminate", InMemoryPaymentGatewayClient())

    show(
        "2. RETRY - transient timeout, same idempotency key, recovers itself",
        FlakyPaymentGatewayClient(fail_times=2),
        case_id="C-9002",
    )

    show(
        "3. BUDGET EXHAUSTED - never got an answer, escalates (does not assume success)",
        ScriptedPaymentGatewayClient(
            ExecutionResult(ExecutionStatus.TIMEOUT, False, False)
        ),
        case_id="C-3003",
    )

    show(
        "4. ESCALATE - the rail refused; retrying a definite 'no' is pointless",
        ScriptedPaymentGatewayClient(
            ExecutionResult(ExecutionStatus.REJECTED, True, True)
        ),
        case_id="C-1187",
    )

    show(
        "5. CORRECT - rail settles 90 of 120, harness issues the missing 30",
        PartialAmountPaymentGatewayClient(cap=90.0),
        case_id="C-6006",
    )

    print(f"\n{LINE}\n6. DECISION LAYER - same cases, no LLM required\n{LINE}")
    engine = RuleBasedDecisionEngine()
    cases = [
        ("duplicate charge, 120", dict(amount=120.0, is_duplicate_charge=True)),
        ("tiny amount, 8", dict(amount=8.0)),
        ("high value, 5000", dict(amount=5000.0)),
        ("stale, 400 days", dict(amount=120.0, days_since_transaction=400)),
        ("fraud flagged", dict(amount=50.0, fraud_signals=["velocity"])),
    ]
    for label, overrides in cases:
        case = TransactionCase(
            case_id="C-0001",
            merchant="Example Store",
            days_since_transaction=overrides.pop("days_since_transaction", 10),
            customer_claim="Item never arrived.",
            **overrides,
        )
        decision = engine.decide(case)
        print(
            f"  {label:<24} -> {decision.action.value:<9} {decision.rule_id.value}"
        )


if __name__ == "__main__":
    main()
