# Wiring this into `portfolio-risk-evaluator`

*Part of [Chapter 6](./README.md).*

**Status: revised after reading the real repo.** An earlier version of this file assumed the wiring was a field-rename exercise. Having now read `portfolio-risk-evaluator`'s actual contract, that assumption was wrong in a way worth documenting rather than quietly fixing.

## What was verified

Read from `github.com/fgmartinez/portfolio-risk-evaluator` @ `4a10109`:

| Claim | Status |
|---|---|
| Chapter 6's harness loop, resolver, corrector, idempotency behave as documented | **Verified** — 112 tests |
| Chapter 6's `app/schemas.py` field names match the trunk project | **Verified false.** They do not, and they were never meant to. |
| The trunk project has an execution layer for the harness to drive | **Verified false.** It has none, by design. |
| Trunk project state | Days 1–3 done. `/review` still returns 501. `src/agent/` empty. **54 tests passing** (6 contract + 48 rule). |

## The finding: the harness does not belong here

`portfolio-risk-evaluator` is a **review** system, not an **execution** system. Its output is a recommendation:

```python
class ReviewAction(str, Enum):
    auto_approve = "auto_approve"
    secondary_review = "secondary_review"
    escalate_immediate = "escalate_immediate"

class ReviewDecision(BaseModel):
    case_id: str
    action: ReviewAction
    risk_level: RiskLevel
    triggered_rules: list[RuleTrigger]      # a LIST — not one rule_id
    summary: str
    disclaimer: str = DEFAULT_DISCLAIMER    # set by code, never by the LLM
```

There is **no amount to move, no payment gateway, and nothing to execute.** None of the three actions has a side effect on a financial system — they route a case to a human or clear it. And the project's own `CLAUDE.md` closes the door explicitly:

> *"Do not scrape real transaction data or connect to any real payment processor."*

Chapter 6's harness is built around `PaymentGatewayClient.issue_refund(case_id, amount)` — executing a money-moving action, observing a timeout, retrying idempotently, correcting a partial settlement. **That entire problem does not exist in this project, and adding it would be scope creep against a documented non-goal.**

So the honest correction to the notebook's long-standing claim:

> ~~Chapter 6's harness feeds `portfolio-risk-evaluator`'s `/review` endpoint.~~
>
> **The harness's *executor* belongs to `fintech-support-ai-evaluator`, which has real side-effecting operations (`escalate_to_human`, payment actions). What belongs to `portfolio-risk-evaluator` is the harness's *resolver*.**

## What genuinely transfers: the resolver, not the executor

This is not a consolation prize. `compute_risk_level` in `src/tools/risk_rules.py` is *already* a resolver in Chapter 6's sense, arrived at independently:

```python
def compute_risk_level(triggers: list[RuleTrigger]) -> RiskLevel:
    if not triggers:
        return RiskLevel.low
    has_severe = any(t.rule_id in SEVERE_RULE_IDS for t in triggers)
    if has_severe or len(triggers) >= HIGH_RISK_TRIGGER_COUNT:
        return RiskLevel.high
    return RiskLevel.medium
```

Compare to `resolve_next_action`: a **pure function mapping collected evidence to a classification**, no I/O, no model, exhaustively testable. Same shape, same reasoning, same reason it's testable in isolation. The Day 4 step that maps `RiskLevel` → `ReviewAction` is the second half of the same pattern.

Everything Chapter 6 says about resolvers applies directly to it, and these are the concrete things to check on Day 4:

1. **Is there a fail-safe fallthrough?** Chapter 6's resolver escalates on any unrecognised combination rather than defaulting to success. The `RiskLevel` → `ReviewAction` mapping needs the same property: an unmapped or ambiguous state must land on `secondary_review` or `escalate_immediate`, never `auto_approve`. **`auto_approve` is the "assume it worked" of this system** — it is the one outcome that must never be reachable by omission.
2. **Is branch *order* pinned by a test, not just branch coverage?** `compute_risk_level` already has the ambiguity: a case can be both severe *and* have 3+ triggers. Today both roads lead to `high`, so it doesn't bite — but the moment someone adds a fourth level, order becomes behaviour.
3. **Is there a property test?** The Chapter 6 analogue: *nothing except an empty trigger list may produce `low`*. That keeps holding when a 13th rule is added and someone forgets to update a table-driven test — which is exactly the omission a table cannot catch.

## What else transfers, by chapter

| Chapter | Applies to | Note |
|---|---|---|
| **7 — Tool calling** | **Day 4 (LangGraph)** | Most immediately useful. `vendor_note` is a documented injection vector (R12) — Chapter 7's "injection through tool *results*" and the registry-as-authorisation-boundary argument both apply. |
| 6 — decision layer | Day 4 | `risk_rules.py` ≡ `RuleBasedDecisionEngine`: the deterministic baseline the LLM must beat. The project independently reached the same architecture. |
| 6 — grounding | Already done, and done *better* | Chapter 6 validates the rule id at parse time; this project types it as `RuleTrigger.rule_id: RuleId`, so **Pydantic rejects an invented rule at construction**. That is the stronger control, and Chapter 6 should arguably adopt it. |
| 8–9 — eval + golden sets | Week 4 | Their planned distribution (30/25/20/15/10) is finer-grained than Chapter 9's four types. Chapter 9's `expected_tool_order` argument applies once the graph has more than one node. |
| 10 — compliance | Week 4 (L5) | Each of the 12 rules already cites a real regulation (31 CFR 1010.310, 31 U.S.C. §5324, PSD2 SCA). That is most of a traceability chain already built. |
| 11–12 — CI + observability | Weeks 3, 5 | Chapter 11's fast-gate/eval-gate split maps directly: 54 deterministic tests in the fast gate, DeepEval/RAGAS in the slow one. |

## What NOT to do

- **Do not copy `app/harness/` into this project.** There is nothing for it to execute. It would be an unused abstraction that has to be explained in an interview, which is worse than not having it.
- **Do not rename Chapter 6's schemas to match.** Chapter 6's `RuleId` (`AUTO_APPROVE_LOW_VALUE`, …) is a *teaching* enum for a refund domain. The trunk project's R1–R12 are the real ones. They are different systems; the notebook's version should stay illustrative and clearly labelled as such.
- **Do not build Day 4 in one pass.** The trunk project's `CLAUDE.md` is explicit, and documents a time this already went wrong on the RAG day: smallest reviewable increment, explain before implementing, let the user write the first attempt at core learning-relevant logic. That instruction governs any work in that repo, including work informed by this notebook.

## If the harness pattern is wanted in this project anyway

There is one honest way it could earn its place, and it is worth knowing so the answer to "why no harness here?" is a decision rather than an omission.

The moment `escalate_immediate` acquires a *side effect* — creating a case in a review queue, notifying an on-call analyst, writing to an audit store — the full pattern applies immediately: that write can time out, partially succeed, or be duplicated, and "we recommended escalation but the case was never created" is precisely the silent-failure mode Chapter 5 exists to name.

Until then, `/review` is a pure function from case to recommendation, and a pure function does not need a harness. **That is the correct architectural answer, and it is a better interview answer than bolting one on:** *"The harness pattern applies where a decision has an effect. This system's decision is a recommendation, so the executor isn't needed — but the resolver is, and that's `compute_risk_level`."*
