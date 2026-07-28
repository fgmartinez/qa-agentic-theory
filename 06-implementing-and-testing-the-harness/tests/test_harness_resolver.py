import pytest

from app.harness.resolver import resolve_next_action
from app.harness.types import ExecutionResult, ExecutionStatus, NextAction


@pytest.mark.parametrize(
    "status,amount_matches,persisted,expected",
    [
        # Transient failure -> retry, not silent success.
        (ExecutionStatus.TIMEOUT, False, False, NextAction.RETRY),
        # Gateway actively refused -> a human looks at it.
        (ExecutionStatus.REJECTED, True, True, NextAction.ESCALATE),
        # Executed but not what was asked -> correct upstream, don't trust it.
        (ExecutionStatus.APPROVED, False, True, NextAction.CORRECT),
        # The happy path -> done.
        (ExecutionStatus.APPROVED, True, True, NextAction.TERMINATE),
        # Unexpected / unmatched combination -> fail safe, don't assume success.
        (ExecutionStatus.PENDING, True, False, NextAction.ESCALATE),
    ],
)
def test_resolver_covers_every_branch(status, amount_matches, persisted, expected):
    result = ExecutionResult(
        status=status,
        amount_matches_expected=amount_matches,
        state_persisted=persisted,
    )
    assert resolve_next_action(result) == expected
