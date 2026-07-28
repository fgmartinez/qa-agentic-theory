# Glossary

*Part of [qa-agentic-theory](./README.md).*

Every term this notebook uses in a load-bearing way, with the chapter that develops it. Written so a definition read here is enough to follow a chapter without backtracking — and so terms that are routinely confused with each other are defined *against* each other rather than separately.

## The confusable pairs

These cause more real bugs than everything else in this glossary combined. Learn them as pairs.

| | | The distinction |
|---|---|---|
| **`context`** vs. **`retrieval_context`** | Ch. 8 | `retrieval_context` is what the model **was actually shown**; `context` is **ground truth**, independent of retrieval. Faithfulness reads the first, Correctness the second. Conflating them destroys the ability to tell a retrieval bug from a generation bug. |
| **Faithfulness** vs. **Correctness** | Ch. 8 | Faithfulness: did the model stay honest to what it saw? Correctness: is the answer *true*? A faithful answer built on wrong retrieval is confidently wrong — and faithfulness will score 1.0. |
| **Context Precision** vs. **Context Recall** | Ch. 8 | Precision: was what we retrieved relevant? (noise) Recall: did we retrieve everything needed? (gaps) High recall with low precision still degrades answers. |
| **Fake** vs. **Stub** | Ch. 6 | A **fake** is a working in-process replacement used generally (the in-memory gateway `/review` runs on). A **stub** is scripted for one test (`ScriptedPaymentGatewayClient`). A fake more forgiving than production manufactures green tests for broken code. |
| **RETRY** vs. **CORRECT** | Ch. 6 | RETRY: outcome unknown (timeout) → **same** idempotency key. CORRECT: it happened but not as asked → **new** key, shortfall only. Getting them backwards double-refunds or never pays the remainder. |
| **Tool call** vs. **Action** | Ch. 5 | A tool call is a **proposal**. Nothing has happened. The gap between them is the entire subject of the harness. |
| **Query drift** vs. **Score drift** | Ch. 12 | Query drift: users ask about things the corpus never covered. Score drift: the same questions score worse. Distinguished by the question *distribution*, not the score. |

## A–Z

**Adversarial case** *(Ch. 9)* — A golden-set case whose expected output is an honest non-answer, because the corpus genuinely doesn't cover the question. Tests overconfidence. Routinely skipped, and one of only two case types that catch a system which never says "I don't know".

**Agent** *(Ch. 3)* — An LLM with tools and a **loop**. Remove the loop and what remains is a function call. The loop is what lets it act on what it observed.

**Agent loop** *(Ch. 3)* — Perceive → Reason/Plan → Act → Observe/Reflect. Each step is a distinct failure mode; conflating them is the most common agent-testing mistake. Terminates when the model declines to call a tool.

**Attempt** *(Ch. 6)* — One turn of the harness loop: the command sent, the result observed, the verdict resolved. The sequence of attempts is the audit trail.

**Attention** *(Ch. 1)* — The mechanism letting every token weigh every other token when predicting the next one. Why a model can connect "it" on page three to a noun on page one.

**Autonomy** *(Ch. 5)* — `ACT + OBSERVE + CORRECT`. Falsifiable by design: a system that acts but never observes is a script; one that observes but can't correct is a dashboard.

**Backoff** *(Ch. 6)* — A delay before a retry, growing with attempt number. Applied *between* attempts, never after the last one.

**Chain-of-Thought (CoT)** *(Ch. 4)* — Prompting the model to reason step by step before answering. Pays when there is more than one step **and the steps interact**. Costs latency and output tokens.

**Chunking** *(Ch. 2)* — Splitting documents before embedding. Chunk on the boundary that makes a fragment independently meaningful; apply size limits after. A budget decision as much as a retrieval one.

**Closed enum grounding** *(Ch. 6)* — Constraining a decision to cite one member of a fixed set, converting hallucination from a subjective judgement into a **membership test** that can fail a build.

**Confused deputy** *(Ch. 7)* — The agent has permissions the user doesn't, and a request exploits the gap. Fixed by putting authorisation *in the tool*, scoped by caller identity — never in the prompt.

**Context window** *(Ch. 1)* — Maximum tokens (input + output) a model can attend to. Exceed it and content isn't seen at all — no error, just a confident answer with a hole in it.

**Corrector** *(Ch. 6)* — Turns a `CORRECT` verdict into a concrete next command. Kept separate from the resolver: the resolver classifies, the corrector does arithmetic. Refuses (escalates) when there's no evidence to compute from.

**Correlation ID** *(Ch. 6, 12)* — An id on every log line for one request, so a sequence spanning several modules can be reassembled with one query. The prerequisite for tracing, not an enhancement to it.

**DeepEval** *(Ch. 8)* — Output-quality evaluation framework. Pytest-native, CI-friendly, extensible via GEval. Tells you *something* is wrong.

**DORA** *(Ch. 10)* — EU regulation on operational resilience. Art. 11 (graceful degradation) is the direct grounding for the harness; Art. 8 (traceability) for the attempt trail.

**Embedding** *(Ch. 2)* — A vector representing meaning rather than wording. Documents and queries **must** use the same model, or similarity scores are computable and meaningless.

**EU AI Act risk tiers** *(Ch. 10)* — Minimal / high / prohibited. Both trunk projects are **high risk**, where logging, explainability, human oversight, and robustness evaluation are mandatory rather than best practice.

**Escalation case** *(Ch. 9)* — A golden-set case that fails even if the answer is correct, because the required behaviour is *recognising it shouldn't answer*.

**ExecutionResult** *(Ch. 6)* — Evidence of what a gateway actually did. Frozen: nothing between observation and resolution may adjust it.

**Fallthrough (fail-safe)** *(Ch. 6)* — The resolver's final branch. An unrecognised signal escalates rather than defaulting to success. Load-bearing: silent success on an unknown signal is the failure mode the notebook exists to prevent.

**Few-shot** *(Ch. 4)* — Showing worked examples in the prompt rather than describing the task abstractly.

**Fine-tuning** *(Ch. 1)* — Changing weights through additional training. The second lever, never the first — reach for it only when prompting has been exhausted and a *measured* gap remains.

**Function schema** *(Ch. 7)* — The JSON Schema describing a tool's parameters. Constrains what the model may send and what you will accept. Enums here are the highest-value reliability feature available.

**GEval** *(Ch. 8)* — A custom metric defined by criteria written in plain language. The criteria string **is a prompt aimed at the judge** — vague criteria produce an unreliable judge, and therefore a threshold you can't gate on. List explicit PASS *and* FAIL cases.

**Golden set** *(Ch. 9)* — The versioned, risk-tagged, human-reviewed case collection that every metric runs against. The one artefact that cannot be validated by the test suite, which is why 100% manual review is non-negotiable.

**Grounding** *(Ch. 2, 4, 6)* — Constraining an answer to a source: retrieved context (RAG) or a closed rule set (enum). The same underlying move — remove the model's freedom to fill a gap plausibly.

**Hallucination** *(Ch. 8, 10)* — A claim not supported by the provided context. Distinct from a *retrieval failure*, where the model was never shown the fact and answered faithfully from what it had.

**Harness** *(Ch. 5, 6)* — The layer between a proposed decision and the systems it affects. Executes, observes, resolves, and loops. The only component holding a client to the outside world.

**Idempotency key** *(Ch. 6)* — Derived from **logical intent** (case + amount), deliberately excluding the attempt number, so retries dedupe. Format to fixed precision before hashing, or float noise mints a second refund.

**LLMTestCase** *(Ch. 8)* — DeepEval's fixture holding one interaction: input, actual output, expected output, context, retrieval context, tools called.

**MCP (Model Context Protocol)** *(Ch. 7)* — An open protocol exposing tools, resources, and prompts to any model client, turning M×N integrations into M+N. Standardises transport and discovery, **not trust** — an MCP tool is exactly as untrusted as a local one.

**Multi-hop case** *(Ch. 9)* — A case needing more than one tool in a specific **order**. Catches the expensive bug where wrong order produces a plausible, policy-accurate, wrong answer.

**Observability** *(Ch. 12)* — Four layers: structured logging → tracing → metrics → dashboards/alerting. Build in that order; each derives from the one before.

**Parallel vs. sequential tool calls** *(Ch. 7)* — Parallel when calls are independent (one round trip); sequential when a later call needs an earlier **result**. You can't force independence that doesn't exist, but you can accidentally destroy independence that does.

**Property test** *(Ch. 6)* — Asserting an invariant across the whole input space rather than enumerating rows. Keeps holding when someone adds an enum member and forgets the table.

**Protocol** *(Ch. 6, 7)* — A structural interface. Lets the harness accept a fake, a stub, or a real payment rail with no caller changes.

**RAG** *(Ch. 2)* — Retrieval-augmented generation. Chunk → embed → store → retrieve → ground → generate. Retrieval and generation fail independently and must be measured separately.

**RAGAS** *(Ch. 8)* — Pipeline evaluation framework separating retrieval quality from generation quality. Tells you *where* the problem is, after DeepEval tells you *that* there is one.

**Registry (tool)** *(Ch. 7)* — Holds the tools an agent may call, and is therefore the **authorisation boundary**: an unregistered callable cannot be reached whatever the model emits. A structural guarantee, not a behavioural one.

**Resolver** *(Ch. 6)* — Pure function mapping one observation to one verdict. No I/O, no clock, no model — so it can be tested exhaustively and stays predictable when the model isn't.

**Risk level** *(Ch. 9, 11)* — `low`/`medium`/`high`/`critical` on every golden case. Lets the CI gate block on a critical failure regardless of aggregate pass rate.

**RuleId** *(Ch. 6)* — The closed set a decision must cite. No `other` member and no free-text fallback, on purpose.

**Streaming** *(Ch. 1)* — Returning tokens as generated. A UX choice, not an evaluation choice — metrics run against the complete response.

**Temperature** *(Ch. 1)* — Randomness in next-token choice. `0.0` for judges, extraction, and decisions; higher only when variety is the goal rather than a tolerated side effect.

**TerminalReason** *(Ch. 6)* — *Why* the loop stopped, distinct from *what* the last action was. Separates gateway refusal from budget exhaustion from an uncorrectable gap — three very different on-call responses.

**Threshold** *(Ch. 8, 11)* — The pass bar for a metric, set from the **cost of being wrong**. Never 1.0 on anything judge-scored: it fails on variance, and a gate people learn to bypass is worse than a looser one they respect.

**Token** *(Ch. 1)* — ~3–4 characters of English. Simultaneously the unit of computation, pricing, and the context limit.

**Tool** *(Ch. 3, 7)* — A name, a description, a JSON Schema, and a callable. The model sees the first three and emits a request; it never executes anything.

**Tool description** *(Ch. 7)* — Prompt text, not documentation. Pattern: what / when with examples / when **not** and which sibling tool instead / constraints. Write descriptions as a *set* — the question is whether it distinguishes the tool, not whether it describes it.

**ToolCorrectnessMetric** *(Ch. 3, 8)* — Measures whether the right tool was called with the right parameters. Says nothing about whether the call was valid, executed, or recovered — the gap the harness fills.

**Tree-of-Thought (ToT)** *(Ch. 4)* — Exploring multiple reasoning paths with backtracking. Steeper cost than CoT; neither trunk project has needed it.

**Vector store** *(Ch. 2)* — Where embeddings live for similarity search. Chroma by default (persistence, metadata filtering); FAISS when scale genuinely outgrows one machine.

**Walking skeleton** *(Ch. 5, 6)* — A thin end-to-end implementation built against real interfaces with fakes behind them. Replaced by writing a new class satisfying the same Protocol, not by restructuring.
