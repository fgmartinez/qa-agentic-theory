# Chapter 5 — The Harness Pattern

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 4 — Prompt Engineering](../04-prompt-engineering/README.md). Next: [Chapter 6 — Implementing and Testing the Harness](../06-implementing-and-testing-the-harness/README.md).*

Closing the loop between a model's decision and the real world — and why most agent demos never build this layer.

## The problem: a tool call is not an action

Chapter 3 ended on a gap: agent evaluation content almost universally stops at step 3 of the loop — *did the model call the right tool with the right parameters*. `ToolCorrectnessMetric` answers exactly that question and nothing more.

But a tool call is a **proposal**, not an **action**. Between "the model decided to call `issue_refund(amount=120, case_id="C-4471")`" and "the refund happened, and the system knows it happened correctly," there is an entire layer of work: actually invoking the real system, checking the response makes sense, persisting the new state, and — critically — deciding what to do if any of that fails. Trusting the tool call silently is how a payment agent ends up behaving as if a refund succeeded when the gateway actually returned a timeout.

That layer is the **harness**. It's the piece of infrastructure — not a metric, not a prompt — that sits between the model's decision and the systems it affects.

## Anatomy of the harness

The diagram this chapter is built on (`images/harness-feedback-loop.png`) models it with a refund decision as the running example. Reproduced here in the harness's own vocabulary:

```
Model decides (tool call) → Harness → Execution (real systems) → Observation (signals) → New decision
```

| Box | Responsibility |
|---|---|
| **Model / Decision** | Reasons over the case and proposes an action — e.g. "approve this refund." This is as far as a plain LLM call, or step 3 of the agent loop, goes on its own. |
| **Harness** | Takes that proposal and actually carries it out against real systems, then hands the result back into the model's context. The model never talks to the payment API or the database directly — the harness is the only thing with that access, which is also what makes the boundary testable and auditable. |
| **Execution / systems involved** | The concrete systems the harness calls — in the source diagram: payment API, database, refunds ledger. In `portfolio-risk-evaluator`: a payment gateway client and a dispute/case store. |
| **Signals / Observation** | What actually came back: was the operation approved, rejected, or left pending? Does the amount match what was expected? Does the database reflect the new state? This is evidence, not the model's opinion of what happened. |
| **New decision** | Given the observation, what happens next: **terminate** (done), **correct** (fix and retry with adjusted parameters), **retry** (try the same action again — e.g. after a transient timeout), or **escalate** (hand off to a human). This is a resolver, not another LLM call — usually a small, deterministic state machine, precisely because this step needs to stay predictable even when the model isn't. |

> **Why the model doesn't touch the systems directly.** If the LLM call itself performed the API call, a hallucinated parameter or a malformed response would corrupt production state with no checkpoint in between. Routing every effect through the harness gives you one place to validate, log, rate-limit, and roll back — the same reason a REST API doesn't let the frontend write to the database directly.

## The loop, and what "autonomy" actually means

The source diagram states the general loop as:

```
ACTION → RESULT → OBSERVATION → NEW DECISION
```

and defines autonomy as a formula rather than a vibe:

```
AUTONOMY = ACT + OBSERVE + CORRECT
```

This is a useful, falsifiable definition. A system that acts but never observes isn't autonomous — it's a fire-and-forget script. A system that observes but can't correct isn't autonomous either — it's a dashboard. All three, in a loop, are what the word "agent" needs to mean beyond "an LLM with function calling enabled."

## Applied: where the harness belongs, and where it doesn't

The most useful thing this chapter can teach is **when the pattern does not apply** — because an unused abstraction is a liability, not a hedge.

### `fintech-support-ai-evaluator` — the harness fits

That project's agent has `escalate_to_human` and payment-side operations: decisions with **effects**. An escalation that silently fails to create a case is exactly the gap between "the model decided" and "the world changed". Full pattern applies — executor, resolver, and loop.

### `portfolio-risk-evaluator` — only half the pattern fits

Verified against the real repo (`4a10109`): its `/review` produces a **recommendation**, not an action.

```python
class ReviewAction(str, Enum):
    auto_approve = "auto_approve"
    secondary_review = "secondary_review"
    escalate_immediate = "escalate_immediate"
```

No amount moves. No gateway exists, and the project's own rules forbid connecting one. **`/review` is a pure function from case to recommendation — and a pure function does not need a harness.**

What *does* apply is the resolver half. That project's `compute_risk_level(triggers) -> RiskLevel` is already a resolver in this chapter's sense, arrived at independently: a pure function mapping collected evidence to a classification, no I/O, no model, exhaustively testable. Everything this chapter says about resolvers — fail-safe fallthrough, branch order as behaviour, property tests over the input space — applies to it directly.

And the fail-safe question has a precise local form: **`auto_approve` is that system's "assume it worked."** It is the one outcome that must never be reachable by omission or by an unmatched branch.

> **The distinction worth carrying into an interview.** The harness pattern applies where a decision has an *effect*. Splitting it into an executor (needed only when something can fail in the world) and a resolver (needed whenever evidence must be turned into a verdict) is what lets you say *"no harness here, and here's why"* as a design decision rather than an omission.

> **Walking skeleton, not a mock that gets replaced later.** Where the executor *is* needed, build its clients against a real interface (e.g. an abstract `PaymentGatewayClient`) with an in-memory fake behind it — not a throwaway mock. Swapping the fake for a real rail should mean writing a new class satisfying the same Protocol, not restructuring the endpoint.

## Why this is a genuine testing dimension

`ToolCorrectnessMetric` tests whether the model called `issue_refund` with the right `case_id` and `amount`. It says nothing about whether the harness correctly turned a `TIMEOUT` into a `RETRY` instead of silently treating it as success. That's a separate, deterministic layer, testable with plain pytest, independent of the LLM entirely — worked through fully in Chapter 6.

This is also where the domain-knowledge argument gets concrete rather than abstract: DORA's operational resilience requirements are specifically about systems that *detect* failures and *respond correctly*, not just about systems that make correct decisions on the happy path. A harness with an untested resolver is exactly the kind of gap that argument is about — and Chapter 6 turns it into a real test, not just a talking point.

## Decision log

**ADR-002 — Introduce an explicit Harness layer between decision and execution**

| Field | Detail |
|---|---|
| Context | `/review` produces a `ReviewDecision` but does not execute it. Diagram analysis (this chapter) surfaced that tool-call correctness alone doesn't cover execution failure or recovery. |
| Decision | Add `app/harness/` as a distinct module in the trunk project: types, a `PaymentGatewayClient` protocol + in-memory fake, and a pure `resolve_next_action()` state machine. |
| Consequence | `/review` will orchestrate: LLM decision → harness execution → resolver, instead of returning the LLM's decision directly. Adds one new testable, LLM-independent layer. |
| Status | Proposed here; implemented and unit-tested in [Chapter 6](../06-implementing-and-testing-the-harness/README.md). |

## Exercises

### 1 — Test the formula

`AUTONOMY = ACT + OBSERVE + CORRECT`. Classify each system and name the missing term:

(a) A cron job that posts a daily report to Slack.
(b) A dashboard that alerts when refund failures exceed 5%.
(c) A retry wrapper that re-sends any failed HTTP request three times.
(d) An LLM that calls `issue_refund` and returns the tool call to the user.

<details><summary>Solution</summary>

(a) **ACT only** — fire-and-forget. No observation, so it cannot know it failed.
(b) **OBSERVE only** — a dashboard. It knows, and can do nothing.
(c) **ACT + CORRECT, no real OBSERVE** — the interesting one. It reacts to *transport* failure but never inspects the *result*: a 200 response containing `{"status": "rejected"}` counts as success. It corrects a signal it isn't actually reading.
(d) **Neither OBSERVE nor CORRECT** — and arguably not even ACT, since a tool call is a proposal. This is most agent demos.

The formula's value is that it's falsifiable. "Is this autonomous?" is a vibe; "which of the three terms is missing?" has an answer.
</details>

### 2 — Justify the indirection

A colleague says: "The harness is over-engineering. Let the model's tool call hit the payment API directly — you've just added a class." Give the strongest version of their argument, then answer it.

<details><summary>Solution</summary>

**Their strongest case:** it's genuinely less code, the indirection buys nothing on the happy path, and the tool-calling layer already validates arguments against a schema (Chapter 7). If the call is well-formed, why wrap it?

**The answer:** because the happy path isn't what the layer is for. Four things become impossible without it — one chokepoint to log, rate-limit and roll back; a place to distinguish a timeout from a rejection and respond differently; a deterministic recovery path that can be tested exhaustively with no model; and an audit trail pairing the decision with what actually happened. Chapter 7's schema validates that the *request* is well-formed; it says nothing about what the *response* means.

The framing that usually lands: it's the same reason a frontend doesn't write directly to the database. Nobody calls that over-engineering, and the argument is identical — one place to enforce invariants beats N callers each getting it right.
</details>

### 3 — Design the resolver before reading Chapter 6

A gateway returns `status`, `settled_amount`, and `persisted`. Write the mapping to `{TERMINATE, RETRY, CORRECT, ESCALATE}` yourself. Then state what your unmatched-input case does, and why.

<details><summary>Solution (compare against Chapter 6)</summary>

The mapping most people reach: timeout → retry, rejected → escalate, approved-but-wrong-amount → correct, approved-and-persisted → terminate.

The part worth grading yourself on is the **fallthrough**. If your default was "assume success", that is precisely the failure mode this notebook exists to name — a system that silently reports success on a signal it doesn't recognise. It must be `ESCALATE`.

Second thing to check: did you handle `approved` + `not persisted`? The rail says yes, your system has no record. That disagreement can't be resolved automatically, and it's the case people most often forget to write down.
</details>

## Interview preparation

**"What's the harness pattern?"**

> A layer between the model's decision and the systems it affects. The model proposes an action; the harness executes it against the real system, observes what actually came back, and decides what happens next — terminate, retry, correct, or escalate. The key property is that the model never holds a client to the payment API or the database; the harness is the only thing with that access. That's what makes the boundary auditable and testable.

**"Why does that matter more for AI than for normal software?"**

> Because the component producing the decision is probabilistic and the component executing it must not be. In normal software the caller and the callee are both deterministic, so you can reason about the whole path. With a model in front, the only way to make guarantees is to put a deterministic layer between the decision and the effect — and then the guarantees are about that layer, which you can test exhaustively. It's also where the domain argument gets concrete: DORA's operational-resilience requirements are about systems that detect failures and respond correctly, which is exactly this layer, not the model's accuracy.

**"Define autonomy."**

> Act plus observe plus correct, in a loop. It's a useful definition because it's falsifiable — a system that acts but never observes is a fire-and-forget script, and one that observes but can't correct is a dashboard. Most things marketed as agents are missing at least one term, and naming which one is missing is a faster diagnosis than arguing about whether something "is an agent".

**"What's the difference between a tool call and an action?"**

> A tool call is a proposal. The model emitting `issue_refund(amount=120, case_id="C-4471")` means it has decided; it does not mean anything moved. Between that decision and "the customer has 120 and our system knows it" there's execution, verification, persistence, and failure handling. Trusting the tool call is how a payment agent behaves as though a refund succeeded when the gateway actually timed out — and `ToolCorrectnessMetric` will happily report 100% on that system, because the call *was* correct.

## Next

[Chapter 6 — Implementing and Testing the Harness](../06-implementing-and-testing-the-harness/README.md) turns this into working, tested code.
