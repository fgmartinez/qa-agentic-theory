# Chapter 8 — Golden Datasets & Synthetic Data

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 7 — Evaluation Metrics](../07-evaluation-metrics/README.md). Next: [Chapter 9 — Compliance Mapping](../09-compliance-mapping/README.md).*

Every metric in Chapter 7 is only as good as the test cases it runs against. A weak golden set produces evaluations that report high scores while missing exactly the cases that would have mattered. This chapter is about building the golden set deliberately, not accumulating whatever cases were convenient to write.

## What a golden set case needs

A rich case carries more than a question and an answer — it carries enough structure to evaluate retrieval, generation, *and* tool routing from the same record:

```json
{
  "id": "GS-001",
  "type": "direct_lookup",
  "risk_level": "medium",
  "input": "How many days do I have to request a refund on an overdue invoice?",
  "expected_output": "You have 90 days from the due date to request a refund. You'll need to submit form F-12.",
  "relevant_policy": "refund_policy.txt",
  "expected_tools": ["get_payment_policy"],
  "expected_tool_order": ["get_payment_policy"],
  "notes": "Base refund case. Must cite both the deadline and the form."
}
```

`expected_tools` / `expected_tool_order` exist specifically so the same case can also drive `ToolCorrectnessMetric` (Chapter 3 / Chapter 7) — one authored case, three layers of evaluation, instead of maintaining parallel test suites that drift apart.

## Case types — and why each one exists

A golden set built only from "obvious" questions systematically misses the failure modes that actually matter. Four categories, each targeting a distinct failure:

| Type | What it tests | Example |
|---|---|---|
| **Direct lookup** | Basic retrieval + generation on a single, clearly-covered fact | "How many days for a refund?" |
| **Multi-hop** | Whether the agent correctly sequences more than one tool when the answer needs both | "Invoice INV-004 — can I get a refund and what's the process?" (needs `check_invoice_status` *then* `get_payment_policy`, in that order) |
| **Adversarial** | Whether the system says "I don't know" instead of inventing an answer, when the corpus genuinely doesn't cover the question | "What's the early-payment discount?" (no such policy exists — `expected_output` is an honest non-answer, not a plausible-sounding guess) |
| **Escalation** | Whether the system correctly recognizes it should *not* attempt to answer and hands off instead | "My company got a legal notice about invoice INV-004" — this is `escalate_to_human` territory, not a policy lookup |

Adversarial and escalation cases are the ones a rushed golden set skips — and they're the ones that catch a system that's technically working but overconfident. `RuleId`-grounded rejection (portfolio-risk-evaluator's approach — Chapter 5) and this adversarial-case pattern are the same underlying discipline applied twice: don't let the system answer for something it has no grounding for.

## Generating candidates at scale, without lowering the bar

Hand-writing every case doesn't scale, but synthetic generation without review produces a golden set that quietly encodes the LLM's own blind spots into the test oracle. The workable pattern is generation *plus* mandatory human review before anything is promoted:

```python
# Generate candidates from the knowledge base — never hand-write
# every case, but never trust one unreviewed either.
df = generate_synthetic_candidates(knowledge_base="data/policies/")
df.to_csv("data/synthetic_candidates.csv", index=False)

# 1. Export to CSV
# 2. Review 100% of candidates manually
# 3. Mark which ones pass review
# 4. Only reviewed cases move into golden_set.json
```

> **The rule that makes this safe.** 100% manual review before a synthetic case is promoted, no exceptions for volume. A synthetic case that looks reasonable but has a subtly wrong `expected_output` doesn't fail loudly — it just quietly certifies a wrong answer as correct every time the suite runs.

A `.claude/agents/golden-generator.md` sub-agent can do the generation step directly against the project's own knowledge base, producing candidates in the exact target schema (direct lookup + multi-hop + adversarial per document), which is worth doing precisely because the human review step stays the bottleneck on purpose — automation should widen the funnel, not skip the checkpoint.

## Keeping the golden set honest over time

Two companion agents (or scripts, if a sub-agent is overkill for the moment) keep a golden set from silently going stale:

- **regression-analyzer** — diffs evaluation results between runs and reports which metrics got worse, not just whether the overall pass rate held.
- **score-monitor** — reads evaluation logs continuously and alerts when any metric drops below its Chapter 7 threshold, formatted for the CI/CD gate in Chapter 10.

## Applied to `fintech-support-ai-evaluator`

The golden set for that project is versioned, scoped to the project, and tagged by risk:

```json
{
  "version": "1.2",
  "project": "fintech-support-ai-evaluator",
  "risk_level": "high",
  "total_cases": 15,
  "cases": [ /* direct_lookup, multi_hop, adversarial, escalation — see above */ ]
}
```

`risk_level` on each case (`low` / `medium` / `high` / `critical`) is what lets Chapter 7's thresholds and Chapter 9's compliance mapping apply *unevenly and on purpose* — a `critical` escalation case failing is a very different event from a `low` general-info case scoring slightly under threshold, and a flat pass/fail rate hides that difference.

## Next

[Chapter 9 — Compliance Mapping: EU AI Act, DORA, OWASP LLM Top 10](../09-compliance-mapping/README.md) turns `risk_level` and the five-layer suite from Chapter 7 into an explicit, defensible mapping against the regulations that actually apply to a FinTech AI system.
