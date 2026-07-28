# Chapter 8 — Evaluation Metrics: DeepEval & RAGAS

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 7 — Tool Calling and Function Schemas](../07-tool-calling-and-function-schemas/README.md). Next: [Chapter 9 — Golden Datasets](../09-golden-datasets/README.md). Feeds: the evaluation suites in `fintech-support-ai-evaluator` and `clinic-ai-testing`.*

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
| 5 | Compliance Safety | `FinancialAccuracy` (GEval), `SensitiveDataProtection` (GEval), Bias | FinancialAccuracy ≥ 0.90, SensitiveData = 1.0 | EU AI Act / DORA — Chapter 10 |

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

## Worked example: four metrics on one bad answer

Metrics are easier to reason about when you score the same interaction with all of them and watch them disagree.

**Question:** *"Can I get a refund on invoice INV-1002?"*

**Ground truth (`context`):** *Refunds are available within 180 days. INV-1002 was charged 200 days ago and is therefore not eligible.*

**What retrieval actually returned (`retrieval_context`):** *"Refunds are processed within 5 business days."*

**System answer:** *"Yes — refunds are processed within 5 business days, so you should see it shortly."*

| Metric | Score | Why |
|---|---|---|
| Faithfulness | **1.0 — passes** | Every claim is supported by what the model was shown. |
| Answer Relevancy | **~0.9 — passes** | It is about refunds on the invoice asked about. |
| Context Recall | **0.0 — fails** | The eligibility rule was never retrieved. |
| Answer Correctness | **0.0 — fails** | Against ground truth, the answer is the opposite of true. |

**Three of the four numbers look fine or irrelevant, and the system told a customer they'd get a refund they are not entitled to.**

This is the single most important thing to internalise about LLM evaluation:

> **Faithfulness passing is not evidence the answer is right.** It only means the model didn't invent anything *beyond what it was given*. If retrieval hands it the wrong context, a perfectly faithful answer is a confidently wrong one — and the metric most people lead with will report success.

It also shows why `context` and `retrieval_context` must not be conflated. Faithfulness reads `retrieval_context` ("given what it saw, did it stay honest?"). Correctness reads `context` ("is this actually true?"). Point both at the same field and you lose the ability to distinguish a retrieval bug from a generation bug — which is the entire diagnostic value of the suite.

## Exercises

### 1 — Read the metric combination

For each pattern, name the failing layer and the next debugging step:

(a) Faithfulness 0.95, Context Recall 0.45
(b) Faithfulness 0.55, Context Precision 0.92, Context Recall 0.90
(c) Context Recall 0.95, Context Precision 0.40, Faithfulness 0.70
(d) Tool Correctness 1.0, Task Completion 0.50

<details><summary>Solution</summary>

(a) **Retrieval — recall.** The generator faithfully used what it got; not enough was fetched. Debug chunking and `k`, not the prompt. (This is Chapter 2's boundary-split failure.)
(b) **Generation.** Retrieval did its job — precision and recall both high — and the model still drifted from the context. Debug the prompt's grounding instruction, or the generator model's capability.
(c) **Retrieval — precision.** Everything needed was found, buried in noise, and the noise diluted the answer. Lower `k` or improve ranking. Note faithfulness dropped *as a consequence* of precision, which is why fixing faithfulness directly would fail.
(d) **Neither retrieval nor grounding.** The agent called exactly the right tools and still didn't accomplish the user's goal — a strategy/orchestration problem. Classic cause: it stopped after step one of a two-step task. Correctness measures the moves; completion measures the outcome.

The habit worth building: **never debug from one metric.** Each of these four diagnoses is invisible from any single number in it.
</details>

### 2 — Set a threshold and defend it

Pick a threshold for Faithfulness in (a) a recipe chatbot, (b) a payment-policy support agent, (c) a medication-information assistant. Justify each, then say what happens at 1.0.

<details><summary>Solution</summary>

(a) **~0.75.** A slightly embellished recipe is a poor experience, not a harm. A tight threshold here buys little and blocks releases.
(b) **≥ 0.90.** Inventing financial policy has direct monetary and regulatory consequence. This is the notebook's default for the FinTech projects.
(c) **≥ 0.95, plus a separate safety metric.** Utility and safety are different axes — an answer can be accurate and still unsafe by omitting "consult your doctor". Faithfulness will not catch that; a dedicated GEval criterion will.

**At 1.0:** the gate becomes unusable. Judge scoring has inherent variance, so a 1.0 threshold fails on judge noise rather than on regressions, and the team learns to bypass the gate — which is worse than a looser threshold that is actually respected. Reserve 1.0 for genuinely binary, deterministically-checkable things: tool *sequence* on a critical flow, or `SensitiveDataProtection` where any leak is a failure.
</details>

### 3 — Fix a criteria string

```python
GEval(name="Quality", criteria="Check if the answer is good and accurate.")
```

Name three defects and rewrite it for the payment-support domain.

<details><summary>Solution</summary>

**Defects:** (1) "good" is undefined — the judge invents its own rubric, differently each run; (2) no PASS/FAIL conditions, so scores are unanchored and cluster near the middle; (3) no `evaluation_params`, so it isn't stated which fields the judge should even read.

```python
GEval(
    name="PolicyGrounding",
    model=judge,
    criteria="""
    Determine whether every factual claim about payment policy in the
    ANSWER is supported by the CONTEXT.

    FAIL if the answer states a timeline, fee, percentage, or eligibility
    condition that does not appear in the context.
    FAIL if it names a process, form, or department not in the context.
    PASS if every policy claim traces to the context.
    PASS if the answer states plainly that the context does not cover the
    question.
    """,
    evaluation_params=["input", "actual_output", "context"],
    threshold=0.90,
)
```

Explicit PASS cases matter as much as FAIL cases — listing only failures biases the judge toward failing, because it has no positive anchor. For maximum reproducibility, supply `evaluation_steps` explicitly rather than letting the judge infer them from prose.
</details>

### 4 — Decide what does *not* need a judge

Of these, which need an LLM judge and which can be plain assertions? (a) the answer cites a real `RuleId`; (b) the answer is faithful to context; (c) no card number appears in the output; (d) the right tool was called; (e) the tone is appropriately empathetic.

<details><summary>Solution</summary>

**Plain assertions:** (a) membership test against the enum — Chapter 6 does exactly this; (c) regex/Luhn check, and a *far* more reliable leak detector than asking a judge; (d) set/sequence comparison against expected tools.

**Needs a judge:** (b) faithfulness requires reading meaning across two texts; (e) tone is irreducibly subjective.

The lesson generalises: **push everything you can down to a deterministic check.** Judge-based metrics are slower, cost tokens, vary run to run, and are themselves fallible. Every check you can express as an assertion is one fewer source of CI flake. People reach for a judge on (a), (c) and (d) far more often than they should.
</details>

## Interview preparation

**"Why can't you just use assertions?"**

> Because the correct output isn't a single string. "Refunds take 5 business days" and "You'll see it within a week" are both right, and `assertEqual` fails one of them. So instead of exact matching you score properties — is it grounded in the context, does it answer the question, did it invent anything — and gate on thresholds. That said, I push everything I can *back* to assertions: whether the cited rule id is in the enum, whether a card number appears, whether the right tool was called. Those are deterministic, and a judge on them is strictly worse.

**"What's the difference between `context` and `retrieval_context`?"**

> `retrieval_context` is what the model was actually shown; `context` is ground truth independent of retrieval. Faithfulness reads the first — given what it saw, did it stay honest. Correctness reads the second — is this actually true. Conflating them is the most common setup error, and it destroys the diagnostic: you lose the ability to tell a retrieval bug from a generation bug. I've seen an answer score 1.0 faithfulness and 0.0 correctness because retrieval returned the wrong policy — the model was perfectly honest about the wrong thing.

**"DeepEval or RAGAS?"**

> Both, for different questions. DeepEval tells me *something* is wrong — it's output-quality focused, pytest-native, CI-friendly, and extensible with GEval for domain rules. RAGAS tells me *where*, because it separates retrieval quality from generation quality. The workflow is: DeepEval's faithfulness fails, then I look at RAGAS's context precision and recall to decide whether to fix the retriever or the prompt. Running only one leaves you guessing which layer to debug.

**"How do you choose a threshold?"**

> From the cost of being wrong, not from what the system currently scores. Inventing financial policy is a monetary and regulatory problem, so faithfulness sits at 0.90 there where a recipe bot would be fine at 0.75. And I avoid 1.0 on anything judge-scored — judge variance means it fails on noise rather than regressions, and a gate people learn to bypass is worse than a slightly looser one they respect. I reserve 1.0 for deterministic checks: tool sequence on a critical flow, or any-leak-is-a-failure cases.

**"Give me a failure a single metric would miss."**

> Retrieval returns the wrong policy — "refunds process in 5 business days" — for a question about *eligibility*, where the invoice is 200 days old and not eligible. The answer says "yes, you'll see it shortly". Faithfulness passes at 1.0, because every claim is supported by what the model was shown. Relevancy passes. Only context recall and correctness fail. So the metric most people lead with reports success while the system has promised a customer a refund they're not entitled to. That's why I run a layered suite rather than a headline number.

## Next

Every metric in this chapter is only as good as the test cases it runs against. [Chapter 9 — Golden Datasets & Synthetic Data](../09-golden-datasets/README.md) covers where those cases actually come from.
