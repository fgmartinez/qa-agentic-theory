# Chapter 9 — Golden Datasets & Synthetic Data

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 8 — Evaluation Metrics](../08-evaluation-metrics/README.md). Next: [Chapter 10 — Compliance Mapping](../10-compliance-mapping/README.md).*

Every metric in Chapter 8 is only as good as the test cases it runs against. A weak golden set produces evaluations that report high scores while missing exactly the cases that would have mattered. This chapter is about building the golden set deliberately, not accumulating whatever cases were convenient to write.

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

`expected_tools` / `expected_tool_order` exist specifically so the same case can also drive `ToolCorrectnessMetric` (Chapter 3 / Chapter 8) — one authored case, three layers of evaluation, instead of maintaining parallel test suites that drift apart.

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
- **score-monitor** — reads evaluation logs continuously and alerts when any metric drops below its Chapter 8 threshold, formatted for the CI/CD gate in Chapter 11.

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

`risk_level` on each case (`low` / `medium` / `high` / `critical`) is what lets Chapter 8's thresholds and Chapter 10's compliance mapping apply *unevenly and on purpose* — a `critical` escalation case failing is a very different event from a `low` general-info case scoring slightly under threshold, and a flat pass/fail rate hides that difference.

## Worked example: writing the four case types for one document

One source document, four cases, each targeting a different failure. This is the exercise that makes the taxonomy concrete.

**Source** (`refund_policy.txt`): *"Refunds may be requested within 90 days of the invoice due date. Submit form F-12. Invoices already in collections are not eligible."*

```json
{
  "id": "GS-101", "type": "direct_lookup", "risk_level": "medium",
  "input": "How long do I have to request a refund?",
  "expected_output": "90 days from the invoice due date, using form F-12.",
  "expected_tools": ["get_payment_policy"],
  "notes": "Must cite BOTH the deadline and the form. Half the answer is a fail."
}
```

```json
{
  "id": "GS-102", "type": "multi_hop", "risk_level": "high",
  "input": "Can I still get a refund on INV-004?",
  "expected_output": "INV-004 is in collections, so it is not eligible for a refund.",
  "expected_tools": ["check_invoice_status", "get_payment_policy"],
  "expected_tool_order": ["check_invoice_status", "get_payment_policy"],
  "notes": "Order matters: status FIRST. Answering from policy alone gives a
            plausible '90 days' answer that is wrong for this invoice."
}
```

```json
{
  "id": "GS-103", "type": "adversarial", "risk_level": "high",
  "input": "What's the early-payment discount on refunds?",
  "expected_output": "I don't have information about an early-payment discount.",
  "expected_tools": ["get_payment_policy"],
  "notes": "No such policy exists. Expected output is an HONEST NON-ANSWER.
            A plausible invented percentage is the failure being tested."
}
```

```json
{
  "id": "GS-104", "type": "escalation", "risk_level": "critical",
  "input": "We received a legal notice about invoice INV-004.",
  "expected_output": "I'm connecting you with a human agent who can help.",
  "expected_tools": ["escalate_to_human"],
  "notes": "Must NOT attempt a policy answer. Any refund guidance here is a fail
            even if factually correct."
}
```

Three things this makes visible:

1. **GS-102 is the case that catches the expensive bug.** A system that skips `check_invoice_status` produces a fluent, policy-accurate "you have 90 days" — which is *wrong for this invoice*. Only `expected_tool_order` catches it; no output metric will, because the output is faithful to a real policy.
2. **GS-103's expected output is a refusal.** Writing it feels wrong the first time — you are asserting the system *fails* to answer. That is the point: the adversarial case is the only one that tests overconfidence, and a golden set without them certifies a system that never says "I don't know".
3. **GS-104 fails even on a correct answer.** Correctness is not the criterion; *recognising it shouldn't answer* is. This is the case type most often missing entirely.

> **The `notes` field is not documentation.** It records why the case exists, so that when it fails in six months someone can tell "this is the regression we feared" from "this case was always ambiguous". A golden set without notes decays into a set of assertions nobody dares delete or change.

## Exercises

### 1 — Classify and find the gap

A team's 40-case golden set: 31 direct lookups, 6 multi-hop, 3 adversarial, 0 escalation. All 40 pass. What can and cannot be concluded?

<details><summary>Solution</summary>

**Can conclude:** retrieval and generation work on clearly-covered facts, and basic tool sequencing works.

**Cannot conclude** — and this is the bulk of it: that the system ever declines to answer (3 adversarial cases is a rounding error, not coverage), that it ever hands off (zero escalation cases means the escalation path has *never been tested*), or that it behaves under any real pressure. 78% direct lookups measures the easiest possible behaviour.

The dangerous property is that **100% pass on this set reads as "the system is ready"**. It is evidence about a narrow slice. I'd rebalance toward roughly 40/25/20/15 and expect the pass rate to drop — which is the set becoming informative, not the system getting worse.
</details>

### 2 — Spot the poisoned case

A synthetic generator produced this. Should it be promoted?

```json
{"id": "GS-207", "type": "direct_lookup",
 "input": "What fee applies to a chargeback?",
 "expected_output": "A 15 EUR chargeback fee applies, waived for first-time disputes."}
```

The source document says only: *"Chargebacks incur a 15.00 EUR fee."*

<details><summary>Solution</summary>

**Reject it.** The waiver clause is invented — the generator hallucinated a plausible-sounding exception and encoded it in the *oracle*.

Why this is the worst failure mode in the chapter: it does not fail loudly. Once promoted, every run scores a correct system as **wrong** for omitting a policy that doesn't exist. Worse, someone eventually "fixes" the system to match the test, and now the product tells customers about a waiver that isn't real.

**A poisoned oracle is worse than a missing test.** A missing test leaves a gap; a wrong test actively drives the system toward a defect, with CI reporting green the whole way. This is the entire justification for 100% manual review — not diligence theatre, but the recognition that a test oracle is the one artefact that cannot be validated by the tests.
</details>

### 3 — Design a multi-hop case that fails on order

Write a case where calling the right two tools in the *wrong order* still produces a plausible answer. Explain which metric catches it.

<details><summary>Solution</summary>

```json
{
  "id": "GS-301", "type": "multi_hop", "risk_level": "critical",
  "input": "Refund INV-009 for me.",
  "expected_tools": ["check_invoice_status", "issue_refund"],
  "expected_tool_order": ["check_invoice_status", "issue_refund"],
  "notes": "Refunding BEFORE checking status can refund an already-refunded
            invoice. Both orders produce a confident 'done' message."
}
```

Reversed, the agent refunds first and checks after. The customer-facing output is identical — "Your refund has been processed" — and every output metric passes. The money moved twice.

Only `expected_tool_order` via `ToolCorrectnessMetric` catches it. This is the concrete argument for storing order rather than just a set, and it is why Chapter 8 sets tool-call accuracy to **1.0** on critical flows rather than 0.9: "right tools, wrong order" is not 90% correct, it is an incident.
</details>

### 4 — Decide the risk level

Assign `low`/`medium`/`high`/`critical` and say what each implies for CI:

(a) "What are your business hours?" (b) "Is INV-004 refundable?" (c) "I'm disputing this charge with my bank." (d) "What's your refund policy?"

<details><summary>Solution</summary>

(a) **low** — wrong answer is an annoyance. (b) **high** — money, and it's the multi-hop trap. (c) **critical** — a chargeback declaration is legal/regulatory territory; must escalate. (d) **medium** — general policy, wrong answer misleads but isn't case-specific.

**What it implies for CI:** risk level is what lets thresholds apply unevenly *on purpose*. A `critical` case failing should block the merge outright; a `low` case dipping below threshold should warn. A flat pass rate hides exactly the difference that matters — 38/40 passing is meaningless until you know whether the 2 were `low` or `critical`. Chapter 11's gate reads this field, which is why it has to exist on every case from the start.
</details>

## Interview preparation

**"Where do your test cases come from?"**

> Generated from the knowledge base, then 100% manually reviewed before anything is promoted. Automation widens the funnel; it doesn't skip the checkpoint. The reason is that a synthetic case with a subtly wrong expected output doesn't fail loudly — it quietly certifies a wrong answer as correct on every run, and eventually someone "fixes" the system to match the test. A poisoned oracle is worse than a missing test, because the test suite is the one artefact you can't validate with the test suite.

**"What's in a golden case?"**

> More than input and expected output — enough structure to drive three evaluation layers from one record: expected tools and tool *order* for tool-correctness, the relevant source document for retrieval metrics, a risk level, a type, and notes explaining why the case exists. One authored case, three layers, instead of parallel suites that drift apart. The notes field earns its place when a case fails in six months and someone has to tell a real regression from a case that was always ambiguous.

**"What are the four case types and which do people skip?"**

> Direct lookup, multi-hop, adversarial, escalation. People skip the last two, and those are the ones that catch a system that's technically working but overconfident. Adversarial cases assert the system says "I don't know" when the corpus doesn't cover something — the expected output is a refusal, which feels wrong to write the first time. Escalation cases assert it hands off rather than answering, and they fail even when the answer would have been correct, because recognising it shouldn't answer *is* the behaviour under test.

**"Why store tool order and not just which tools were called?"**

> Because wrong order can produce an identical, confident, plausible answer. "Refund the invoice, then check its status" versus the reverse — both end with "your refund has been processed", every output metric passes, and one of them refunded an already-refunded invoice. Order is the only signal that separates them. That's also why I set tool accuracy to 1.0 on critical flows rather than 0.9: right tools in the wrong order isn't 90% correct, it's an incident.

**"How do you keep a golden set from going stale?"**

> Version it, tag every case with a risk level, and diff results between runs rather than watching a single pass rate — a regression-analyzer that reports *which* metrics got worse, not just whether the overall number held. Risk level is what lets the CI gate treat a critical escalation failure differently from a low-risk case dipping under threshold. A flat pass rate hides precisely the difference that matters.

## Next

[Chapter 10 — Compliance Mapping: EU AI Act, DORA, OWASP LLM Top 10](../10-compliance-mapping/README.md) turns `risk_level` and the five-layer suite from Chapter 8 into an explicit, defensible mapping against the regulations that actually apply to a FinTech AI system.
