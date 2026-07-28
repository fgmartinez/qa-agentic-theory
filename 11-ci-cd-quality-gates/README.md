# Chapter 11 — CI/CD Quality Gates for AI Systems

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 10 — Compliance Mapping](../10-compliance-mapping/README.md). Next: [Chapter 12 — Observability & Telemetry](../12-observability-and-telemetry/README.md). This closes the loop back to [Chapter 6](../06-implementing-and-testing-the-harness/README.md)'s pytest suite and [Chapter 8](../08-evaluation-metrics/README.md)'s thresholds.*

Everything in Chapters 8–10 (Evaluation Metrics, Golden Datasets, Compliance Mapping) is only a quality *bar* until something actually enforces it on every change. This chapter is that enforcement: the same "exit 1 blocks the merge" pattern already familiar from Cypress-in-Jenkins, applied to LLM quality instead of UI behavior.

## Thresholds as config, not scattered constants

Every threshold from Chapter 8 lives in one file, with the reasoning next to the number — not as a magic literal buried in a test file six months later with no memory of why `0.90` and not `0.85`.

```yaml
# config/thresholds.yaml
version: "1.0"
risk_level: "high"   # from Chapter 10's EU AI Act tier

rag_layer:
  context_precision:
    threshold: 0.80
    rationale: "Reduce noise in answers about regulated policy"
  context_recall:
    threshold: 0.80
    rationale: "Ensure full coverage of relevant policy"
  faithfulness:
    threshold: 0.90
    rationale: "Zero tolerance for inventing financial policy"
  hallucination:
    threshold: 0.15   # lower is better for this one
    rationale: "High restriction — risk of incorrect financial advice"

agent_layer:
  tool_call_accuracy:
    threshold: 1.0
    rationale: "Tool order matters in payment flows (DORA)"
  agent_goal_accuracy:
    threshold: 0.90
    rationale: "Minimal tolerance for incomplete AR tasks"

compliance_layer:
  financial_advice_hallucination:
    threshold: 0.05
    rationale: "EU AI Act Art. 13 — transparency, no deception"
  sensitive_data_exposure:
    threshold: 0.0    # absolute zero tolerance
    rationale: "DORA + GDPR — customer and invoice data"
```

## Wiring thresholds into pytest

```python
import pytest, yaml
from deepeval import assert_test
from deepeval.metrics import ContextualPrecisionMetric, FaithfulnessMetric

with open("config/thresholds.yaml") as f:
    THRESHOLDS = yaml.safe_load(f)["rag_layer"]

@pytest.fixture(scope="module")
def golden_set():
    import json
    with open("data/golden_set.json") as f:
        return json.load(f)["cases"]

@pytest.mark.parametrize("case_id", ["GS-001", "GS-002", "GS-003"])
def test_faithfulness(case_id, rag_system, golden_set):
    """Every case checked against the threshold from config —
    not a hardcoded number duplicated across test files."""
    case = next(c for c in golden_set if c["id"] == case_id)
    answer, contexts = rag_system(case["input"])
    test_case = LLMTestCase(
        input=case["input"], actual_output=answer,
        expected_output=case["expected_output"], retrieval_context=contexts,
    )
    metric = FaithfulnessMetric(threshold=THRESHOLDS["faithfulness"]["threshold"])
    assert_test(test_case, [metric])
```

## The pipeline

```yaml
# .github/workflows/eval-ci.yml
name: AI Evaluation Pipeline
on:
  push: { branches: [main, develop] }
  pull_request: { branches: [main] }

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt

      # In CI: a cloud judge model (no Ollama container to manage).
      # Locally: a local judge (deepseek-r1:7b) — no API cost.
      # Same test code, different judge injected via config.
      - name: Configure evaluation model
        env: { OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }} }
        run: deepeval login --confident-api-key ${{ secrets.DEEPEVAL_API_KEY }}

      - name: Run RAG evaluation suite
        run: python -m pytest tests/test_rag_eval.py -v --json-report --json-report-file=eval-results.json

      - name: Run agent evaluation suite
        run: python -m pytest tests/test_agent_eval.py -v

      - uses: actions/upload-artifact@v3
        if: always()   # keep the report even when tests fail — that's when you need it most
        with: { name: eval-results, path: eval-results.json }

      - name: Check evaluation gate
        run: python scripts/check_eval_gate.py eval-results.json
```

```python
# scripts/evaluate.py — the exit code IS the CI signal
from src.eval.runner import run_full_evaluation

report = run_full_evaluation()
if report.pass_rate < 0.8:
    print(f"FAILED: pass rate {report.pass_rate:.0%} below 80% threshold.")
    exit(1)   # Jenkins/GitHub Actions reads this as a failed build
else:
    print("PASSED: all quality gates met.")
    exit(0)
```

> **Same pattern as `npx cypress run` in Jenkins.** A deterministic UI test suite and a probabilistic LLM evaluation suite plug into CI/CD identically: run, produce a pass rate, exit non-zero on failure, block the merge. The only thing that changed is what's inside the box being tested — the gate mechanics are the same discipline already known from Cypress.

## The four categories a full run actually covers

| # | Category | Source | Metric |
|---|---|---|---|
| 1 | Golden dataset | Chapter 9's authored cases | Faithfulness + Answer Relevancy |
| 2 | Hallucination probes | Adversarial cases designed to trigger fabrication | Hallucination |
| 3 | Adversarial prompts | Chapter 10's injection/role-manipulation set | Injection Resistance (GEval) |
| 4 | RAGAS pipeline | Full retrieval + generation sweep | Context Precision/Recall, Faithfulness, Answer Correctness |

Running all four on every push — not just the golden dataset — is what keeps a regression in retrieval (Chapter 2) or a new prompt-injection vector (Chapter 10) from silently landing on `main` between milestones.

## Where this closes the loop

This is the last chapter of the current notebook, and it lands back on the two things every earlier chapter built toward:

- The **harness resolver** (Chapter 6) is pure and deterministic specifically *so* it can be a normal, fast pytest suite in this pipeline — no judge model, no flakiness, runs in milliseconds on every push.
- The **five-layer evaluation suite** (Chapter 8), **golden set** (Chapter 9), and **compliance mapping** (Chapter 10) are what `scripts/evaluate.py` actually runs — this chapter is the delivery mechanism, not a separate topic.

## Worked example: two suites, two speeds

The mistake that makes an AI quality gate unusable is running everything as one job. Deterministic tests take a second and never flake; judge-scored tests take minutes, cost tokens, and vary. Putting them in the same stage means the fast signal arrives at the speed of the slow one — and the whole thing gets bypassed.

```yaml
jobs:
  fast-gate:                       # every push, every branch
    steps:
      - run: pytest tests/          # Ch.6 harness  (112 tests, 0.65s)
      - run: pytest tests/          # Ch.7 toolkit  (27 tests, 0.11s)
      - run: python scripts/check_rule_catalogue.py

  eval-gate:                       # PRs to main only
    needs: fast-gate               # don't spend tokens if the cheap gate failed
    steps:
      - run: pytest tests/test_rag_eval.py --json-report
      - run: pytest tests/test_agent_eval.py
      - run: python scripts/check_eval_gate.py eval-results.json
```

| | Fast gate | Eval gate |
|---|---|---|
| Runs | Every push | PRs to `main` |
| Duration | ~1 second | Minutes |
| Cost | Zero | Judge tokens |
| Flake risk | None | Real |
| Blocks on | Any failure | Threshold breach |
| Content | Resolver, loop, idempotency, schemas, dispatch, grounding | Faithfulness, recall, tool correctness, injection resistance |

Two properties worth stating explicitly:

1. **`needs: fast-gate` is a cost control.** If the resolver is broken, spending judge tokens to discover the answers are also bad is pure waste. Order stages by cost.
2. **Most of what makes the system safe is in the *fast* gate.** The harness loop, idempotency, closed-enum grounding, tool dispatch validation — 139 tests, no model, about a second. That is the reusable insight from Chapters 6 and 7: agent safety is mostly deterministic, so most of it can gate every single push rather than only PRs.

### The gate script is where judgement lives

`exit 1` is the mechanism; *deciding when to exit 1* is the design:

```python
report = run_full_evaluation()

# A flat pass rate hides the difference that matters (Chapter 9's risk_level).
critical_failures = [r for r in report.failures if r.risk_level == "critical"]

if critical_failures:
    print(f"BLOCKED: {len(critical_failures)} critical case(s) failed.")
    for f in critical_failures:
        print(f"  {f.case_id}: {f.metric} = {f.score:.2f} (threshold {f.threshold})")
    exit(1)

if report.pass_rate < 0.80:
    print(f"BLOCKED: pass rate {report.pass_rate:.0%} below 80%.")
    exit(1)

if report.pass_rate < 0.90:
    print(f"WARNING: pass rate {report.pass_rate:.0%} — merging, but investigate.")

exit(0)
```

> **One critical escalation failure blocks the merge even at a 97% pass rate.** That is the whole reason Chapter 9 puts `risk_level` on every case. A gate that only reads an aggregate treats "38/40, both failures were low-risk" and "38/40, both failures were legal-notice escalations" as the same event, and they are not remotely the same event.

## Exercises

### 1 — Diagnose an ignored gate

A team's eval gate fails ~30% of the time on unchanged code. Engineers re-run until green. Name three causes and the order to fix them.

<details><summary>Solution</summary>

**Causes:** (1) thresholds set at or near 1.0 on judge-scored metrics, so normal judge variance breaches them; (2) the judge runs at temperature > 0, making it non-reproducible (Chapter 1); (3) a judge model too weak for the task, producing near-random scores on subtle cases.

**Fix order:** (2) first — it's a one-line config change and removes a whole variance source for free. Then (1), setting thresholds from observed score distributions rather than aspiration. Then (3), which costs money or latency.

The real damage isn't the flake, it's the **learned bypass**. Once "re-run it" is the reflex, the gate has stopped being a control — and the same reflex will be applied to the sensitive-data gate that must never be bypassed. A 30% flake rate doesn't degrade the gate by 30%, it degrades it to zero.
</details>

### 2 — Split the suites

Classify: (a) resolver branch coverage; (b) faithfulness on 40 golden cases; (c) every cited rule id is in the enum; (d) prompt-injection resistance; (e) the response schema validates; (f) tool order on critical flows.

<details><summary>Solution</summary>

**Fast gate (deterministic, no model):** (a), (c), (e). All plain assertions, milliseconds, zero flake.
**Eval gate (judge-scored):** (b), (d).
**Either — and this is the interesting one:** (f). If the golden case records `expected_tool_order` and you capture actual calls, comparing two lists is a **plain assertion**. It only needs a judge if you're scoring whether a *different* order was acceptable.

The habit: **before putting something in the slow gate, ask whether it's actually deterministic.** Tool order, schema validity, and enum membership get judge-scored far more often than they should be — slower, costlier, flakier, for a check `==` already answers.
</details>

### 3 — Choose what blocks and what warns

Design the block/warn policy for: a critical escalation case failing; faithfulness at 0.89 against a 0.90 threshold; sensitive-data exposure above zero; overall pass rate dropping 92% → 87%.

<details><summary>Solution</summary>

- **Critical escalation failure → BLOCK.** Zero tolerance; this is the Art. 14 chain from Chapter 10.
- **Faithfulness 0.89 vs 0.90 → WARN** on a single case (within judge noise), **BLOCK** if the *aggregate* is below threshold or several cases moved together. One case one point under is noise; a distribution shift is a regression.
- **Sensitive data > 0 → BLOCK, always.** Deterministic and binary, so no variance argument applies.
- **92% → 87% → BLOCK**, but on the *delta*, not the absolute. It's above an 80% floor, yet a 5-point drop in one PR is a regression regardless of where it sits. Absolute thresholds catch bad states; deltas catch bad changes, and you want both.

The principle: **block on things that are binary or that moved; warn on things that are graded and stable.**
</details>

### 4 — Handle the non-reproducible failure

The eval gate fails on `main` but passes locally on the same commit. Where do you look first?

<details><summary>Solution</summary>

**The judge.** The pipeline above deliberately uses a cloud judge in CI and a local one (`deepseek-r1:7b`) locally — same test code, different judge injected via config. A different judge is a different measuring instrument, and thresholds calibrated against one don't transfer to the other.

Second: is the CI judge pinned to a *version*? A provider silently updating a model changes every score, and a suite that passed on Monday fails on Tuesday with no commit in between.

Third: temperature and seed in CI.

The general lesson — **the judge is part of the system under test.** It gets pinned, versioned, and changed deliberately, exactly like a dependency. "We upgraded the judge model" is a change that requires re-baselining every threshold, and treating it as an infrastructure detail is how a team loses a week.
</details>

## Interview preparation

**"How do you put a probabilistic system in CI?"**

> Same mechanics as any suite: run it, produce a pass rate, exit non-zero, block the merge. Identical to `npx cypress run` in Jenkins — only the contents of the box changed. What's different is the design around it: thresholds live in one config file with a documented rationale per number, and I split fast deterministic tests from slow judge-scored ones so the cheap signal isn't delayed by the expensive one.

**"What's in your fast gate versus your slow gate?"**

> Fast gate runs on every push — the harness loop, idempotency, resolver branch coverage, schema validation, tool dispatch, closed-enum grounding. About 139 tests in a second, no model, no flake. Slow gate runs on PRs to main and covers what genuinely needs a judge: faithfulness, context recall, injection resistance. The slow one depends on the fast one, so I don't spend judge tokens discovering the answers are bad when the resolver is already broken. The insight from building it is that most of what makes an agent *safe* is deterministic, so most of it can gate every push.

**"How do you stop the gate from being bypassed?"**

> By making sure it fails for real reasons. A gate that flakes 30% of the time doesn't lose 30% of its value, it loses all of it — engineers learn to re-run until green, and then they apply that reflex to the gate that actually matters. So: judge at temperature zero, thresholds set from observed distributions rather than aspiration, never 1.0 on anything judge-scored, and the judge model pinned to a version. If it fails, it should mean something.

**"Does a pass rate tell you enough?"**

> No, and that's why every golden case carries a risk level. 38 out of 40 passing means completely different things depending on whether the two failures were low-risk lookups or critical escalation cases. My gate blocks on any critical failure regardless of the aggregate — one legal-notice case being answered by a bot blocks the merge at a 97% pass rate. I also gate on the *delta*, not just the absolute: 92% dropping to 87% is a regression even though it's above the floor.

**"Your suite passes in CI but fails locally. First thing you check?"**

> The judge. CI and local typically run different judge models — a cloud model in the pipeline, a local one for cost-free iteration — and a different judge is a different measuring instrument. Thresholds calibrated against one don't transfer. Then whether the CI judge is version-pinned, because a provider silently updating a model shifts every score with no commit in between. The underlying point is that the judge is part of the system under test: it gets pinned and versioned like any dependency, and changing it means re-baselining thresholds.

## Next

This pipeline gates what happens *before* a deploy. [Chapter 12 — Observability & Telemetry](../12-observability-and-telemetry/README.md) is the last chapter in this notebook, and it covers the same questions asked continuously *after* deploy, against real traffic instead of a static golden set.

Roadmap items beyond Chapter 12 (not yet written): LLM-as-judge model selection in depth (when a local judge is defensible vs. when it isn't), and a dedicated deep-dive on drift detection tooling (Arize, Fiddler) referenced briefly there.
