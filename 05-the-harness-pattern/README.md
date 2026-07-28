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

## Applied to `portfolio-risk-evaluator`

This is where the diagram stops being generic and becomes a concrete next milestone. Current state of the project:

- `/health` — functional.
- `/review` — returns `501 Not Implemented`. `TransactionCase` and `ReviewDecision` schemas exist; the closed `RuleId` enum exists; six tests pass.

Everything built so far covers the **Model / Decision** box only: given a `TransactionCase`, produce a `ReviewDecision` that cites a real `RuleId`. That's step 3 of the agent loop — reasoning and proposing an action. Nothing executes it yet. The harness is the missing majority of this diagram, and it's what turns `/review` from an LLM wrapper into something closer to what the project's evaluation layer (RuleId grounding, hallucination prevention, compliance mapping) was actually built to defend.

> **Walking skeleton, not a mock that gets replaced later.** The project's existing architecture rule applies directly here: the harness's system clients should be built against a real interface (e.g. an abstract `PaymentGatewayClient`) with an in-memory fake implementation behind it for now — not a throwaway mock that gets rewritten when a real gateway is wired in later. Swapping the fake for Stripe/Adyen/whatever real rail applies should mean writing a new class that satisfies the same interface, not restructuring the endpoint.

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

## Next

[Chapter 6 — Implementing and Testing the Harness](../06-implementing-and-testing-the-harness/README.md) turns this into working, tested code.
