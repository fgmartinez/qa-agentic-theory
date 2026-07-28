"""A deterministic, LLM-free decision engine.

Two reasons this exists, and neither is "we could not get the LLM working":

1. **It is the walking skeleton's default.** The service runs end to end,
   today, with no model, no API key, and no network. Every test in this
   chapter that is not specifically about the LLM uses this engine, which is
   why the suite runs in milliseconds and never flakes.

2. **It is the baseline the LLM has to beat.** A model-based engine that does
   not outperform these seven ``if`` statements on the golden set (Chapter 9)
   is not earning its latency, cost, or risk. Having the baseline in the repo
   turns "should this be an LLM?" from an aesthetic argument into a
   measurement.

Rule order matters: the checks run most-restrictive first, so a high-value
*and* fraud-flagged case escalates for fraud rather than being caught by the
value ceiling. Changing the order changes the behaviour, which is exactly why
``tests/test_decision_rules.py`` pins the precedence explicitly.
"""

from __future__ import annotations

from ..schemas import ReviewAction, ReviewDecision, RuleId, TransactionCase

#: Above this, a human signs off regardless of how clean the case looks.
HIGH_VALUE_THRESHOLD = 500.0

#: Below this, the cost of human review exceeds the amount at risk.
LOW_VALUE_THRESHOLD = 25.0

#: Refund window in days.
REFUND_WINDOW_DAYS = 180

#: Prior disputes above this suggest a pattern worth a human's attention.
REPEAT_DISPUTER_THRESHOLD = 3


class RuleBasedDecisionEngine:
    """Reference implementation of the review policy."""

    name = "rule-based"

    def decide(self, case: TransactionCase) -> ReviewDecision:
        # 1. Fraud signals outrank everything. A fraud-flagged case is never
        #    auto-approved no matter how small the amount.
        if case.fraud_signals:
            return ReviewDecision(
                action=ReviewAction.ESCALATE,
                rule_id=RuleId.ESCALATE_SUSPECTED_FRAUD,
                amount=0.0,
                rationale=(
                    f"Fraud signals present: {', '.join(sorted(case.fraud_signals))}."
                ),
            )

        # 2. Outside the refund window is a hard 'no' - checked before value,
        #    because an out-of-window case should be rejected, not escalated,
        #    even when the amount is large.
        if case.days_since_transaction > REFUND_WINDOW_DAYS:
            return ReviewDecision(
                action=ReviewAction.REJECT,
                rule_id=RuleId.REJECT_OUTSIDE_WINDOW,
                amount=0.0,
                rationale=(
                    f"{case.days_since_transaction} days since transaction exceeds "
                    f"the {REFUND_WINDOW_DAYS}-day window."
                ),
            )

        # 3. A repeat disputer is a pattern, not a transaction. Escalate.
        if case.prior_disputes > REPEAT_DISPUTER_THRESHOLD:
            return ReviewDecision(
                action=ReviewAction.ESCALATE,
                rule_id=RuleId.ESCALATE_REPEAT_DISPUTER,
                amount=0.0,
                rationale=(
                    f"{case.prior_disputes} prior disputes exceeds the "
                    f"{REPEAT_DISPUTER_THRESHOLD}-dispute threshold."
                ),
            )

        # 4. High value needs a human even when everything else is clean.
        if case.amount > HIGH_VALUE_THRESHOLD:
            return ReviewDecision(
                action=ReviewAction.ESCALATE,
                rule_id=RuleId.ESCALATE_HIGH_VALUE,
                amount=0.0,
                rationale=(
                    f"{case.amount:.2f} {case.currency} exceeds the "
                    f"{HIGH_VALUE_THRESHOLD:.2f} auto-decision ceiling."
                ),
            )

        # 5. A duplicate charge is objectively verifiable - refund it.
        if case.is_duplicate_charge:
            return ReviewDecision(
                action=ReviewAction.REFUND,
                rule_id=RuleId.REFUND_DUPLICATE_CHARGE,
                amount=case.amount,
                rationale="Duplicate charge confirmed on the case record.",
            )

        # 6. Small amounts inside the window: refunding is cheaper than
        #    reviewing.
        if case.amount <= LOW_VALUE_THRESHOLD:
            return ReviewDecision(
                action=ReviewAction.REFUND,
                rule_id=RuleId.AUTO_APPROVE_LOW_VALUE,
                amount=case.amount,
                rationale=(
                    f"{case.amount:.2f} {case.currency} is at or below the "
                    f"{LOW_VALUE_THRESHOLD:.2f} auto-approval threshold."
                ),
            )

        # 7. Everything in between: a service-failure refund on the customer's
        #    claim. This is the branch most worth replacing with a model -
        #    it is the only one that depends on reading unstructured text.
        return ReviewDecision(
            action=ReviewAction.REFUND,
            rule_id=RuleId.REFUND_SERVICE_FAILURE,
            amount=case.amount,
            rationale="Within window, below ceiling, no fraud or repeat-dispute signal.",
        )
