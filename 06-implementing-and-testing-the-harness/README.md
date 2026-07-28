# Chapter 6 — Implementing and Testing the Harness

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 5 — The Harness Pattern](../05-the-harness-pattern/README.md). Next: [Chapter 7 — Tool Calling and Function Schemas](../07-tool-calling-and-function-schemas/README.md).*

Chapter 5 argued for the harness. This chapter builds it — as a real backend service, stage by stage, with the loop closed and every failure path executed by a test.

**By the end of this chapter you should be able to build this service from an empty folder without looking at the solution.** That is the bar. Reading it and nodding is not the same skill as producing it under interview conditions, and the [exercises](#exercises) are how you find out which one you have.

---

## Contents

- [What you are building](#what-you-are-building)
- [The gap this chapter closes](#the-gap-this-chapter-closes)
- [Stage 0 — Run it first](#stage-0--run-it-first)
- [Stage 1 — The vocabulary (`types.py`)](#stage-1--the-vocabulary-typespy)
- [Stage 2 — The boundary (`gateway.py`)](#stage-2--the-boundary-gatewaypy)
- [Stage 3 — The deterministic core (`resolver.py`)](#stage-3--the-deterministic-core-resolverpy)
- [Stage 4 — Correction (`corrector.py`)](#stage-4--correction-correctorpy)
- [Stage 5 — The loop (`service.py`)](#stage-5--the-loop-servicepy)
- [Stage 6 — The decision layer](#stage-6--the-decision-layer)
- [Stage 7 — The API](#stage-7--the-api)
- [Stage 8 — Observability](#stage-8--observability)
- [The test suite, and why it is shaped this way](#the-test-suite-and-why-it-is-shaped-this-way)
- [Verified output](#verified-output)
- [Failure taxonomy — the reference table](#failure-taxonomy--the-reference-table)
- [Exercises](#exercises)
- [Interview preparation](#interview-preparation)
- [What's still open](#whats-still-open)

---

## What you are building

A dispute-review service. A case arrives over HTTP; a decision layer proposes what to do with it; a harness executes that proposal against a payment rail, observes what actually happened, and corrects or escalates until it reaches a terminal state. Then it reports the truth — not the proposal.

```
POST /review
     │
     ▼
┌─────────────────┐   proposes    ┌──────────────────────────────────────┐
│ Decision layer  │──────────────▶│ Harness                              │
│ rules  or  LLM  │  ReviewDecision│  ┌────────────────────────────────┐ │
└─────────────────┘               │  │ ACT     gateway.issue_refund() │ │
        ▲                         │  │  ▼                             │ │
        │ never touches           │  │ OBSERVE ExecutionResult        │ │
        │ the gateway             │  │  ▼                             │ │
        │                         │  │ RESOLVE resolve_next_action()  │ │
        │                         │  │  ▼                             │ │
        │                         │  │ TERMINATE ─────────────▶ done  │ │
        │                         │  │ RETRY     ─── same key ──┐     │ │
        │                         │  │ CORRECT   ── new amount ─┤     │ │
        │                         │  │ ESCALATE  ─────────▶ human│    │ │
        │                         │  └──────────────────────────┴─────┘ │
        │                         └───────────────┬──────────────────────┘
        │                                         ▼
        │                              ┌────────────────────┐
        └──────────────────────────────│  Payment rail      │
                 (only via harness)    │  (fake / real)     │
                                       └────────────────────┘
```

Final module layout:

```
06-implementing-and-testing-the-harness/
├── app/
│   ├── main.py            # FastAPI: /health, /rules, /review
│   ├── config.py          # every operational lever, one place
│   ├── schemas.py         # TransactionCase, ReviewDecision, closed RuleId
│   ├── logging_setup.py   # structured JSON logs + correlation ids
│   ├── decision/
│   │   ├── engine.py      # DecisionEngine Protocol, DecisionError
│   │   ├── rules.py       # RuleBasedDecisionEngine — no LLM
│   │   └── llm.py         # LLMDecisionEngine + prompt + grounding validation
│   └── harness/
│       ├── types.py       # vocabulary + RefundCommand (idempotency key)
│       ├── gateway.py     # Protocol + 1 fake + 4 test doubles
│       ├── resolver.py    # resolve_next_action() — pure
│       ├── corrector.py   # how CORRECT actually corrects
│       └── service.py     # ReviewHarness — THE LOOP
├── tests/                 # 112 tests
├── demo.py                # runnable tour, no server needed
└── WIRING.md              # dropping this into the trunk project
```

~2,800 lines including tests. Every claim about behaviour below is backed by a test you can run.

## The gap this chapter closes

The first version of this chapter shipped four files and eight tests. It was correct as far as it went, and it had a hole big enough to invalidate the entire premise:

```python
def execute_refund_decision(self, case_id, amount):
    execution = self._gateway.issue_refund(case_id, amount)
    next_action = resolve_next_action(execution)
    return HarnessOutcome(execution, next_action)   # ...and then what?
```

The resolver could return `RETRY`. **Nothing ever retried.** It could return `CORRECT`. Nothing ever corrected. Chapter 5 defines autonomy as:

```
AUTONOMY = ACT + OBSERVE + CORRECT
```

and that code implements ACT, implements OBSERVE, and then hands CORRECT to the caller as a suggestion. A harness that can only *recommend* a retry is a harness whose recovery path has never once executed in anger — while looking tested, because the resolver's unit tests all pass.

That is a worse position than having no harness at all, and it is worth being blunt about *why*: an untested recovery path is a liability that presents as an asset. This chapter's version closes the loop.

## Stage 0 — Run it first

Before reading a line of implementation, watch it work. Understanding lands faster against observed behaviour than against prose.

```bash
cd 06-implementing-and-testing-the-harness
pip install -r requirements.txt
python demo.py
```

Abridged real output:

```
========================================================================
2. RETRY - transient timeout, same idempotency key, recovers itself
========================================================================
  attempt 1: requested  120.00 key=e93f395893d24740 -> timeout  executed=None  => RETRY
  attempt 2: requested  120.00 key=e93f395893d24740 -> timeout  executed=None  => RETRY
  attempt 3: requested  120.00 key=e93f395893d24740 -> approved executed=120.0 => TERMINATE
  TERMINAL: resolved
  ledger[C-9002] = 120.0

========================================================================
5. CORRECT - rail settles 90 of 120, harness issues the missing 30
========================================================================
  attempt 1: requested  120.00 key=298c89c4aca3ca3d -> approved executed=90.0 => CORRECT
  attempt 2: requested   30.00 key=021553a3ddb12a11 -> approved executed=30.0 => TERMINATE
  TERMINAL: resolved
  ledger[C-6006] = 120.0
```

Two things to notice now, because the rest of the chapter is largely about them:

1. In scenario 2 the **idempotency key never changes across retries**. The customer is refunded 120.00, once, despite three gateway calls.
2. In scenario 5 the key **does** change, and the second attempt is for 30.00, not 120.00. The ledger lands on exactly 120.00.

Those two behaviours are opposites, and both are correct. Getting them backwards double-refunds a customer.

## Stage 1 — The vocabulary (`types.py`)

Build the nouns first. Every other module is written in these terms, and getting the vocabulary right makes the rest close to mechanical.

```python
class ExecutionStatus(str, Enum):
    APPROVED = "approved"    # confirmed
    REJECTED = "rejected"    # a definite no
    PENDING  = "pending"     # genuinely unknown yet
    TIMEOUT  = "timeout"     # no answer — NOT the same as failure
```

> **The distinction the whole chapter turns on.** `TIMEOUT` is an *absence of information*, not evidence of failure. The refund may well have gone through. A system that treats a timeout as failure and retries naively double-refunds; a system that treats it as success loses the customer's money. It is neither, and the only safe way to act on it is idempotently.

```python
@dataclass(frozen=True)
class RefundCommand:
    case_id: str
    amount: float
    attempt: int = 1

    @property
    def idempotency_key(self) -> str:
        raw = f"{self.case_id}|{self.amount:.2f}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

Read that key derivation carefully — it encodes a policy decision:

| Included | Excluded | Consequence |
|---|---|---|
| `case_id` | | Two different disputes are two different operations. |
| `amount`, to 2dp | | Refunding a different amount is a different operation, so `CORRECT` gets a fresh key. |
| | `attempt` | **The critical omission.** Retries share a key, so the rail can dedupe them. |

Formatting to `.2f` before hashing is not cosmetic: without it, `120.0` and `120.000000001` hash differently, and a float that survived a JSON round-trip could silently become a second refund. `test_key_is_stable_across_float_representations` pins it.

`ExecutionResult` is frozen because it is **evidence**. Nothing between the gateway call and the resolver should be able to adjust an observation — that immutability is the difference between "the observation is a fact" and "the observation is a value someone could quietly tune".

`TerminalReason` deserves its own note. It exists because `NextAction.ESCALATE` is not a sufficient answer to "what happened?":

```python
class TerminalReason(str, Enum):
    RESOLVED = "resolved"
    ESCALATED_BY_GATEWAY = "escalated_by_gateway"              # the rail said no
    ESCALATED_BUDGET_EXHAUSTED = "escalated_budget_exhausted"  # we never got an answer
    ESCALATED_UNCORRECTABLE = "escalated_uncorrectable"        # a gap we won't guess at
```

An on-call engineer at 3am needs to tell those three apart instantly. They imply completely different responses: a refusal is a business problem, an exhausted budget is an infrastructure problem, an uncorrectable gap is a reconciliation problem.

## Stage 2 — The boundary (`gateway.py`)

One Protocol, and everything that touches the outside world goes through it.

```python
class PaymentGatewayClient(Protocol):
    def issue_refund(self, command: RefundCommand) -> ExecutionResult: ...
```

That is the entire production contract. `ReviewHarness` is the only class in the codebase that holds one — a single chokepoint to log, rate-limit, or roll back, and a single thing to point at when an interviewer asks how you stop a model from touching a payment rail.

### The fake implements idempotency for real

```python
def issue_refund(self, command):
    previous = self._by_key.get(command.idempotency_key)
    if previous is not None:
        return replace(previous, detail="replayed", replayed=True)  # no second effect
    ...
```

This is the most important design decision in the file, and it is easy to get wrong in a way that is invisible for months.

> **A fake must be weaker than production, never more forgiving.** A fake that ignored the idempotency key would let every retry test pass while the production adapter double-refunds. The fake would be *manufacturing green tests for broken code*. Whenever a test double is more permissive than the real dependency, the suite is measuring the double, not the system.

### Five doubles, and the vocabulary for them

| Class | Kind | Why it exists |
|---|---|---|
| `InMemoryPaymentGatewayClient` | **fake** | Working in-process replacement. The walking skeleton runs on it. |
| `ScriptedPaymentGatewayClient` | **stub** | Always answers one canned observation. |
| `SequencedPaymentGatewayClient` | **stub** | Answers a *sequence* — the only way to test a loop. |
| `FlakyPaymentGatewayClient` | **fake** | Fails `n` times then works. Realistic transient fault. |
| `PartialAmountPaymentGatewayClient` | **fake** | Caps the settled amount. `CORRECT`'s reason to exist. |

> **QA bridge.** Same distinction as `cy.intercept()` returning a fixture (a **stub**, scripted per test) versus a lightweight in-process replacement of a real dependency (a **fake**, general-purpose). The fake is what `/review` actually runs on; the stubs exist only inside test files. `SequencedPaymentGatewayClient` is the one with no Cypress analogue worth naming, and it is the one loop testing cannot do without — you cannot express "time out twice, then approve" with a double that always says the same thing.

## Stage 3 — The deterministic core (`resolver.py`)

```python
def resolve_next_action(result: ExecutionResult) -> NextAction:
    if result.status == ExecutionStatus.TIMEOUT:
        return NextAction.RETRY
    if result.status == ExecutionStatus.REJECTED:
        return NextAction.ESCALATE
    if result.status == ExecutionStatus.APPROVED and not result.amount_matches_expected:
        return NextAction.CORRECT
    if result.status == ExecutionStatus.APPROVED and result.state_persisted:
        return NextAction.TERMINATE
    return NextAction.ESCALATE
```

Four branches, one fallthrough, no I/O, no clock, no randomness, no LLM. Three properties follow from that purity, and each is worth being able to state out loud:

1. **It can be tested exhaustively, not sampled.** 4 statuses × 2 × 2 booleans = 16 inputs, and `test_no_input_combination_is_unhandled` walks all 16. You cannot make that claim about anything with a model in it.
2. **It stays predictable when the model's decision wasn't.** The recovery logic is the last line of defence; making it depend on the same component that just produced a questionable decision defeats the purpose.
3. **It is auditable by a human who does not write Python.** Four `if` statements is a control a regulator can read. A prompt is not.

### Branch order is behaviour

An approved-but-wrong-amount result *also* satisfies the `TERMINATE` branch's `state_persisted` condition. It matches two branches, and only the ordering decides which wins. Swap lines 3 and 4 and every partial refund silently becomes a success.

That is why the suite pins order explicitly and not just coverage:

```python
def test_amount_mismatch_outranks_persistence_on_an_approved_call():
    result = ExecutionResult(APPROVED, amount_matches_expected=False,
                             state_persisted=True, executed_amount=90.0)
    assert resolve_next_action(result) is NextAction.CORRECT
```

### The last line is load-bearing

```python
return NextAction.ESCALATE   # unmatched combination — fail safe, not silent
```

An unrecognised combination of signals escalates rather than defaulting to "assume it worked". Silent success on an unknown signal is the single failure mode this entire notebook is about; the resolver refuses to produce it even by omission.

`test_only_a_fully_clean_approval_can_terminate` states that as a **property** rather than a table row: across the whole input space, if the answer is `TERMINATE` then the status was `APPROVED`, the amount matched, and state persisted. Property-style tests keep holding when someone adds a fifth `ExecutionStatus` and forgets to add a row — which is exactly the omission table-driven tests cannot catch.

## Stage 4 — Correction (`corrector.py`)

The resolver can *say* "correct this". Saying it is useless unless something knows **how**. This is the module the original chapter was missing entirely.

```python
class ShortfallCorrector:
    def correct(self, command, result) -> RefundCommand | None:
        if result.executed_amount is None:
            return None                      # no evidence — refuse to guess
        shortfall = round(command.amount - result.executed_amount, 2)
        if shortfall <= 0:
            return None                      # equal, or an over-refund → human
        if shortfall < self._dust_threshold:
            return None                      # not worth an API call
        return RefundCommand(command.case_id, shortfall, command.attempt + 1)
```

The one line that matters most: the correction is for **the remainder**, not the original amount. Requested 120, settled 90 → issue 30. Re-sending 120 would over-refund by 90 — and it is a genuinely tempting bug, because "retry the operation" is the reflex and it is wrong here.

Three refusals, each a real failure mode rather than defensive noise:

| Condition | Why `None` (escalate) is right |
|---|---|
| `executed_amount is None` | No evidence to compute from. Guessing is precisely what the harness exists to prevent. |
| `shortfall <= 0` | The rail sent *more* than asked. An over-refund needs a human, not more automation. |
| `shortfall < 0.01` | Chasing a 0.004 remainder generates gateway calls forever, for less than the call costs. |

`NoOpCorrector` is the honest default for a team that has not yet decided what automatic correction means in its domain: **escalating a correctable case is a cost; silently mis-correcting one is an incident.** Start conservative, move to `ShortfallCorrector` when the domain rule is actually settled.

Separating the corrector from the resolver is deliberate. The resolver answers a *classification* question ("what kind of situation is this?"); the corrector answers an *arithmetic* one ("what should we send instead?"). Fusing them produces a function that is hard to test and easy to get subtly wrong.

## Stage 5 — The loop (`service.py`)

Everything so far has been parts. This is the machine.

```python
def run(self, case_id: str, amount: float) -> HarnessOutcome:
    command = RefundCommand(case_id=case_id, amount=amount, attempt=1)
    attempts = []

    for turn in range(1, self._max_attempts + 1):
        execution = self._gateway.issue_refund(command)          # ACT
        next_action = resolve_next_action(execution)             # OBSERVE + RESOLVE
        attempts.append(Attempt(turn, command, execution, next_action))

        if next_action is NextAction.TERMINATE:
            return self._finish(attempts, TerminalReason.RESOLVED)

        if next_action is NextAction.ESCALATE:
            return self._finish(attempts, TerminalReason.ESCALATED_BY_GATEWAY)

        if next_action is NextAction.RETRY:
            command = command.next_attempt()                     # SAME key
            if turn < self._max_attempts:
                self._backoff(turn)
            continue

        if next_action is NextAction.CORRECT:
            corrected = self._corrector.correct(command, execution)
            if corrected is None:
                return self._finish(attempts, TerminalReason.ESCALATED_UNCORRECTABLE)
            command = corrected                                  # NEW key
            continue

    return self._finish(attempts, TerminalReason.ESCALATED_BUDGET_EXHAUSTED)
```

### The attempt budget is not optional

An agent loop without a budget is an unbounded spend of money and time against a production system. `max_attempts` is a constructor argument with a default of 3 and a `ValueError` below 1.

Note the exit when it runs out: `ESCALATED_BUDGET_EXHAUSTED`, **not** a silent give-up and not an exception. Every path out of `run()` is an explicit terminal state. There is no path that returns "probably fine".

### The bug this loop had, and the test that caught it

The first version backed off after *every* retry, including the last one — sleeping before a retry that would never happen. Pure latency, no benefit.

```python
def test_backoff_delays_grow_and_are_not_applied_after_the_final_attempt():
    ...
    assert delays == [0.5, 1.0]      # two sleeps for three attempts
```

That test failed on the first run (`assert [0.5, 1.0, 1.5] == [0.5, 1.0]`), which is why the guard `if turn < self._max_attempts` exists. Worth stating plainly because it is the honest version of how this code came to be: the test was written from the *intent* ("you wait between tries, not after the last one"), the implementation disagreed, and the test won.

Injecting `sleeper` is what makes that testable at all — the suite passes `delays.append` and asserts on the schedule without waiting a second and a half.

### Retry vs. correct, side by side

This is the single most interview-worthy detail in the chapter:

| | RETRY | CORRECT |
|---|---|---|
| Triggered by | `TIMEOUT` — no answer | `APPROVED` + wrong amount |
| Did the operation happen? | **Unknown** | Yes, just not as asked |
| Idempotency key | **Same** — dedupe is the point | **Different** — it is a new operation |
| Amount sent | Identical | The shortfall only |
| If you got it backwards | Double refund | Shortfall never paid |

Two tests pin the two halves, and they are deliberately mirror images:

```python
def test_retry_reuses_the_same_idempotency_key():
    assert len({c.idempotency_key for c in gateway.commands}) == 1

def test_correction_changes_the_idempotency_key():
    assert len({a.command.idempotency_key for a in outcome.attempts}) == 2
```

## Stage 6 — The decision layer

The harness knows nothing about *why* a refund was proposed. The decision layer is a Protocol, so nothing downstream learns whether a decision came from an LLM or an `if` statement:

```python
class DecisionEngine(Protocol):
    name: str
    def decide(self, case: TransactionCase) -> ReviewDecision: ...
```

### The rule engine is a baseline, not a placeholder

`RuleBasedDecisionEngine` is seven ordered `if` statements. It exists for two reasons, and "we couldn't get the LLM working" is neither:

1. **The walking skeleton runs on it** — no model, no API key, no network. The whole suite is fast and never flakes.
2. **It is the bar the LLM has to clear.** A model-based engine that cannot beat seven `if` statements on the golden set (Chapter 9) is not earning its latency, cost, or risk. Keeping the baseline in the repo turns "should this be an LLM?" from an aesthetic argument into a measurement.

Rule *order* is behaviour here too — fraud outranks a small amount, so a €5 fraud-flagged case never auto-approves. `test_rule_precedence_when_several_conditions_match` pins each pairing.

### The closed enum is the hallucination defence

```python
class RuleId(str, Enum):
    AUTO_APPROVE_LOW_VALUE = "AUTO_APPROVE_LOW_VALUE"
    REFUND_DUPLICATE_CHARGE = "REFUND_DUPLICATE_CHARGE"
    ...
```

If the decision layer could return free-text justification, a model would happily invent an authoritative-sounding policy that does not exist, and nothing downstream could tell. Constraining the citation to an enum converts hallucination from a subjective judgement ("is this rationale reasonable?") into a **membership test** ("is this string in the enum?") — and a membership test can fail a CI build.

```python
def test_hallucinated_rule_id_is_rejected():
    hallucinated = '{"action":"refund","rule_id":"REFUND_GOODWILL_GESTURE",...}'
    with pytest.raises(DecisionError, match="outside the closed set"):
        parse_decision(hallucinated)
```

`REFUND_GOODWILL_GESTURE` is exactly the kind of plausible, helpful, entirely invented policy a model produces. Near-misses are tested too (`refund_duplicate_charge`, `REFUND-DUPLICATE-CHARGE`, truncations) because they are more dangerous than obvious inventions — a lenient, normalising parser is tempting to write and quietly destroys the guarantee.

### Most of `llm.py` is not the model call

```
case → prompt → model → raw text → JSON → validated ReviewDecision
                  ↑        ↑         ↑
       the only part    fenced-block   closed-enum
       people think    tolerance      grounding
       about
```

**Model output is untrusted input.** It deserves the same suspicion as a request body from the public internet. Every arrow can fail, and every failure raises `DecisionError` rather than returning a plausible default:

> A parser that returned `ESCALATE` on malformed output would be indistinguishable downstream from a model that genuinely decided to escalate. Monitoring would show a healthy service quietly escalating everything.

One subtle rule worth copying: **tolerate formatting, refuse incoherence.** Fenced blocks, leading prose, and trailing "let me know if you need anything else!" are cosmetic and tolerated — 500ing on those makes a brittle service. But an `escalate` carrying `amount: 900` is *incoherent*, and normalising it to 0 would hide a model that has misunderstood its own output format. That one raises.

Every one of these tests runs with a four-line `FakeLLMClient`. **Parsing and validation around a model call is ordinary deterministic code and deserves ordinary deterministic tests.** Save Chapter 8's statistical machinery for the question these genuinely cannot answer: *was the decision good?*

## Stage 7 — The API

`main.py` is deliberately thin: wire components, translate HTTP ↔ domain, own exactly one piece of policy.

```python
try:
    decision = decision_engine.decide(case)
except DecisionError as exc:
    return escalate_to_human(...)   # ← the one policy this module owns
```

A decision layer that failed produced *no decision*. The safe response is a human — not a guess, and not a 500 that loses the dispute in an error log.

### The constraint the whole chapter exists to enforce

```python
def test_a_refused_refund_does_not_read_as_success(client):
    main.gateway = ScriptedPaymentGatewayClient(REJECTED)
    body = client.post("/review", json=payload()).json()

    assert body["decision"]["action"] == "refund"   # the proposal stands
    assert body["resolved"] is False                # the outcome does not
    assert body["requires_human_review"] is True
```

**`decision` alone cannot be the whole response once a harness exists.** Before the harness, returning the `ReviewDecision` was the end of the story. After, it is only the end of the story when the loop resolved. If a `RETRY`, `CORRECT`, or `ESCALATE` does not change what the endpoint returns, the harness runs and its output is discarded — worse than not having it, because it looks tested and defensible while never influencing a single response.

Note also that escalations and rejections **never touch the rail**:

```python
def test_escalation_does_not_touch_the_payment_rail(client, fresh_gateway):
    ...
    assert fresh_gateway.call_count == 0
```

Running the harness with `amount=0` and treating the no-op as meaningful would be the lazy version. Saying "no execution required" explicitly is the honest one.

### The schema is the first control

Validation runs *before* the model or the rules get a chance to be clever:

```python
amount: float = Field(..., ge=0, le=1_000_000)
```

A negative refund is a payment. A model that talks itself into `amount=-500` is stopped by Pydantic long before it reaches a payment rail — 422, no decision made. That is a cheaper and more reliable control than any prompt instruction.

## Stage 8 — Observability

Chapter 12 argues structured logging is the layer to build **first**, because tracing, metrics, and alerting all derive from it and none can be retrofitted onto unparseable prose. Rather than promise that, this chapter does it.

One JSON object per line, correlation id on every line, anything passed via `extra=` merged in:

```json
{"ts":"2026-07-28T11:47:32","level":"INFO","logger":"api","event":"decision.made","correlation_id":"f3153b428ef6","case_id":"C-4471","action":"refund","rule_id":"REFUND_DUPLICATE_CHARGE","engine":"rule-based"}
{"ts":"2026-07-28T11:47:32","level":"INFO","logger":"harness","event":"harness.attempt","correlation_id":"f3153b428ef6","case_id":"C-4471","attempt":1,"requested_amount":120.0,"idempotency_key":"75a32b563cbb6862","status":"approved","executed_amount":120.0,"replayed":false,"next_action":"terminate"}
{"ts":"2026-07-28T11:47:32","level":"INFO","logger":"api","event":"harness.finished","correlation_id":"f3153b428ef6","case_id":"C-4471","terminal_reason":"resolved","attempts":1}
```

That is real captured output, not an illustration. Three modules, one shared `correlation_id`, and the entire life of a request reconstructable with a single grep. Without the shared id, correlating those lines in production means guessing at timestamps.

The middleware accepts an inbound `X-Correlation-ID` so a trace can span more than this service — the cheapest possible step toward Chapter 12's distributed tracing, and `test_caller_supplied_correlation_id_is_preserved` keeps it honest.

`contextvars` rather than a global, so concurrent requests cannot read each other's id.

## The test suite, and why it is shaped this way

| File | Tests | Answers |
|---|---|---|
| `test_harness_resolver.py` | 13 | Is the classification right, in **every** case? |
| `test_harness_service.py` | 13 | Does the **loop** do the right thing over a sequence? |
| `test_types_and_corrector.py` | 16 | Are the key and the arithmetic right? |
| `test_decision_rules.py` | 30 | Is the policy right, including precedence and boundaries? |
| `test_decision_llm.py` | 30 | Is model output **parsed and grounded** safely? |
| `test_api.py` | 20 | Does the wiring hold, and does the response tell the truth? |

**112 tests, zero of which call an LLM, all of which run in about a second.**

That last property is not an accident, and it is the reusable lesson: *almost everything that makes an agent safe is deterministic and can be tested deterministically.* The loop, the idempotency key, the recovery logic, the grounding check, the schema constraints, the failure policy — none of them need a model to test. What genuinely needs Chapter 8's statistical machinery is one narrow question: **was the decision itself good?** Keeping that question separate is what keeps the suite fast and the CI gate meaningful.

The pyramid, in this codebase's terms:

```
                  ┌──────────────────┐
                  │   test_api.py    │  20  integration: real routing,
                  │                  │      real validation, fake rail
              ┌───┴──────────────────┴───┐
              │  test_harness_service    │  13  the loop over sequences
              │  test_decision_llm       │  30  parsing/grounding
          ┌───┴──────────────────────────┴───┐
          │  test_harness_resolver           │  13  pure, exhaustive
          │  test_types_and_corrector        │  16  pure, arithmetic
          │  test_decision_rules             │  30  pure, policy
          └──────────────────────────────────┘
```

## Verified output

Actually run, on Python 3.12.7 / pytest 8.4.2 — not transcribed. Worth saying explicitly, since plausible-looking test output is trivial to write by hand and this repo's standard is that it isn't.

```
$ python -m pytest tests/
112 passed, 1 warning in 0.65s
```

And the service, booted for real:

```
$ python -m uvicorn app.main:app --port 8931

$ curl -s localhost:8931/health
{"status":"ok","gateway":"InMemoryPaymentGatewayClient","decision_engine":"rule-based"}

$ curl -s -X POST localhost:8931/review -H 'Content-Type: application/json' \
    -d '{"case_id":"C-4471","amount":120.0,"merchant":"Example Store",
         "days_since_transaction":10,"customer_claim":"Charged twice",
         "is_duplicate_charge":true}'
{"case_id":"C-4471","correlation_id":"f3153b428ef6",
 "decision":{"action":"refund","rule_id":"REFUND_DUPLICATE_CHARGE","amount":120.0,
             "rationale":"Duplicate charge confirmed on the case record.","confidence":1.0},
 "executed":true,"resolved":true,"terminal_reason":"resolved","final_status":"approved",
 "total_executed_amount":120.0,
 "attempts":[{"number":1,"requested_amount":120.0,"idempotency_key":"75a32b563cbb6862",
              "status":"approved","executed_amount":120.0,"replayed":false,
              "next_action":"terminate"}],
 "requires_human_review":false}

$ curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8931/review \
    -H 'Content-Type: application/json' -d '{"case_id":"C-1","amount":-5,...}'
422
```

## Failure taxonomy — the reference table

The table to be able to reproduce from memory. It is the chapter in one page.

| Observation | Verdict | Key | Why |
|---|---|---|---|
| `TIMEOUT` | `RETRY` | **same** | No answer ≠ failure. Idempotency makes the retry safe. |
| `REJECTED` | `ESCALATE` | — | A definite no. Retrying costs money and changes nothing. |
| `APPROVED`, amount mismatch | `CORRECT` | **new** | It happened, differently. Issue the shortfall only. |
| `APPROVED`, persisted, match | `TERMINATE` | — | The only success. |
| `APPROVED`, not persisted | `ESCALATE` | — | Rail says yes, our records say nothing. Reconciliation. |
| `PENDING` | `ESCALATE` | — | Genuinely unknown. Fail safe. |
| Budget exhausted | `ESCALATE` | — | `BUDGET_EXHAUSTED` ≠ `BY_GATEWAY`. Different on-call response. |
| Corrector returns `None` | `ESCALATE` | — | No evidence, over-refund, or dust. Don't guess. |
| `DecisionError` | never executes | — | No decision was produced. A human, not a guess. |
| Schema violation | 422 | — | Rejected before any decision is made. |

## Exercises

Do these before reading the solutions. The gap between "I followed that" and "I can produce that" is the entire difference between having read a chapter and knowing it.

### 1 — Trace the loop by hand (no code)

Gateway returns, in order: `TIMEOUT`, `TIMEOUT`, `APPROVED (executed 90 of 120)`. `max_attempts=4`, `ShortfallCorrector`.

Write out every attempt: number, amount requested, whether the key changed, verdict. What is the terminal reason and the final ledger balance?

<details><summary>Solution</summary>

| # | Amount | Key | Observation | Verdict |
|---|---|---|---|---|
| 1 | 120.00 | K1 | TIMEOUT | RETRY |
| 2 | 120.00 | K1 (same) | TIMEOUT | RETRY |
| 3 | 120.00 | K1 (same) | APPROVED, executed 90 | CORRECT |
| 4 | 30.00 | K2 (**new**) | APPROVED, executed 30 | TERMINATE |

Terminal reason `RESOLVED`, ledger 120.00, budget used exactly. Attempt 4 is the last one available — with `max_attempts=3` this same sequence would end `ESCALATED_BUDGET_EXHAUSTED` **after the correction was already issued**, i.e. with 90.00 refunded and 30.00 outstanding. Worth sitting with: a budget that is too small does not merely fail, it can stop halfway through a correction and leave inconsistent state. That is the argument for `ESCALATED_BUDGET_EXHAUSTED` carrying the full attempt trail rather than just a flag.
</details>

### 2 — Break idempotency deliberately

Change `idempotency_key` to include `attempt`. Run the suite. Which tests fail, and which of them is the one that would have been a production incident?

<details><summary>Solution</summary>

`test_retry_reuses_the_same_idempotency_key` and `test_next_attempt_preserves_the_key_and_increments_the_counter` fail directly. `test_idempotent_gateway_does_not_double_charge_on_replay` still passes — it calls `run()` twice fresh, so both start at attempt 1.

The incident is the first one. With the attempt in the key, `FlakyPaymentGatewayClient(fail_times=1)` refunds the customer **twice**: attempt 1 times out at the rail *after* moving money, attempt 2 carries a new key and is treated as a fresh operation. The fake's ledger would show 240.00 for a 120.00 dispute.

Note what this exercise really demonstrates: the tests that fail loudest are not the ones that matter most. Reading *which* failure is the incident is a skill worth practising.
</details>

### 3 — Add a new `ExecutionStatus`

Add `PARTIALLY_SETTLED`. Do not touch the resolver. Run the suite.

<details><summary>Solution</summary>

Everything passes — because the resolver's fallthrough sends unknown statuses to `ESCALATE`, and `test_only_a_fully_clean_approval_can_terminate` is a property over `ExecutionStatus`, so it automatically covers the new member and confirms it cannot terminate.

That is fail-safe design working as intended: an unhandled signal degrades to "ask a human", never to "assume success". Now decide deliberately whether `PARTIALLY_SETTLED` should map to `CORRECT` — and notice that the safe default bought you the time to decide instead of shipping a silent bug.
</details>

### 4 — Make the corrector wrong in the tempting way

Change `ShortfallCorrector` to re-send `command.amount` instead of the shortfall. Which test catches it, and what would the customer see?

<details><summary>Solution</summary>

`test_partial_settlement_is_corrected_by_refunding_the_shortfall` fails on the ledger assertion: 210.00 instead of 120.00 (90 settled, then a full 120 re-sent). The customer is over-refunded by 90.00.

This is the most tempting bug in the chapter because "retry the operation" is the instinct, and it is right for `RETRY` and wrong for `CORRECT`. The ledger assertion — not the verdict assertion — is what catches it. **Assert on the effect, not just on the classification.**
</details>

### 5 — Ship a hallucination past the guard

Without editing `parse_decision`, get a decision citing a rule that is not real policy to pass validation.

<details><summary>Solution</summary>

Add the invented rule to the `RuleId` enum. Validation passes, because the guard tests membership of the enum — and the enum is now wrong.

The lesson generalises well beyond this codebase: **the grounding check is only as good as the catalogue it checks against.** Chapter 10 covers the control that closes this — the enum, the prompt, and the policy document have to be kept in sync by something (a test, a generation step, a review gate), because "validated against the rule set" means nothing if the rule set can be edited casually. `test_prompt_lists_every_allowed_rule` is one half of that lock; a review policy on the enum is the other.
</details>

### 6 — Build it from scratch (the real exercise)

Empty folder. In order: `types` → `gateway` → `resolver` → `corrector` → `service` → API. Write the test first at each stage.

Rules: no looking at this chapter's code until a stage's tests pass. The loop in `service.py` is the stage that separates people who understood the chapter from people who read it.

<details><summary>Checkpoints</summary>

- `types`: does your key change when the amount changes and stay put when the attempt does?
- `gateway`: does your fake replay on a repeated key, or does it happily double-charge?
- `resolver`: exhaustive over all 16 inputs, and does your `TERMINATE` property hold?
- `corrector`: shortfall or full amount? Do you refuse when `executed_amount is None`?
- `service`: every exit an explicit terminal reason; backoff between tries, not after the last.
- API: does a refused refund read as `resolved: false`?
</details>

## Interview preparation

Model answers. The good version is short, concrete, and names a trade-off — not a definition recital.

**"Walk me through what you built."**

> A dispute-review service where the model proposes and a deterministic harness disposes. `POST /review` takes a transaction case, a decision layer proposes an action citing a rule from a closed enum, and the harness executes it against a payment rail, observes what came back, and loops — retry, correct, or escalate — until a terminal state. The response reports what actually happened, not what was proposed. 112 tests, none of which call an LLM, running in about a second.

**"Why not just let the model call the payment API directly?"**

> Because a tool call is a proposal, not an action. Between "the model decided to refund 120" and "the customer has 120" there is execution, verification, persistence, and failure handling. Routing it through one chokepoint gives one place to log, rate-limit, validate, and roll back — the same reason a frontend doesn't write to the database directly. It's also what makes the boundary testable: the entire recovery layer has no model in it, so I can test it exhaustively.

**"How do you stop it double-refunding on a timeout?"**

> The idempotency key is derived from the logical intent — case id plus amount to two decimal places — and deliberately excludes the attempt number, so every retry of the same refund carries the same key and the rail dedupes it. A timeout is an absence of information, not evidence of failure; the refund may already have happened. Idempotency is what makes it safe to act under that uncertainty. And the fake gateway implements dedupe for real, because a fake more forgiving than production manufactures green tests for broken code.

**"What's the difference between retry and correct?"**

> Retry is for a transient failure where I don't know whether it happened — same parameters, same key. Correct is for an operation that definitely happened but not as asked, like a partial settlement — different amount, and therefore a *different* key, because refunding 30 is genuinely a different operation from refunding 120. Getting them backwards is the interesting failure: sharing a key on a correction means the shortfall never gets paid, and minting a new key on a retry double-refunds.

**"How do you test something non-deterministic?"**

> Mostly by noticing how little of it is. The loop, the idempotency key, the recovery logic, the schema constraints, the grounding check — all deterministic, all tested exhaustively, no model. What's genuinely non-deterministic is one question: was the decision good? That needs a golden set and metrics with thresholds, and I keep it in a separate suite so the fast deterministic gate stays fast. Separating those two is most of the work.

**"How do you stop the model inventing a policy?"**

> The decision must cite a rule from a closed enum. That turns hallucination from a subjective judgement into a membership test, and a membership test can fail a build. Anything outside the set raises rather than falling back to a default — a fallback would be indistinguishable downstream from a genuine escalation, and monitoring would show a healthy service quietly escalating everything. The limit is that the check is only as good as the catalogue, so the enum and the prompt have to be locked together — there's a test asserting every enum member appears in the prompt.

**"What would you do differently / what's still weak?"**

> Three things. The gateway is in-memory, so the ledger dies with the process — real persistence and an outbox pattern is the next piece. Correction handles the shortfall case only; over-refunds and currency mismatches escalate, which is deliberate but not free. And the retry budget is global rather than per-failure-mode — three timeouts and three partial settlements are very different situations to spend the same budget on.

> **Note on that last answer.** Being able to name your own system's limits precisely is worth more in an interview than any feature list. It demonstrates you've thought past the happy path, which is exactly the claim this chapter is trying to let you make.

## What's still open

Honest status:

- **Verified**: the loop, resolver, corrector, idempotency, decision layer, API contract, and structured logging — 112 tests plus a live `uvicorn` run, both transcribed above from real output.
- **Not verified**: that `app/schemas.py`'s field names match `portfolio-risk-evaluator`'s real `TransactionCase` / `ReviewDecision` / `RuleId`. That repo's code was not available to read. The schemas here are **this notebook's own** — structurally right, deliberately not presented as a transcription of production. [`WIRING.md`](./WIRING.md) has the adapter pattern that makes the swap a one-file change.
- **Not built**: persistence (the ledger is in-memory), authentication, and an outbox for the case where the process dies between the rail confirming and our state persisting — the one failure mode this design observes (`APPROVED` + `not state_persisted` → `ESCALATE`) but cannot yet prevent.

## Decision log

**ADR-002 — Introduce an explicit Harness layer between decision and execution**

| Field | Detail |
|---|---|
| Decision | `app/harness/`: types with an intent-derived idempotency key, a `PaymentGatewayClient` Protocol plus one fake and four doubles, a pure `resolve_next_action()`, a separate `Corrector`, and `ReviewHarness` running a bounded ACT→OBSERVE→CORRECT loop. |
| Consequence | `/review` orchestrates decision → harness → response, and the response reflects `terminal_reason`, not just the proposal. |
| Status | Implemented, 112/112 passing, service verified running. Trunk wiring pending real schemas. |

**ADR-003 — The loop is bounded and every exit is an explicit terminal reason**

| Field | Detail |
|---|---|
| Context | ADR-002's first implementation returned a `NextAction` without acting on it — `RETRY` and `CORRECT` had no implementation at all. |
| Decision | `max_attempts` (default 3, `ValueError` below 1); four `TerminalReason` values distinguishing gateway refusal, budget exhaustion, and uncorrectable gaps. |
| Consequence | An operator can tell "the rail said no" from "we never got an answer" without reading code. No path returns "probably fine". |
| Status | Implemented and tested. |

## Next

Chapter 5 and this chapter cover the *execution* half of tool use — what happens after a tool call. The other half, how a model is told what tools exist and how it emits a call in the first place, has been assumed rather than explained. [Chapter 7 — Tool Calling and Function Schemas](../07-tool-calling-and-function-schemas/README.md) covers that mechanism, and it is the last structural piece before evaluation.
