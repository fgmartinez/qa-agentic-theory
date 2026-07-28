"""The three tools from ``fintech-support-ai-evaluator``, defined properly.

These are the running example for Chapter 7's schema-design rules. Read the
docstrings as what they are: **prompt text**. They are the only thing the
model has to decide *when* each tool applies, and the boundary between
``get_payment_policy`` and ``check_invoice_status`` exists only because these
descriptions draw it.
"""

from __future__ import annotations

from enum import Enum

from .registry import ToolRegistry

registry = ToolRegistry()


class PolicyTopic(str, Enum):
    """Closed set of policy topics.

    An open ``str`` here would invite "refunds", "refund policy", "Refunds",
    and "how do refunds work" - four spellings of one topic, three of which
    miss. The enum makes the acceptable values part of the schema the model
    is shown.
    """

    REFUNDS = "refunds"
    CHARGEBACKS = "chargebacks"
    FEES = "fees"
    PAYOUT_SCHEDULE = "payout_schedule"


@registry.register
def get_payment_policy(topic: PolicyTopic) -> str:
    """Look up the company's WRITTEN POLICY on a payment topic.

    Use for general questions about how something works in principle - "how
    long do refunds take?", "what fee applies to chargebacks?".

    Do NOT use for questions about a specific invoice, payment, or customer.
    Use check_invoice_status for those.
    """
    policies = {
        PolicyTopic.REFUNDS: "Refunds are processed within 5 business days.",
        PolicyTopic.CHARGEBACKS: "Chargebacks incur a 15.00 EUR fee.",
        PolicyTopic.FEES: "Standard processing fee is 1.4% + 0.25 EUR.",
        PolicyTopic.PAYOUT_SCHEDULE: "Payouts settle every Tuesday.",
    }
    return policies[PolicyTopic(topic)]


@registry.register
def check_invoice_status(invoice_id: str) -> dict:
    """Look up the CURRENT STATUS of one specific invoice by its id.

    Use when the question is about a particular invoice - "was INV-1002
    paid?", "why is my invoice still pending?".

    Do NOT use for general policy questions. Use get_payment_policy instead.
    Requires a known invoice id; do not guess one.
    """
    invoices = {
        "INV-1001": {"status": "paid", "amount": 240.0, "currency": "EUR"},
        "INV-1002": {"status": "pending", "amount": 89.5, "currency": "EUR"},
    }
    if invoice_id not in invoices:
        raise KeyError(invoice_id)
    return {"invoice_id": invoice_id, **invoices[invoice_id]}


@registry.register
def escalate_to_human(reason: str, urgency: str = "normal") -> str:
    """Hand the conversation to a human support agent.

    Use when the customer is disputing a charge, asking for an exception to
    policy, expressing significant dissatisfaction, or asking something the
    other tools cannot answer.

    Prefer escalating over guessing.
    """
    return f"Escalated ({urgency}): {reason}"
