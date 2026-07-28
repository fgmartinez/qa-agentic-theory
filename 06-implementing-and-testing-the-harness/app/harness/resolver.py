"""The 'New decision' box of the harness diagram.

resolve_next_action is a pure function: same ExecutionResult in, same
NextAction out, every time. No LLM call, no I/O. That purity is the
point - it means this step can be unit tested exhaustively and stays
predictable even when the model's original decision wasn't.
"""
from .types import ExecutionResult, ExecutionStatus, NextAction


def resolve_next_action(result: ExecutionResult) -> NextAction:
    if result.status == ExecutionStatus.TIMEOUT:
        # Transient failure at the gateway - the decision itself was
        # never proven wrong, so retry rather than escalate.
        return NextAction.RETRY

    if result.status == ExecutionStatus.REJECTED:
        # The gateway actively refused the operation - a human needs
        # to look at this, the harness should not retry blindly.
        return NextAction.ESCALATE

    if result.status == ExecutionStatus.APPROVED and not result.amount_matches_expected:
        # Executed, but not what was asked for - something upstream
        # (parameter construction, currency conversion, rounding)
        # needs correcting before this can be trusted as done.
        return NextAction.CORRECT

    if result.status == ExecutionStatus.APPROVED and result.state_persisted:
        return NextAction.TERMINATE

    # Any other combination (e.g. PENDING, or APPROVED without a
    # persisted state) is unexpected - fail safe by escalating rather
    # than silently assuming success.
    return NextAction.ESCALATE
