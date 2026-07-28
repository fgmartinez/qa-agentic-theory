# Wiring this into `portfolio-risk-evaluator`

*Part of [Chapter 6](./README.md).*

This chapter's service is standalone and complete. Dropping it into the trunk project is a **schema adaptation problem**, not a rewrite — this file is the exact procedure.

## What is verified, and what is not

Being precise about this matters more than sounding finished:

| Claim | Status |
|---|---|
| The harness loop, resolver, corrector, and idempotency behave as documented | **Verified** — 112 tests, run, output in the chapter |
| The service boots and serves `/health`, `/rules`, `/review` | **Verified** — live `uvicorn` run, transcript in the chapter |
| The field names below match `portfolio-risk-evaluator`'s real schemas | **Not verified.** That repo's `main.py` / `schemas.py` were not available to read. |

The schemas in `app/schemas.py` are **this notebook's own**, designed to be structurally right and renamed on contact with reality. Do not assume `TransactionCase.days_since_transaction` exists in the trunk project because it exists here.

## The adapter pattern

Do **not** edit `app/harness/` to match the trunk project's names. The harness deliberately knows nothing about `TransactionCase`, `ReviewDecision`, or `RuleId` — that independence is why it is testable without an LLM, and it is worth preserving. Instead, write one adapter module in the trunk project:

```python
# portfolio_risk_evaluator/harness_adapter.py
from app.harness import ReviewHarness, InMemoryPaymentGatewayClient
from .schemas import ReviewDecision  # the trunk project's REAL schema

def execute(decision: ReviewDecision, harness: ReviewHarness):
    """Translate the trunk project's decision into a harness call.

    The ONLY file that needs to change when the trunk project's field names
    differ from Chapter 6's. Everything under app/harness/ stays untouched.
    """
    return harness.run(
        case_id=decision.<REAL_CASE_ID_FIELD>,
        amount=decision.<REAL_AMOUNT_FIELD>,
    )
```

Three things to reconcile when the real schemas are in hand:

1. **The case identifier.** Chapter 6 calls it `case_id`. If the trunk project uses `transaction_id` or `dispute_ref`, change it in the adapter only.
2. **The amount.** Chapter 6 assumes the decision carries the amount to refund. If the trunk project's `ReviewDecision` carries only an action and the amount lives on the case, pass the case's amount instead.
3. **The rule enum.** Chapter 6's `RuleId` is illustrative. The trunk project's is authoritative — keep the trunk project's and delete this one, or the grounding check validates against the wrong catalogue, which is worse than not checking at all.

## The change that is required regardless of field names

**`decision` alone cannot remain the whole response.**

Before the harness, `/review` returning a `ReviewDecision` was the end of the story. After, it is only the end of the story when `outcome.terminal_reason is TerminalReason.RESOLVED`. A `RETRY`, `CORRECT`, or `ESCALATE` has to change what the endpoint returns.

If the harness runs and its output is discarded, the result is **worse than not having a harness**: the system looks tested and defensible while the recovery path has never once influenced a response. `tests/test_api.py::test_a_refused_refund_does_not_read_as_success` is the regression test for exactly this, and it should be ported alongside the code.

## Suggested order

1. Copy `app/harness/` in wholesale. It has no trunk-project dependencies.
2. Copy `tests/test_harness_*.py` and `tests/test_types_and_corrector.py`. They should pass unchanged. **If they don't, stop** — something was modified during the copy.
3. Write `harness_adapter.py` against the real schemas.
4. Change `/review` to call it, and widen the response model to carry `terminal_reason` / `requires_human_review`.
5. Port `tests/test_api.py`'s assertions about refused refunds, adjusted to the real response shape.

Steps 1–2 are mechanical and independently verifiable. Only step 3 onward needs the real code in front of you.
