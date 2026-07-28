# Chapter 3 — AI Agents 101

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 2 — RAG Fundamentals](../02-rag-fundamentals/README.md). Next: [Chapter 4 — Prompt Engineering](../04-prompt-engineering/README.md).*

What an AI agent actually is, what a tool is, and the four-step loop every agent runs on — the vocabulary the rest of this notebook is built on.

## What is an AI agent?

An **AI agent** is an LLM wired up to two things a plain chatbot doesn't have: **tools** it can invoke to affect or query the outside world, and a **loop** that lets it act on what happens after it uses one. A chatbot answers in text and stops. An agent can decide it needs more information, go get it, and change its answer based on what it finds — without a human manually feeding it the next step.

The distinction that actually matters, restated from a slightly different angle than Chapter 1's transformer mechanics: a plain LLM call is a pure function — text in, text out, nothing else happens. An agent is that same function wrapped in a loop with side effects: it can read a database, call an API, retrieve a document, and *do something different* depending on what comes back. That side-effect capability is also exactly where the risk lives, which is the reason this notebook spends an entire chapter (Chapter 5) on the layer that's supposed to control it.

## What are tools?

A **tool** is a function the model can choose to call, described to the model as a name, a natural-language description of what it does, and a schema for its parameters. The model doesn't execute the tool itself — it emits a structured request ("call `get_payment_policy` with `topic="refunds"`"), and something outside the model (Chapter 5's harness, in this notebook's vocabulary) actually runs it and returns the result.

Three properties of a good tool definition, in order of how often getting them wrong causes real bugs:

1. **The description has to be unambiguous about *when* to use it.** A vague description ("looks up information") invites the model to call the wrong tool for a question that's actually covered by a different one. `check_invoice_status` vs. `get_payment_policy` in `fintech-support-ai-evaluator` only stay distinct if their descriptions make the boundary between "status of a specific invoice" and "the policy that applies in general" explicit.
2. **The parameter schema has to be strict enough to reject nonsense.** A `case_id: str` with no format constraint accepts a hallucinated ID just as happily as a real one — the schema is a first line of defense, not just documentation.
3. **The tool has to return something the model can actually reason about.** A tool that returns a raw 500-line JSON blob forces the model to extract the relevant fact itself, which is one more place for it to misread something. Returning a focused, pre-summarized result is worth the extra engineering.

## The loop, in one sentence

> An agent is a chatbot with a tool, plus a loop that lets it act on what happens after it uses the tool. Remove the loop — call a tool once and stop — and what's left is a function call, not an agent. The loop is the entire point.

Every AI agent, regardless of framework (LangGraph, CrewAI, a hand-rolled loop), runs the same four-step cycle. The names vary by source, but the shape doesn't. A public roadmap diagram (archived at [`images/ai-agents-roadmap.png`](../images/ai-agents-roadmap.png)) labels the steps: **Perception / User Input**, **Reason and Plan**, **Acting / Tool Invocation**, **Observation & Reflection**. That's the vocabulary used throughout this notebook.

## The four steps

1. **Perception / Input** — the agent receives the current state: the user's request, plus anything already in context (prior turns, retrieved documents, prior tool results). This is the only information the model has. If something relevant isn't in this input, the model cannot know it, no matter how capable the model is.

2. **Reason and Plan** — the model decides what to do next given that input: answer directly, retrieve more information, or call a tool. This is where prompt engineering (Chapter 4), chain-of-thought, and system instructions do their work — they shape *how* the model reasons before it commits to an action.

3. **Acting / Tool Invocation** — the model emits a structured call: which tool, with which parameters. At this point the model has only *proposed* an action — nothing in the real world has happened yet. This distinction is small to state and enormous in consequence, and it's the entire subject of Chapter 5.

4. **Observation & Reflection** — the result of the action (or the fact that it failed) is fed back into the model's context. The model reasons again, now with new information, and either finishes or loops back to step 2.

> **QA bridge.** Map this to Gherkin: step 1 is your `Given` (context/state), step 2 is the implicit decision logic, step 3 is your `When` (the action under test), step 4 is your `Then` (the assertion) — except the agent's "Then" isn't a static assertion, it's dynamic: what it observes changes what it does next. That's the part traditional BDD doesn't have to model, and it's exactly what Chapter 5 covers.

Chapter 1 already covered the mechanics underneath step 2 — tokenization, context windows, temperature — so this chapter doesn't repeat them. What's worth restating here is *why* they matter specifically for an agent: temperature affects how reproducible the tool-selection decision in step 3 is, and the context window caps how much of steps 1 and 4's accumulated history the model can still see by the time it's deciding what to do next.

## Why this loop shape matters for QA

Each of the four steps is a *different* failure mode, and conflating them is the most common mistake in agent testing:

| Step | Failure mode | What it looks like |
|---|---|---|
| Perception | Missing or wrong context | Agent answers about the wrong transaction because the wrong case was retrieved. |
| Reason and Plan | Wrong decision logic | Agent decides to auto-approve a transaction that should have been escalated. |
| Acting | Wrong tool / wrong parameters | Agent calls the refund tool with the wrong transaction ID. This is what `ToolCorrectnessMetric` catches. |
| Observation | Silent execution failure | The tool call was *correct*, but the payment API timed out, and nothing downstream noticed — the system behaves as if the refund succeeded when it didn't. |

> **The gap.** Most agent evaluation content — courses, DeepEval's built-in metrics, most portfolio projects — stops at step 3. It tests whether the right action was proposed. It does not test what happens once that action is executed and the world doesn't cooperate. That's step 4, and step 4 needs its own architectural component, not just a metric. That component is the **harness** — Chapter 5.

## Worked example: one loop, traced

The four steps are abstract until you watch them run. A customer asks: *"Was invoice INV-1002 paid, and if not why is it taking so long?"*

```
TURN 1
  1. PERCEPTION   system prompt + tool defs + "Was INV-1002 paid, and why so slow?"
  2. REASON       two things asked: a specific status AND a general policy.
                  Status first — the answer may make the second moot.
  3. ACT          check_invoice_status(invoice_id="INV-1002")     ← a PROPOSAL
  4. OBSERVE      {"status": "pending", "amount": 89.5}

TURN 2
  1. PERCEPTION   everything above, PLUS the tool result
  2. REASON       pending, so the "why slow" half now matters
  3. ACT          get_payment_policy(topic="payout_schedule")
  4. OBSERVE      "Payouts settle every Tuesday."

TURN 3
  1. PERCEPTION   everything above, PLUS both results
  2. REASON       enough to answer
  3. ACT          — no tool call —
  4. —            "INV-1002 is still pending (89.50 EUR). Payouts settle
                   Tuesdays, so it should clear then."
```

Four things this makes visible that the numbered list above cannot:

1. **Context accumulates.** Turn 3's input contains everything from turns 1 and 2. A long agent conversation is not a series of small requests — it is one request that grows, which is why Chapter 1's context-window arithmetic is an agent concern and not a background detail.
2. **The loop terminates by the model declining to call a tool.** There is no "done" signal. Step 3 producing prose instead of a call *is* the exit condition — and an agent that never stops proposing tools is the failure mode this implies.
3. **The calls were sequential by necessity.** Turn 2's decision depended on turn 1's *result*. Had the customer asked about two invoices, both lookups could have gone out in one turn (Chapter 7's parallel calls).
4. **Nothing here executed anything.** Both tools were reads. Had turn 2 been `issue_refund`, step 3 would still have been only a proposal — and everything Chapter 5 covers would suddenly apply.

## Exercises

### 1 — Assign the failure

For each incident, name which of the four steps failed, and say why the other three are wrong:

(a) The agent answers a question about the wrong customer's invoice.
(b) The agent calls `get_payment_policy` when asked about a specific invoice.
(c) The agent auto-approves a €4,000 refund that policy says needs a human.
(d) The refund tool timed out; the agent tells the customer it's been refunded.

<details><summary>Solution</summary>

(a) **Perception.** The wrong record entered context. The reasoning was sound *given what it saw* — this is a retrieval bug, and no amount of prompt work fixes it.
(b) **Acting.** Right intent, wrong tool — a tool-selection error, which is what `ToolCorrectnessMetric` measures and what Chapter 7's description boundaries prevent.
(c) **Reason and Plan.** The decision logic itself is wrong. The right tool may well have been called correctly afterwards.
(d) **Observation.** The tool call was *correct*; execution failed and nothing downstream noticed. No metric on steps 1–3 catches this — it needs Chapter 5's harness.

The reason this exercise matters: (b) and (c) are frequently misdiagnosed as each other, and (d) is routinely misdiagnosed as (c). Fixing the prompt when the real fault is (d) produces months of no improvement.
</details>

### 2 — Find the missing loop

Someone shows you code: it builds a prompt, calls the model with tools, gets a tool call, executes it, returns the tool's output to the user. They call it an agent. Is it?

<details><summary>Solution</summary>

No. That's a **function call with extra steps**. The tool result goes to the *user*, never back into the model's context — so the model never reasons about what came back, and cannot decide to do something different.

The tell: there's no `while` or recursion. One pass, one exit. Remove the loop and you remove the model's ability to act on what it observed, which is the only thing separating an agent from a chatbot with routing.

Concretely, this system cannot answer the worked example above at all: it would return the raw `{"status": "pending"}` and never get to the policy lookup.
</details>

### 3 — Break the termination condition

An agent loops forever, calling `check_invoice_status` on the same invoice repeatedly. Give three plausible causes, one per layer.

<details><summary>Solution</summary>

1. **The result isn't reaching context.** The tool executes but its output isn't appended as a `role: "tool"` message — so from the model's view the question is still unanswered, and it tries again. A wiring bug, not a model bug.
2. **The result is unusable.** It's returned, but as a 500-line JSON blob or an unlabelled error string, and the model can't extract the fact — so it retries hoping for better. Chapter 3's third tool property ("returns something the model can reason about") and Chapter 7's error shaping both address this.
3. **No iteration budget.** Nothing caps the loop, so a model that would have looped twice on a bad day loops forever. This one is not really a cause — it's the *absence of the control that bounds the other two* (Chapter 6's `max_attempts`).

Worth noting the order: 1 and 2 are the actual bug, 3 is what stops it costing €400 before anyone notices. Fix all three.
</details>

### 4 — Map to Gherkin, then find where it breaks

Write the worked example above as a Gherkin scenario. Which part of the agent's behaviour does the notation fail to express?

<details><summary>Solution</summary>

```gherkin
Given invoice INV-1002 exists with status "pending"
  And the payout policy states settlement occurs on Tuesdays
When the customer asks whether INV-1002 was paid and why it is slow
Then the answer states the invoice is pending
  And the answer explains payouts settle on Tuesdays
```

What it cannot express: **the `Then` changed what happened next.** In turn 1 the agent observed "pending" and that observation *caused* turn 2's policy lookup. Had the status been "paid", turn 2 would never have happened.

Gherkin assumes a static assertion at the end of a fixed path. An agent's observation is an input to its next decision, so the path is not fixed — the number of steps depends on the data. That's the structural difference between BDD and agent testing, and it's the reason a golden set (Chapter 9) records *expected tool sequences* rather than a single expected output.
</details>

## Interview preparation

**"What is an AI agent?"**

> An LLM with tools and a loop. A plain LLM call is a pure function — text in, text out, nothing happens. An agent can call something, see what came back, and do something different because of it. The loop is the whole point: remove it and you have a function call. And the side-effect capability is exactly where the risk lives, which is why the interesting engineering isn't the model, it's the layer that controls what the model is allowed to actually do.

**"Walk me through the agent loop."**

> Four steps. Perception — the model receives the current state: the request plus everything already in context. Reason and plan — it decides whether to answer or call a tool. Acting — it emits a structured tool call, which is a *proposal*; nothing has happened yet. Observation — the result goes back into context and it reasons again, either finishing or looping. Two things I'd flag: context accumulates every turn, so a long conversation is one growing request; and the loop terminates by the model *declining* to call a tool, not by any explicit done signal.

**"Where do most people go wrong testing agents?"**

> They test step 3 and stop. `ToolCorrectnessMetric` asks whether the right tool was called with the right parameters, and that's genuinely useful — but it says nothing about what happened when the call executed. The tool call can be perfectly correct and the payment API times out and nothing downstream notices, so the system behaves as if a refund succeeded. That's a step-4 failure, and it needs an architectural component, not a metric. Each of the four steps is a distinct failure mode, and conflating them means fixing prompts when the real bug is in execution.

**"How is this different from testing a normal application?"**

> The assertion isn't static. In BDD the `Then` is the end of the path; in an agent the observation *feeds the next decision*, so the number of steps depends on the data. That means a golden set records an expected tool *sequence* rather than one expected output, and it means an agent can reach the right answer by a route you didn't anticipate — which you have to decide whether to score as a pass. The deterministic parts, though — did it call a registered tool, were the arguments schema-valid, did the harness recover — those test exactly like normal software, and most of the system is those parts.

## Next

Before getting to the harness, step 2 — *how* the model reasons before it acts — deserves its own chapter: [Chapter 4 — Prompt Engineering](../04-prompt-engineering/README.md) covers what actually goes into making that reasoning step reliable.
