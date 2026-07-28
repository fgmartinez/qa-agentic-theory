# QA Agentic Theory

A study textbook for AI Quality Engineering. Twelve chapters, each self-contained, each ending in exercises with worked solutions and an interview-preparation section. Two chapters ship runnable, tested code — a complete harness-based backend service and a tool-calling toolkit.

**The bar this repo is built to clear:** after working through it, you should be able to sit down at an empty editor and build a full harness-based agent system — backend included — and then defend every design decision in an interview, the same way a QA engineer can explain test types, pyramids, and coverage strategy without notes.

Chapter order follows a public AI Agents learning roadmap (archived in `images/`), extended past where that roadmap stops into everything needed to evaluate, secure, and operate what gets built.

## Start here

| If you want to… | Go to |
|---|---|
| Work through it properly | **[STUDY-GUIDE.md](./STUDY-GUIDE.md)** — three paths, how to read a chapter, spaced repetition, self-assessment |
| Look up a term | **[GLOSSARY.md](./GLOSSARY.md)** — every load-bearing term, plus the confusable pairs that cause real bugs |
| Prove you learned it | **[CAPSTONE.md](./CAPSTONE.md)** — build a different system from a specification, no code provided |
| Just run something | `cd 06-implementing-and-testing-the-harness && pip install -r requirements.txt && python demo.py` |

## Chapters

| # | Chapter | Covers | Code |
|---|---|---|---|
| 1 | [LLM Fundamentals](./01-llm-fundamentals/README.md) | Tokens, context windows, generation controls, model families, reasoning models, fine-tuning vs. prompting, pricing | — |
| 2 | [RAG Fundamentals](./02-rag-fundamentals/README.md) | Chunking, embeddings, vector stores, retrieval, grounding — and the chunk-boundary failure traced end to end | — |
| 3 | [AI Agents 101](./03-ai-agents-101/README.md) | What an agent and a tool are, the four-step loop, one loop traced turn by turn, per-step failure modes | — |
| 4 | [Prompt Engineering](./04-prompt-engineering/README.md) | Specificity, context, precise terms, CoT/ToT, one prompt across four revisions, GEval criteria as prompts | — |
| 5 | [The Harness Pattern](./05-the-harness-pattern/README.md) | Why a tool call is not an action; `AUTONOMY = ACT + OBSERVE + CORRECT` | — |
| 6 | [Implementing and Testing the Harness](./06-implementing-and-testing-the-harness/README.md) | The full backend, built stage by stage: idempotency, the bounded loop, correction, decision layer, API, structured logging | **112 tests** |
| 7 | [Tool Calling and Function Schemas](./07-tool-calling-and-function-schemas/README.md) | Function schemas, the round trip, schema design, validation, error shaping, injection, MCP | **27 tests** |
| 8 | [Evaluation Metrics](./08-evaluation-metrics/README.md) | `LLMTestCase`, the metric landscape, DeepEval vs. RAGAS, GEval, four metrics scored on one bad answer | — |
| 9 | [Golden Datasets](./09-golden-datasets/README.md) | Case structure, the four case types written out, synthetic generation, mandatory review, risk levels | — |
| 10 | [Compliance Mapping](./10-compliance-mapping/README.md) | EU AI Act tiers, requirement→metric→threshold, DORA, OWASP LLM Top 10, answering an auditor with a test id | — |
| 11 | [CI/CD Quality Gates](./11-ci-cd-quality-gates/README.md) | Thresholds as config, the fast gate vs. the eval gate, the exit-code gate, block-vs-warn policy | — |
| 12 | [Observability and Telemetry](./12-observability-and-telemetry/README.md) | The four-layer stack, golden signals, one incident traced through real logs, drift, sampling | — |

Every chapter ends with **Exercises** (solutions collapsed — write your answer first) and **Interview preparation** (model answers to rehearse out loud).

## The code

Two chapters ship working software, verified rather than transcribed.

**Chapter 6 — a complete backend service.** FastAPI app, closed-enum schemas, a decision layer (deterministic rule engine + LLM engine with grounding validation), and the harness: intent-derived idempotency keys, a pure resolver, a separate corrector, and a **bounded ACT → OBSERVE → CORRECT loop** where every exit is an explicit terminal reason.

```bash
cd 06-implementing-and-testing-the-harness
pip install -r requirements.txt
python demo.py                        # tour every failure path, no server needed
python -m pytest tests/                # 112 passed in 0.65s
python -m uvicorn app.main:app         # then POST /review
```

**Chapter 7 — a tool-calling toolkit.** A registry deriving JSON Schema from type hints, rendering both OpenAI and Anthropic dialects, and a dispatcher that validates before executing and shapes errors the model can act on.

```bash
cd 07-tool-calling-and-function-schemas
python -m pytest tests/                # 27 passed in 0.11s
```

**139 tests, none of which call an LLM, all running in about a second.** That is the notebook's central technical claim made concrete: *almost everything that makes an agent safe is deterministic and can be tested deterministically.* The loop, the idempotency key, the recovery logic, the grounding check, the schema constraints, the dispatch validation — no model required. Only "was the decision *good*?" needs Chapter 8's statistical machinery, and keeping that question separate is what keeps the fast gate fast.

## Two repos, on purpose

| Repo | Role |
|---|---|
| **`qa-agentic-theory`** (this one) | Where a concept gets taught once, in full — definitions, worked examples, exercises, tested code — before it touches production code. |
| [`portfolio-risk-evaluator`](https://github.com/fgmartinez/portfolio-risk-evaluator) | Trunk project 1: a transaction risk **review** agent. 12 regulation-grounded rules as pure functions, plus RAG over a rule knowledge base so citations are retrieved rather than paraphrased. Outputs a recommendation — no execution layer, deliberately. |
| `fintech-support-ai-evaluator` | Trunk project 2: a payment-support RAG + ReAct agent (`get_payment_policy`, `check_invoice_status`, `escalate_to_human`), evaluated across five layers. |
| `clinic-ai-testing` | Reference implementation — the RAG pipeline from Chapter 2, already built and running. |

Rework in a trunk project is expensive on purpose — each is meant to grow as a coherent, interview-defensible codebase, not get rewritten every time understanding improves. This repo absorbs that churn: a topic is learned here with working, tested code, and only *then* does the corresponding piece land in a trunk project, usually as a small drop-in package plus a wiring note. See [Chapter 6's `WIRING.md`](./06-implementing-and-testing-the-harness/WIRING.md) for what that handoff looks like in practice.

## Reading paths

Chapters 1–12 read straight through as one story. Shorter routes:

- **Building an agent backend** → 5 → 6 → 7, then 8–11 for evaluation, compliance, and CI.
- **Building/extending a RAG agent** → 1 → 2 → 3 → 4, then 8–12.
- **Interview in two weeks** → see [STUDY-GUIDE.md's Path B](./STUDY-GUIDE.md#path-b--interview-in-two-weeks).

## Status

- **All 12 chapters written**, cross-linked, with exercises and interview sections throughout.
- **Chapter 6's service**: 112 tests passing, verified running under `uvicorn` — endpoints exercised with real requests, structured log output captured from a real run.
- **`portfolio-risk-evaluator` has been read** (`4a10109`) and a long-standing claim in this notebook was **corrected**: Chapter 6's harness does *not* drop into that project's `/review`. It produces a recommendation, not an action — no amount, no gateway, and a documented rule against connecting one. The harness's **executor** belongs to `fintech-support-ai-evaluator`; its **resolver** is what maps onto `portfolio-risk-evaluator` (whose `compute_risk_level()` already is one). See [`WIRING.md`](./06-implementing-and-testing-the-harness/WIRING.md). Chapter 6's schemas stay explicitly this notebook's own teaching schemas.
- **Chapter 7's toolkit**: 27 tests passing.
- Chapters 2 and 8–11 originated from pre-existing guides (`llm-agentic-eval-guide.html`, `deepeval-ragas-guide.html`, `deepeval-metrics-guide.html`, `clinic-ai-testing/TESTING_AI_SYSTEMS.md`) — ported and reorganised, then extended with worked examples and exercises.

## Roadmap — not yet written

- **LLM-as-judge selection in depth** — when a local judge (`deepseek-r1:7b`) is defensible; self-serving bias mitigation beyond Chapter 8's summary.
- **Drift detection tooling** — Arize/Fiddler, past Chapter 12's overview.
- **Agent frameworks compared** — LangGraph vs. legacy `AgentExecutor` vs. CrewAI/AutoGen.
- **Persistence and the outbox pattern** — Chapter 6 *observes* the "rail confirmed, our state didn't persist" failure but cannot yet prevent it.

## Source material

`images/` holds the two diagrams this notebook is built around: a public AI Agents roadmap (chapter ordering) and a harness/feedback-loop diagram (Chapters 5–6). Not original artwork — shared by another AI practitioner as a conceptual reference, credited inline where used, never reproduced as if original. Chapter 7 exists because that roadmap's "Tools / Actions" section was cut off in the screenshot; rather than invent what it said, that chapter covers the mechanism directly.

## For future sessions

See [`CLAUDE.md`](./CLAUDE.md) for working context — read that first, not this README, when picking the repo back up in a new conversation.
