"""The 'New decision' box of the harness diagram.

``resolve_next_action`` is a pure function: same ``ExecutionResult`` in, same
``NextAction`` out, every time. No LLM call, no I/O, no clock, no randomness.

That purity is the point, and it is worth being precise about why:

1. It can be tested **exhaustively** rather than sampled. The input space is
   4 statuses x 2 x 2 booleans = 16 combinations, and a test can walk all 16.
   You cannot say that about anything with a model in it.
2. It stays predictable **when the model's decision wasn't**. The recovery
   logic is the last line of defence; making it depend on the same component
   that just produced a questionable decision would defeat the purpose.
3. It is the piece a regulator or an incident review can actually read. Four
   branches of plain Python is an auditable control; a prompt is not.

The order of the branches matters and is not arbitrary - see the module's
tests, which pin it.
"""

from .types import ExecutionResult, ExecutionStatus, NextAction


def resolve_next_action(result: ExecutionResult) -> NextAction:
    """Map one observation to one verdict.

    Branch order is deliberate: status is checked before amount, because a
    timeout carries no trustworthy amount to compare in the first place.
    """
    if result.status == ExecutionStatus.TIMEOUT:
        # Transient failure at the gateway. Crucially, a timeout is an
        # *absence of information*, not evidence of failure - the refund may
        # well have gone through. The decision itself was never proven wrong,
        # so retry (idempotently) rather than escalate.
        return NextAction.RETRY

    if result.status == ExecutionStatus.REJECTED:
        # The gateway actively refused. Retrying a definite 'no' just produces
        # the same 'no' more expensively; a human needs to look at this.
        return NextAction.ESCALATE

    if result.status == ExecutionStatus.APPROVED and not result.amount_matches_expected:
        # Executed, but not what was asked for - partial settlement, currency
        # conversion, rounding, a capped rail. Something upstream needs
        # correcting before this can be trusted as done. Note this is NOT a
        # retry: the operation succeeded, it just succeeded differently.
        return NextAction.CORRECT

    if result.status == ExecutionStatus.APPROVED and result.state_persisted:
        return NextAction.TERMINATE

    # Everything else - PENDING, or APPROVED without persisted state - is a
    # combination this resolver does not claim to understand. Fail safe by
    # escalating rather than silently assuming success.
    #
    # This line is load-bearing. 'Assume success on an unrecognised signal' is
    # the single failure mode this entire notebook is about, and the resolver
    # refuses to produce it even by omission.
    return NextAction.ESCALATE
