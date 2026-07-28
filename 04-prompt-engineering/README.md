# Chapter 4 — Prompt Engineering

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 3 — AI Agents 101](../03-ai-agents-101/README.md). Next: [Chapter 5 — The Harness Pattern](../05-the-harness-pattern/README.md).*

Chapter 3's step 2 — Reason and Plan — is where prompt engineering does its work. This chapter is about that step specifically: how the instructions given to a model shape whether it reasons correctly before it ever gets to step 3 (Acting).

## What prompt engineering actually is

**Prompt engineering** is the practice of shaping a model's input — instructions, examples, context, structure — to reliably get the behavior needed, without touching the model's weights. It's the first lever from Chapter 1's fine-tuning-vs-prompting comparison, and for both trunk projects in this notebook, it's been the *only* lever needed so far.

It's easy to underrate because the surface mechanics look like "just write better English." What actually makes a prompt work is closer to writing a specification: unambiguous, complete, and structured so the model can't quietly fill a gap with something plausible instead of asking or refusing.

## Writing prompts that hold up

Three habits do most of the work, in order of impact:

### Be specific

Vague instructions get filled in by the model's own judgment — which is exactly the thing a domain-specific system can't rely on. *"Answer questions about payment policy"* leaves the model free to decide what counts as in-scope. *"Answer only using the retrieved policy context. If the context doesn't cover the question, say so explicitly — never infer a policy that isn't stated"* removes that freedom, and is a direct instance of the RAG-grounding discipline from Chapter 2.

### Provide additional context

The model only knows what's in front of it (Chapter 3's Perception step). A prompt that assumes shared context the model doesn't have — an internal acronym, an implicit business rule, "the usual process" — produces a plausible-sounding answer built on a guess. Spelling out context explicitly, even context that feels obvious to a human reading it, is what closes that gap.

### Use precise technical/domain terms

*"Check if the payment is late"* is ambiguous between several real states (overdue, in dispute, in a grace period). *"Check if `invoice_status == OVERDUE`"* — using the system's actual vocabulary — removes the ambiguity a natural-language paraphrase reintroduces. This matters most exactly where Chapter 9's compliance mapping matters most: financial and regulatory language has precise meanings, and a prompt that paraphrases loosely invites the model to paraphrase loosely too.

## Chain-of-Thought (CoT)

**Chain-of-Thought** prompting asks the model to work through its reasoning step by step before giving a final answer, instead of jumping straight to a conclusion — either by explicit instruction ("think through this step by step before answering") or by example (showing worked reasoning in a few-shot prompt).

CoT measurably improves performance on tasks with more than one logical step, because it gives the model room to catch its own error mid-reasoning instead of committing to a wrong answer in the first token. The cost is real: longer output, more latency, more tokens billed (Chapter 1's token-pricing section). CoT is worth it for genuinely multi-step reasoning (a multi-hop golden-set case from Chapter 8: "check this invoice's status, then look up the policy that applies to that status") and usually not worth it for single-fact lookups where there's no chain to walk.

```python
# Without CoT — jumps straight to a conclusion
prompt = "Is invoice INV-004 eligible for a refund?"

# With CoT — reasoning is elicited explicitly, not left implicit
prompt = """
Is invoice INV-004 eligible for a refund? Work through this step by step:
1. What is the invoice's current status?
2. What does the refund policy say about that status?
3. Based on 1 and 2, is it eligible?
Then give your final answer.
"""
```

> **Why this matters for GEval criteria (Chapter 7).** A `GEval` criteria string *is* a prompt aimed at the judge model instead of the primary generator — the same specificity and CoT principles apply. A vague criteria string ("check if the answer is good") produces as unreliable a judge as a vague system prompt produces an unreliable agent. The `FinancialAccuracy` and `SensitiveDataProtection` criteria in Chapter 9 are deliberately exhaustive about what FAILS and what PASSES for exactly this reason.

## Tree-of-Thought (ToT)

**Tree-of-Thought** extends CoT by exploring *multiple* reasoning paths rather than committing to one linear chain — the model (or an orchestrating process around it) generates several candidate next-steps, evaluates which look most promising, and can backtrack from a path that stops looking productive. Where CoT is one path walked once, ToT is a small search over several.

The trade-off is steeper than CoT's: multiple branches means multiple times the tokens and latency, and the orchestration itself (generating branches, scoring them, choosing which to continue) adds real implementation complexity. ToT earns its cost on problems with several plausible approaches where picking wrong early is expensive to recover from — not on tasks with one clear, mostly-linear path. Neither trunk project in this notebook has needed it yet: the reasoning both need (rule lookup, tool sequencing) is linear enough that CoT alone covers it, and reaching for ToT here would be solving a problem that doesn't exist yet.

## Example use cases (and where this notebook's projects sit among them)

A public roadmap of agent applications lists five common categories — worth placing this notebook's own projects against them, since it clarifies what kind of prompting problem each one actually is:

| Use case | What makes it distinct | Where it sits here |
|---|---|---|
| Personal assistant | Broad scope, low stakes per error | Neither trunk project — both are narrow-domain by design |
| Code generation | Correctness is checkable (it either compiles/passes tests or it doesn't) | Not directly, though Claude Code + BMad tooling in the broader workflow is this category |
| Data analysis | Exploratory, output is often a judgment call | Not directly |
| Web scraping / crawling | Structured extraction from unstructured sources | Not directly |
| **Domain-constrained decisioning** | Narrow scope, high stakes per error, answer must be traceable to a source or rule | **Both trunk projects** — `fintech-support-ai-evaluator` (RAG-grounded) and `portfolio-risk-evaluator` (rule-grounded) |

The category both projects actually fall into doesn't appear on that public list by name, and that's informative on its own: high-stakes, narrow-domain decisioning is a distinct prompting problem from the five listed above, closer to writing a specification than writing an assistant persona. Every technique in this chapter — specificity, explicit context, precise terms, CoT for the genuinely multi-step cases — is disproportionately important here precisely because the failure cost per wrong answer is high and the acceptable answer space is narrow, not broad and forgiving the way a general personal assistant's is.

## Applied: the same discipline, twice

Two prompts already built for the trunk projects are both instances of "be specific + provide context + use precise terms," applied to two different grounding strategies:

- **`portfolio-risk-evaluator`** — the agent's prompt constrains it to cite only from the closed `RuleId` enum (Chapter 9). The specificity isn't just in wording, it's structural: the prompt makes citing a non-existent rule not just discouraged but schema-invalid.
- **`fintech-support-ai-evaluator`** — the agent's prompt constrains it to answer only from retrieved policy context (Chapter 2's grounding discipline) and to explicitly say so when the context doesn't cover the question, which is what the adversarial golden-set cases (Chapter 8) actually verify.

Both are the same underlying move — remove the model's freedom to fill a gap with something plausible — applied through different grounding mechanisms (a closed enum vs. retrieved context).

## Next

[Chapter 5 — The Harness Pattern](../05-the-harness-pattern/README.md) picks up right where Chapter 3's step 3 (Acting) left off: once a well-prompted model has reasoned its way to a decision, something has to actually carry that decision out, safely, against real systems.
