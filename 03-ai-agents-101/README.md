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

## Next

Before getting to the harness, step 2 — *how* the model reasons before it acts — deserves its own chapter: [Chapter 4 — Prompt Engineering](../04-prompt-engineering/README.md) covers what actually goes into making that reasoning step reliable.
