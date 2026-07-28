# Capstone — Build It Yourself

*Part of [qa-agentic-theory](./README.md). Prerequisites: Chapters 1–12.*

A specification, not a tutorial. There are no code snippets to copy — that is deliberate. Every technique needed is in the notebook; assembling them against requirements rather than instructions is the skill the notebook exists to build, and it is the closest thing here to the real task of *sitting down and building a harness system*.

**Different domain from Chapter 6 on purpose.** Reproducing the dispute reviewer tests recall of one solution. Transferring the pattern to a new domain tests whether you understood it.

---

## The system: a subscription cancellation agent

A SaaS company's support agent handles cancellation requests. It must decide what to do, execute it against a billing system, verify the result, and recover or escalate.

### Business rules

| Condition | Decision | Rule id |
|---|---|---|
| Enterprise plan (any value) | Escalate — account manager handles it | `ESCALATE_ENTERPRISE_ACCOUNT` |
| Active contract with >30 days remaining | Escalate — early termination fee applies | `ESCALATE_EARLY_TERMINATION` |
| Customer cites a service outage | Refund the last billing period, then cancel | `REFUND_SERVICE_OUTAGE` |
| Within 14 days of first payment | Full refund and cancel | `REFUND_TRIAL_PERIOD` |
| Standard cancellation | Cancel at period end, no refund | `CANCEL_AT_PERIOD_END` |
| Already cancelled | Reject — nothing to do | `REJECT_ALREADY_CANCELLED` |

Precedence is top to bottom. An enterprise account citing an outage escalates.

### The billing gateway

Two operations, and the second is the interesting one:

```
cancel_subscription(subscription_id, effective_date) -> Result
issue_refund(subscription_id, amount)               -> Result
```

Both return: `status` ∈ {`confirmed`, `refused`, `pending`, `timeout`}, plus `refunded_amount` (refunds only) and `effective_date` (cancellations only).

**Two properties that make this harder than Chapter 6, and are the point of the exercise:**

1. **`REFUND_SERVICE_OUTAGE` requires two operations in order** — refund, *then* cancel. A partial success (refund confirmed, cancel timed out) is a real state your design must handle. The customer has their money and an active subscription.
2. **`pending` is a legitimate terminal state here**, unlike Chapter 6. Some cancellations settle asynchronously at period end. Your resolver must distinguish "pending and that's expected" from "pending and that's wrong" — and you will need something on the command to tell them apart.

---

## Requirements

### Part 1 — The harness

- [ ] Types: execution status, result, verdict, terminal reason, command with an idempotency key
- [ ] A gateway `Protocol` plus a working in-memory fake that **honours idempotency**
- [ ] Test doubles: scripted, sequenced, flaky, partial-refund
- [ ] A **pure** resolver — no I/O, no clock, no model
- [ ] A corrector that refuses rather than guessing when evidence is missing
- [ ] A **bounded** loop where every exit is an explicit terminal reason
- [ ] Multi-step orchestration for the refund-then-cancel flow

**Design decisions to make deliberately and be able to defend:**

1. Does the idempotency key derivation differ from Chapter 6's? Two operations now share a subscription id. *(Hint: what makes two operations logically distinct?)*
2. What happens when the refund confirms and the cancel times out? Retrying the cancel is safe if idempotent — but what if it keeps timing out? Is the terminal state "escalate" with the customer refunded but subscribed? **This is the requirement most people miss, and it is the one a senior interviewer will probe.**
3. How does the resolver tell an expected `pending` from an unexpected one, given it only sees an `ExecutionResult`?

### Part 2 — The decision layer

- [ ] A closed rule enum, no `other`, no free-text fallback
- [ ] Pydantic schemas with constraints that are genuinely controls (what is the analogue of "a negative refund is a payment"?)
- [ ] A `DecisionEngine` Protocol
- [ ] A deterministic rule engine implementing the precedence above
- [ ] An LLM engine: prompt builder, parser, **grounding validation**, `DecisionError` with no fallback value

### Part 3 — The API

- [ ] `GET /health`, `GET /rules`, `POST /cancel`
- [ ] Correlation id middleware, inbound header respected
- [ ] Structured JSON logging carrying the correlation id
- [ ] Response reflecting the **terminal reason**, not just the proposal
- [ ] Decision-layer failure escalates rather than 500ing

### Part 4 — The test suite

Minimum coverage:

- [ ] Resolver, **exhaustively** — every status × boolean combination
- [ ] A property test: only a genuinely clean result may terminate
- [ ] Branch *order*, not just branch coverage
- [ ] Retry reuses the idempotency key; correction changes it
- [ ] The gateway does not double-charge on replay
- [ ] Budget exhaustion is distinct from refusal
- [ ] **Partial success in the two-step flow** ends in a defensible state
- [ ] Rule precedence, including enterprise-plus-outage
- [ ] Threshold boundaries (30 days, 14 days) on both sides
- [ ] A hallucinated rule id is rejected; near-misses too
- [ ] Malformed model output raises rather than defaulting
- [ ] API: a refused cancellation does not read as success
- [ ] API: invalid input is rejected before any decision

**Target: 80+ tests, none calling a model, running in under two seconds.**

### Part 5 — Evaluation

- [ ] 12 golden cases: 4 direct, 3 multi-hop, 3 adversarial, 2 escalation
- [ ] Each with risk level, expected tools, expected tool order, and `notes` explaining why it exists
- [ ] `thresholds.yaml` with a **rationale per number**
- [ ] One GEval criterion with explicit PASS and FAIL cases
- [ ] A gate script blocking on any critical failure regardless of aggregate pass rate

### Part 6 — Compliance and observability

- [ ] A traceability table: requirement → behaviour → cases → metric → threshold → enforcement → runtime evidence, for **two** EU AI Act articles
- [ ] Structured logs sufficient to answer "was any customer double-refunded?" without a debugger
- [ ] A CI design splitting fast deterministic tests from slow judge-scored ones
- [ ] A written incident walkthrough: an alert fires on a spike in escalations — narrate detect → bound → mitigate → diagnose → postmortem against **your own** log format

---

## Checkpoints

Stop and verify at each; don't carry a broken foundation forward.

| # | Checkpoint | Test |
|---|---|---|
| 1 | Types | Key stable across retries, different across amounts and operations |
| 2 | Gateway | Fake replays on repeated key rather than double-charging |
| 3 | Resolver | All combinations covered; expected-`pending` distinguished |
| 4 | Corrector | Refuses without evidence; computes the remainder, not the original |
| 5 | Loop | Every exit an explicit terminal reason; backoff between, not after |
| 6 | **Two-step flow** | **Partial success reaches a defensible, documented state** |
| 7 | Decision | Precedence correct; hallucinated rule rejected |
| 8 | API | Refused cancellation reads as unresolved |
| 9 | Suite | 80+ tests, no model, under two seconds |
| 10 | Evaluation | Gate blocks on a critical failure at a 95% pass rate |

---

## Self-assessment

**Did you actually build it, or reproduce it?**

- Did you copy Chapter 6's idempotency key derivation, or reason about what makes two operations logically distinct here?
- Did you notice `pending` needs different handling before or after writing the resolver?
- Did you handle refund-confirmed-plus-cancel-failed before a test forced you to?

**Could you defend it?** Answer out loud, no notes:

1. Walk me through what you built. *(2 minutes, no jargon)*
2. Why is the resolver a pure function?
3. What happens if the refund succeeds and the cancellation times out?
4. How do you know a customer was never double-refunded?
5. Why is your tool-order threshold 1.0 when faithfulness is 0.9?
6. What's still weak about this system?

Question 6 is the one that separates candidates. **Being able to name your own system's limits precisely is worth more than any feature list** — it demonstrates you thought past the happy path. If you can't answer it, you built it without understanding its boundaries.

**Reference answers for 3 and 4**, since they're the ones with a right shape:

> **(3)** The refund is confirmed and idempotent, so it is not re-issued. The cancellation retries under its own key. If it exhausts the budget, the terminal reason is a distinct value — something like `ESCALATED_PARTIAL_COMPLETION` — because "refunded but still subscribed" is operationally different from both a clean escalation and a clean failure. The response says so explicitly, and the attempt trail shows exactly which operation completed. What it must *not* do is report success because the first operation worked, or retry the refund because the overall flow failed.

> **(4)** From the logs. Every attempt event carries the idempotency key; a repeated key with `replayed: true` proves the gateway deduplicated. It is a query, not an investigation — which is only true because the key was logged per attempt rather than per request.

---

## When it's done

You have built, from a specification, a bounded agent loop with idempotent execution, deterministic recovery, grounded decisions, a fast comprehensive test suite, a risk-weighted evaluation gate, and a compliance chain from regulation to test id.

That is the thing this notebook exists to make you able to do — and it is a substantially more defensible interview answer than "I built a RAG chatbot", because almost every candidate has the second one.

Then go back to [Chapter 6](./06-implementing-and-testing-the-harness/README.md) and read it again. Different chapter now.
