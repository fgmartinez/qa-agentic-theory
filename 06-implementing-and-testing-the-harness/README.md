# Chapter 6 — Implementing and Testing the Harness

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 5 — The Harness Pattern](../05-the-harness-pattern/README.md). Next: [Chapter 7 — Evaluation Metrics](../07-evaluation-metrics/README.md).*

The full `app/harness/` module, verified passing — plus what it still needs before it can be wired into the trunk project's real `/review` endpoint.

## Module layout

Four files, each doing exactly one job from the harness diagram in Chapter 5. No file imports anything from the LLM/decision layer — the harness only needs a `case_id` and an `amount`, on purpose (more on why in [What's still open](#whats-still-open)).

```
06-implementing-and-testing-the-harness/
├── app/harness/
│   ├── types.py     # ExecutionStatus, ExecutionResult, NextAction
│   ├── gateway.py   # PaymentGatewayClient Protocol + fake + scripted stub
│   ├── resolver.py  # resolve_next_action() — pure function
│   └── service.py   # ReviewHarness — orchestrates gateway + resolver
└── tests/
    ├── test_harness_resolver.py
    └── test_harness_service.py
```

Run it yourself:

```bash
cd 06-implementing-and-testing-the-harness
python3 -m pytest tests/ -v
```

## `types.py` — the vocabulary

```python
class ExecutionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    TIMEOUT = "timeout"

@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    amount_matches_expected: bool
    state_persisted: bool

class NextAction(str, Enum):
    TERMINATE = "terminate"
    CORRECT = "correct"
    RETRY = "retry"
    ESCALATE = "escalate"
```

`ExecutionResult` is frozen on purpose — it's evidence, produced once by the gateway call, and nothing downstream should be able to mutate it before the resolver sees it. That immutability is a small thing, but it's the difference between "the observation is a fact" and "the observation is a value someone could quietly adjust."

## `gateway.py` — the only door to the outside world

```python
class PaymentGatewayClient(Protocol):
    def issue_refund(self, case_id: str, amount: float) -> ExecutionResult: ...

class InMemoryPaymentGatewayClient:
    """Walking-skeleton fake: real interface, in-memory backend, always succeeds."""
    def __init__(self) -> None:
        self._ledger: dict[str, float] = {}

    def issue_refund(self, case_id: str, amount: float) -> ExecutionResult:
        self._ledger[case_id] = amount
        return ExecutionResult(ExecutionStatus.APPROVED, True, True)

class ScriptedPaymentGatewayClient:
    """Test double for the non-happy paths — timeout, rejection, mismatch."""
    def __init__(self, scripted_result: ExecutionResult) -> None:
        self._scripted_result = scripted_result

    def issue_refund(self, case_id: str, amount: float) -> ExecutionResult:
        return self._scripted_result
```

> **QA bridge — fake vs. stub, and why the module has both.** `InMemoryPaymentGatewayClient` and `ScriptedPaymentGatewayClient` look similar but exist for different reasons — the same distinction as `cy.intercept()` returning a canned fixture (a **stub**, scripted per test) versus a lightweight in-process replacement of a real dependency (a **fake**, general-purpose). The fake is what `/review` actually runs against today. The stub only exists inside test files, to force the gateway into a specific state (`TIMEOUT`, `REJECTED`) that would be slow or impossible to trigger reliably against the fake.

## `resolver.py` — the deterministic core

```python
def resolve_next_action(result: ExecutionResult) -> NextAction:
    if result.status == ExecutionStatus.TIMEOUT:
        return NextAction.RETRY          # transient — decision wasn't proven wrong
    if result.status == ExecutionStatus.REJECTED:
        return NextAction.ESCALATE       # gateway refused — needs a human
    if result.status == ExecutionStatus.APPROVED and not result.amount_matches_expected:
        return NextAction.CORRECT        # executed, but not what was asked
    if result.status == ExecutionStatus.APPROVED and result.state_persisted:
        return NextAction.TERMINATE      # the happy path
    return NextAction.ESCALATE           # unmatched combination — fail safe, not silent
```

Four `if` statements, no branch left unhandled, no LLM call anywhere in this file. The last line matters as much as any of the others: an unrecognized combination of signals escalates rather than defaulting to "assume it worked." Silent success is exactly the failure mode this whole notebook is about — the resolver refuses to produce it even by omission.

## `service.py` — tying it together

```python
@dataclass(frozen=True)
class HarnessOutcome:
    execution: ExecutionResult
    next_action: NextAction

class ReviewHarness:
    def __init__(self, gateway: PaymentGatewayClient) -> None:
        self._gateway = gateway

    def execute_refund_decision(self, case_id: str, amount: float) -> HarnessOutcome:
        execution = self._gateway.issue_refund(case_id=case_id, amount=amount)
        next_action = resolve_next_action(execution)
        return HarnessOutcome(execution=execution, next_action=next_action)
```

`ReviewHarness` is the only class in the module that holds a `PaymentGatewayClient`. Everything else — the endpoint, the LLM decision logic — talks to `ReviewHarness`, never to the gateway. One object with production access, easy to find in a code review, easy to point to in an interview when asked how an LLM is kept from touching a real payment system directly.

## Tests — run and verified

```python
@pytest.mark.parametrize("status,amount_matches,persisted,expected", [
    (ExecutionStatus.TIMEOUT,  False, False, NextAction.RETRY),
    (ExecutionStatus.REJECTED, True,  True,  NextAction.ESCALATE),
    (ExecutionStatus.APPROVED, False, True,  NextAction.CORRECT),
    (ExecutionStatus.APPROVED, True,  True,  NextAction.TERMINATE),
    (ExecutionStatus.PENDING,  True,  False, NextAction.ESCALATE),
])
def test_resolver_covers_every_branch(status, amount_matches, persisted, expected):
    result = ExecutionResult(status, amount_matches, persisted)
    assert resolve_next_action(result) == expected
```

Plus two service-level tests: one against the fake (happy path terminates, and the fake's ledger actually reflects the amount), one against the scripted stub (a timeout produces `RETRY`, not a silently-approved decision).

```
$ python3 -m pytest tests/ -v
tests/test_harness_resolver.py::test_resolver_covers_every_branch[timeout-False-False-retry] PASSED
tests/test_harness_resolver.py::test_resolver_covers_every_branch[rejected-True-True-escalate] PASSED
tests/test_harness_resolver.py::test_resolver_covers_every_branch[approved-False-True-correct] PASSED
tests/test_harness_resolver.py::test_resolver_covers_every_branch[approved-True-True-terminate] PASSED
tests/test_harness_resolver.py::test_resolver_covers_every_branch[pending-True-False-escalate] PASSED
tests/test_harness_service.py::test_happy_path_terminates_and_persists_to_the_fake_ledger PASSED
tests/test_harness_service.py::test_gateway_timeout_triggers_retry_not_silent_success PASSED
tests/test_harness_service.py::test_gateway_rejection_escalates_to_a_human PASSED

======================== 8 passed in 0.02s ========================
```

This is a real pytest run against the code in this folder, not a transcription — worth saying explicitly since it's easy to write plausible-looking test output by hand. Zero of these tests touch an LLM; all eight are deterministic and fast, which is exactly what a resolver layer should look like.

## What's still open

This module deliberately does not import `TransactionCase`, `ReviewDecision`, or `RuleId` from the trunk project. Wiring `ReviewHarness` into the actual `/review` endpoint needs the trunk project's real field names — pending until `main.py` / `schemas.py` are available to wire against exactly, rather than guessing plausible-looking names that quietly don't match.

The one thing that has to change regardless of exact field names: **`decision` alone can't be the whole response once a harness exists.** Before this change, `/review` returning the LLM's `ReviewDecision` was the end of the story. After, it's only the end of the story if `outcome.next_action == TERMINATE`. A `RETRY`, `CORRECT`, or `ESCALATE` has to change what the endpoint actually returns — otherwise the harness exists, runs, and its output gets discarded, which is worse than not having it, because it will look tested and defensible without being either.

## Decision log

**ADR-002 — Introduce an explicit Harness layer between decision and execution**

| Field | Detail |
|---|---|
| Decision | Added `app/harness/`: types, a `PaymentGatewayClient` Protocol + fake + scripted stub, and a pure `resolve_next_action()` state machine, orchestrated by `ReviewHarness`. |
| Consequence | `/review` must orchestrate: LLM decision → harness execution → resolver, and its response must reflect `next_action`, not just the original decision. |
| Status | Implemented and unit-tested here (8/8 passing). Endpoint wiring into `portfolio-risk-evaluator` pending the real `TransactionCase`/`ReviewDecision` schema. |

## Next

Working code with pytest coverage answers "does the resolver behave correctly" — a narrower question than "is the *agent's decision itself* good." [Chapter 7 — Evaluation Metrics: DeepEval & RAGAS](../07-evaluation-metrics/README.md) covers that second, harder question.
