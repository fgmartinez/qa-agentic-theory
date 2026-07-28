# Chapter 10 — CI/CD Quality Gates for AI Systems

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 9 — Compliance Mapping](../09-compliance-mapping/README.md). Next: [Chapter 11 — Observability & Telemetry](../11-observability-and-telemetry/README.md). This closes the loop back to [Chapter 6](../06-implementing-and-testing-the-harness/README.md)'s pytest suite and [Chapter 7](../07-evaluation-metrics/README.md)'s thresholds.*

Everything in Chapters 7–9 (Evaluation Metrics, Golden Datasets, Compliance Mapping) is only a quality *bar* until something actually enforces it on every change. This chapter is that enforcement: the same "exit 1 blocks the merge" pattern already familiar from Cypress-in-Jenkins, applied to LLM quality instead of UI behavior.

## Thresholds as config, not scattered constants

Every threshold from Chapter 7 lives in one file, with the reasoning next to the number — not as a magic literal buried in a test file six months later with no memory of why `0.90` and not `0.85`.

```yaml
# config/thresholds.yaml
version: "1.0"
risk_level: "high"   # from Chapter 9's EU AI Act tier

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
| 1 | Golden dataset | Chapter 8's authored cases | Faithfulness + Answer Relevancy |
| 2 | Hallucination probes | Adversarial cases designed to trigger fabrication | Hallucination |
| 3 | Adversarial prompts | Chapter 9's injection/role-manipulation set | Injection Resistance (GEval) |
| 4 | RAGAS pipeline | Full retrieval + generation sweep | Context Precision/Recall, Faithfulness, Answer Correctness |

Running all four on every push — not just the golden dataset — is what keeps a regression in retrieval (Chapter 2) or a new prompt-injection vector (Chapter 9) from silently landing on `main` between milestones.

## Where this closes the loop

This is the last chapter of the current notebook, and it lands back on the two things every earlier chapter built toward:

- The **harness resolver** (Chapter 6) is pure and deterministic specifically *so* it can be a normal, fast pytest suite in this pipeline — no judge model, no flakiness, runs in milliseconds on every push.
- The **five-layer evaluation suite** (Chapter 7), **golden set** (Chapter 8), and **compliance mapping** (Chapter 9) are what `scripts/evaluate.py` actually runs — this chapter is the delivery mechanism, not a separate topic.

## Next

This pipeline gates what happens *before* a deploy. [Chapter 11 — Observability & Telemetry](../11-observability-and-telemetry/README.md) is the last chapter in this notebook, and it covers the same questions asked continuously *after* deploy, against real traffic instead of a static golden set.

Roadmap items beyond Chapter 11 (not yet written): LLM-as-judge model selection in depth (when a local judge is defensible vs. when it isn't), and a dedicated deep-dive on drift detection tooling (Arize, Fiddler) referenced briefly there.
