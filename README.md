# QA Agentic Theory

A theory notebook for AI Quality Engineering. Every concept gets explained, worked through with examples, and prototyped in code here — in full — before it lands in a practical project. Chapter order follows a public AI Agents learning roadmap end to end (archived in `images/`); structure and pacing modeled on [DataTalksClub/llm-zoomcamp](https://github.com/DataTalksClub/llm-zoomcamp): numbered chapter folders, each self-contained, each ending in something concrete.

## Two repos, on purpose

| Repo | Role |
|---|---|
| **`qa-agentic-theory`** (this one) | Where a concept gets taught once, in full — definitions, diagrams, worked examples, tested code — before it touches production code. |
| [`portfolio-risk-evaluator`](https://github.com/fgmartinez/portfolio-risk-evaluator) | Trunk project 1: a transaction dispute / risk review agent, walking-skeleton architecture. No RAG — rule-grounded decisions (closed `RuleId` enum) executed through a harness. |
| `fintech-support-ai-evaluator` | Trunk project 2: a payment-support RAG + ReAct agent (`get_payment_policy`, `check_invoice_status`, `escalate_to_human`), evaluated across five layers. |
| `clinic-ai-testing` | Reference implementation — the RAG pipeline described in Chapter 2 already built and running. |

Rework in a trunk project is expensive on purpose — each one is meant to grow as a coherent, interview-defensible codebase, not get rewritten every time understanding improves. This repo absorbs that churn instead: a topic is learned and explained here, with working, tested code, and only *then* does the corresponding piece land in a trunk project — usually as a small drop-in package plus a short wiring note, so a trunk project's commit history stays clean and every commit there represents a settled decision, not a draft.

## Chapters

Numbered in the order a public AI Agents roadmap lays the topic out: prerequisites → LLM fundamentals → RAG → agents 101 → prompt engineering → tools/actions, extended past where that roadmap stops into everything needed to evaluate, secure, and operate what gets built.

| # | Chapter | Covers | Feeds |
|---|---|---|---|
| 1 | [`01-llm-fundamentals`](./01-llm-fundamentals/README.md) | Tokenization, context windows, generation controls, open vs. closed weight models, reasoning vs. standard models, fine-tuning vs. prompting, streaming, pricing. | Foundation for every later chapter |
| 2 | [`02-rag-fundamentals`](./02-rag-fundamentals/README.md) | What/why RAG, chunking, embeddings, vector stores (ChromaDB vs. FAISS), generator/embedder model selection. | `fintech-support-ai-evaluator`, `clinic-ai-testing` |
| 3 | [`03-ai-agents-101`](./03-ai-agents-101/README.md) | What is an agent, what is a tool, the four-step agent loop (perceive → reason/plan → act → observe/reflect) and its per-step failure modes. | Vocabulary for 4–11 |
| 4 | [`04-prompt-engineering`](./04-prompt-engineering/README.md) | Writing prompts that hold up, Chain-of-Thought, Tree-of-Thought, GEval criteria as prompts aimed at a judge. | Both trunk projects' system prompts |
| 5 | [`05-the-harness-pattern`](./05-the-harness-pattern/README.md) | The harness: executes a decision against real systems, observes what happened, decides what's next. The autonomy formula. | `portfolio-risk-evaluator` `/review` |
| 6 | [`06-implementing-and-testing-the-harness`](./06-implementing-and-testing-the-harness/README.md) | Full implementation + pytest suite — 8/8 passing, run and verified. Ready to drop in. | `portfolio-risk-evaluator` |
| 7 | [`07-evaluation-metrics`](./07-evaluation-metrics/README.md) | `LLMTestCase`, the metric landscape, DeepEval vs. RAGAS decision framework, GEval, the layered evaluation view. | Both trunk projects' eval suites |
| 8 | [`08-golden-datasets`](./08-golden-datasets/README.md) | Golden set structure, the four case types (direct/multi-hop/adversarial/escalation), synthetic generation + mandatory review. | Both trunk projects' test oracles |
| 9 | [`09-compliance-mapping`](./09-compliance-mapping/README.md) | EU AI Act risk tiers, requirement→metric→threshold mapping, DORA, OWASP LLM Top 10, prompt-injection defense. | Layer 5 of the eval suite, both projects |
| 10 | [`10-ci-cd-quality-gates`](./10-ci-cd-quality-gates/README.md) | `thresholds.yaml`, pytest wiring, GitHub Actions pipeline, the exit-code gate. | CI for both trunk projects |
| 11 | [`11-observability-and-telemetry`](./11-observability-and-telemetry/README.md) | The four-layer stack (logging → tracing → metrics → dashboard/alerting), golden signals, incident response, drift. | Production readiness for both |

Status: all 11 chapters complete. Chapter 6's code is written and unit-tested (8/8 passing) but not yet wired into `portfolio-risk-evaluator`'s real endpoint — see that chapter's "What's still open" section.

## Reading paths

Chapters 1–11 read straight through as one coherent story (see each chapter's Previous/Next links). Two shorter paths, if only one trunk project is active right now:

- **Building/extending the harness** (`portfolio-risk-evaluator`): 1 → 3 → 4 → 5 → 6, then 7–10 for evaluation/compliance/CI.
- **Building/extending the RAG agent** (`fintech-support-ai-evaluator`, `clinic-ai-testing`): 1 → 2 → 3 → 4, then 7–11 for evaluation/compliance/CI/observability.

Chapters 7–10 (evaluation, golden datasets, compliance, CI/CD) and Chapter 11 (observability) apply identically to both trunk projects regardless of which path got there first.

## Roadmap — not yet written

New chapters get added as new topics come up, same pattern every time: theory here first, trunk project second.

- **LLM-as-judge selection in depth** — when a local judge (`deepseek-r1:7b`) is defensible vs. when it isn't; self-serving bias mitigation beyond the one-paragraph version in Chapter 7.
- **Drift detection tooling** — Arize/Fiddler in more depth than Chapter 11's one-paragraph mention.
- **Agent frameworks compared** — LangGraph vs. legacy `AgentExecutor` vs. CrewAI/AutoGen, and why LangGraph is the market-relevant default going forward.
- **Tool-calling mechanics in depth** — function-calling schemas, MCP, parallel vs. sequential tool calls. (The source roadmap image has a "Tools / Actions" section past where its screenshot was cut off — this notebook currently covers tools only through Chapter 3's definition and Chapters 5–6's execution layer, not the calling-convention mechanics themselves.)

## How to read a chapter

Every chapter folder stands on its own — open its `README.md` and it's self-contained enough to understand and apply what it covers without another chapter open at the same time. That said, chapters build on each other in reading-path order: Chapter 6 assumes Chapter 5's architecture, Chapter 10 assumes Chapter 7's thresholds exist. Reading in path order is the intended experience even though nothing forces it.

Where a chapter ships code, the code lives in that chapter's own folder and is runnable on its own:

```bash
cd 06-implementing-and-testing-the-harness
python3 -m pytest tests/ -v
```

## Source material

`images/` holds the two diagrams this notebook is built around: a public AI Agents roadmap (chapter ordering) and a harness/feedback-loop diagram (Chapters 5–6). Not original artwork — shared by another AI practitioner as a conceptual reference, credited inline where used, never reproduced as if original.

## Related

- [`llm-agentic-eval-guide`](https://github.com/fgmartinez) — the original single-document version of most of Chapters 2 and 7–10's material, plus interview Q&A depth this notebook doesn't try to duplicate. This repo is that material restructured into a navigable, chaptered, GitHub-native notebook, tied explicitly to the two trunk projects and reordered to follow a proper learning sequence — not a replacement for it, a reorganization of it.

## For future sessions

See [`CLAUDE.md`](./CLAUDE.md) for full project context — read that first, not this README, when picking this repo back up in a new conversation.
