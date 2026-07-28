# Chapter 7 — Evaluation Metrics: DeepEval & RAGAS

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 6 — Implementing and Testing the Harness](../06-implementing-and-testing-the-harness/README.md). Next: [Chapter 8 — Golden Datasets](../08-golden-datasets/README.md). Feeds: the evaluation suites in `fintech-support-ai-evaluator` and `clinic-ai-testing`.*

## Why traditional assertions don't work here

Traditional testing is deterministic: same input, same output, one assertion, pass or fail. Ask an LLM the same question ten times and the phrasing varies every time — all correct, all different strings. `assertEquals` has nothing to grab onto.

> **QA bridge.** Testing a REST API is asserting on a fixed JSON shape. Testing an LLM answer is closer to testing a customer-service chatbot: the answer can be phrased ten different correct ways. You need qualitative evaluation, not structural comparison.

Two families of metric exist to handle this:

- **Traditional NLP metrics** (BLEU, ROUGE) — compare generated text to a reference using n-gram overlap. Fast, cheap, reproducible, but purely lexical: *"the cat sat on the mat"* vs. *"a feline rested on the rug"* scores badly despite meaning the same thing.
- **LLM-as-a-Judge** — a second LLM reads the input, the output, and the context, and scores quality on a dimension (faithfulness, relevance, correctness). This is what DeepEval and RAGAS both build on, and it's the dominant paradigm because it captures meaning, not just wording.

> **Watch out — self-serving bias.** Using the same model as both generator and judge means the judge tends to rate its own outputs more favorably. Acceptable for learning with a local model; in production, use a stronger or different model as the judge.

## The core object: `LLMTestCase`

Everything in DeepEval revolves around `LLMTestCase` — the fixture that holds what's needed to evaluate one interaction.

| Field | Meaning |
|---|---|
| `input` | The user's question or prompt. Always required. |
| `actual_output` | What the system actually returned. Always required. |
| `expected_output` | The ideal/reference answer, for comparison metrics. |
| `context` | Ground-truth information, for hallucination checks. |
| `retrieval_context` | What the retriever *actually* returned for this query — may be right, partially right, or wrong. |
| `tools_called` / `expected_tools` | For agent metrics: what was actually invoked vs. what should have been. |

> **The #1 conceptual confusion.** `context` and `retrieval_context` are not the same thing, and mixing them up means a metric measures the wrong thing. `retrieval_context` is what the LLM was actually shown — faithfulness metrics use this, because the question is "given what it saw, did it stay faithful to that?" `context` is the ground truth independent of what was retrieved — correctness metrics use this, because the question is "is the answer factually right, period?" A faithful answer built on bad retrieval can still be a wrong answer.

## The metric landscape

| Metric | Framework | Measures | Failure mode it catches |
|---|---|---|---|
| Faithfulness | Both | Is the answer grounded in the retrieved context? | Hallucination |
| Answer Relevancy | Both | Does the answer address the question asked? | Wrong abstraction / off-topic |
| Context Precision | RAGAS | Are the retrieved chunks actually relevant? | Bad retrieval (noise) |
| Context Recall | RAGAS | Did retrieval find *everything* needed? | Missing knowledge |
| Answer Correctness | RAGAS | Factually + semantically correct vs. ground truth | Any of the above |
| Tool Correctness | DeepEval | Right tool, right parameters | Wrong action (Chapter 3) |
| Hallucination | DeepEval | Fabricated claims not in context (lower is better) | Hallucination |
| GEval (custom) | DeepEval | Any criteria written in plain language | Domain-specific rules |
| Bias | DeepEval | Systematic bias in output | Fairness |

## DeepEval vs. RAGAS — the actual decision

They're complementary, not competing:

- **DeepEval** evaluates *output quality*: faithful, relevant, hallucination-free, unbiased. Pytest-style, CI/CD-native, extensible via `GEval` for custom criteria, and the same framework covers agent metrics (`ToolCorrectnessMetric`).
- **RAGAS** evaluates the *pipeline*: it's built specifically to separate retrieval quality from generation quality, which is exactly the diagnostic DeepEval's output-only metrics can't give you.

**Use both, in this order when a test fails:** DeepEval tells you *something's* wrong (e.g. low Faithfulness). RAGAS tells you *where*: was Context Precision low (retriever returned noise)? Was Context Recall high but Faithfulness still low (retriever found the right info, generator ignored it)? That diagnostic split is the entire value of running both.

```python
# The diagnostic combination the recall/precision rules point to
if faithfulness_low and context_precision_high:
    # generation layer problem — the model had good context and
    # still didn't use it faithfully
    diagnose_generation()
elif context_recall_low and faithfulness_high:
    # retrieval layer problem — what was retrieved was used
    # faithfully, but not enough was retrieved
    diagnose_retrieval()
```

## GEval — custom criteria in plain language

Standard metrics don't cover every domain rule. `GEval` lets you write the criteria as instructions and DeepEval turns them into a scored check — useful exactly where the rule is specific to the business, not a general LLM-quality concern.

```python
financial_accuracy_metric = GEval(
    name="FinancialAccuracy",
    model=judge,
    criteria="""
    Evaluate whether the response contains incorrect or invented
    financial information. It FAILS if it states amounts,
    percentages, or dates not present in the context, or invents
    a process, form name, or department. It PASSES if every
    factual claim is backed by the context, and the system says
    so plainly when it doesn't know.
    """,
    evaluation_params=["input", "actual_output", "context"],
    threshold=0.90,  # high — financial information is unforgiving
)
```

GEval trades determinism for flexibility — for maximum reproducibility, supply explicit `evaluation_steps` instead of letting it infer them from the criteria text.

## A layered view that actually catches failures

A single metric never tells the whole story. The combination that does:

1. **Retrieval** — Context Precision + Context Recall + Context Relevance
2. **Generation** — Faithfulness + Answer Relevancy
3. **Agentic behavior** — Tool Correctness + Task Completion + Hallucination
4. **Safety / policy** — Bias + domain-specific GEval

Four rules worth internalizing, because each is a place a single-metric view lies to you:

- **Faithfulness without Recall isn't enough.** An answer can be fully faithful to what it retrieved and still be wrong, if the retriever missed something. Faithfulness alone doesn't catch that.
- **Recall without Precision isn't enough either.** Retrieving everything relevant, plus a lot of noise, degrades the answer even though nothing needed was missed.
- **Tool Correctness without Task Completion isn't enough.** The agent can call the exactly right tool and still fail to complete the user's actual goal — correctness measures the strategy, completion measures the outcome.
- **Safety is separate from utility.** A response can be genuinely useful and still unsafe — helpful medication information that omits "consult your doctor" is a safety failure a general quality metric won't flag.

## Applied: a five-layer suite for `fintech-support-ai-evaluator`

| # | Layer | Metrics | Threshold | Why |
|---|---|---|---|---|
| 1 | RAG Retrieval | Context Precision, Context Recall, Noise Sensitivity | ≥ 0.80 | Payment policy answers can't tolerate wrong context |
| 2 | RAG Generation | Faithfulness, Answer Relevancy, Hallucination | Faithfulness ≥ 0.90, Hallucination ≤ 0.15 | Financial information needs high fidelity to source |
| 3 | Agent Tool Routing | Tool Call Accuracy, Tool Call F1 | = 1.0 on critical flows | Tool *order* matters in payment flows |
| 4 | Agent Output Quality | Agent Goal Accuracy, Answer Relevancy | ≥ 0.90 | Task has to actually complete, not just look plausible |
| 5 | Compliance Safety | `FinancialAccuracy` (GEval), `SensitiveDataProtection` (GEval), Bias | FinancialAccuracy ≥ 0.90, SensitiveData = 1.0 | EU AI Act / DORA — Chapter 9 |

Thresholds live in one config file, not scattered across test files, with the reasoning for each documented next to the number:

```yaml
# config/thresholds.yaml
rag_layer:
  faithfulness:
    threshold: 0.90
    rationale: "Zero tolerance for inventing financial policy"
  context_recall:
    threshold: 0.80
    rationale: "Must ensure full coverage of relevant policy"
agent_layer:
  tool_call_accuracy:
    threshold: 1.0
    rationale: "Tool order matters in regulated payment flows (DORA)"
```

## Next

Every metric in this chapter is only as good as the test cases it runs against. [Chapter 8 — Golden Datasets & Synthetic Data](../08-golden-datasets/README.md) covers where those cases actually come from.
