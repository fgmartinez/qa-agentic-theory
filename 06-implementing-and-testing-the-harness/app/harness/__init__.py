"""The harness: the layer between a proposed decision and the real world.

Public surface - import from here, not from the submodules::

    from app.harness import ReviewHarness, InMemoryPaymentGatewayClient

Chapter 5 defines what this package is for; Chapter 6 builds it.
"""

from .corrector import Corrector, NoOpCorrector, ShortfallCorrector
from .gateway import (
    FlakyPaymentGatewayClient,
    InMemoryPaymentGatewayClient,
    PartialAmountPaymentGatewayClient,
    PaymentGatewayClient,
    ScriptedPaymentGatewayClient,
    SequencedPaymentGatewayClient,
)
from .resolver import resolve_next_action
from .service import ReviewHarness
from .types import (
    Attempt,
    ExecutionResult,
    ExecutionStatus,
    HarnessOutcome,
    NextAction,
    RefundCommand,
    TerminalReason,
)

__all__ = [
    "Attempt",
    "Corrector",
    "ExecutionResult",
    "ExecutionStatus",
    "FlakyPaymentGatewayClient",
    "HarnessOutcome",
    "InMemoryPaymentGatewayClient",
    "NextAction",
    "NoOpCorrector",
    "PartialAmountPaymentGatewayClient",
    "PaymentGatewayClient",
    "RefundCommand",
    "ReviewHarness",
    "ScriptedPaymentGatewayClient",
    "SequencedPaymentGatewayClient",
    "ShortfallCorrector",
    "TerminalReason",
    "resolve_next_action",
]
