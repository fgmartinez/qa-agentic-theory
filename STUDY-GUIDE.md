# Study Guide

*Part of [qa-agentic-theory](./README.md).*

How to actually work through this notebook so that at the end you can **build a harness-based agent system from an empty folder and defend every decision in an interview**. That is the bar. Reading all twelve chapters and nodding is not the same skill, and the difference only shows up under pressure.

## The honest premise

Reading produces recognition. Interviews and empty editors require **recall and construction**. These are different capabilities and only one of them is trained by reading.

So the structure below front-loads *doing*. Every chapter has exercises with hidden solutions and an interview-preparation section; those are not appendices, they are the chapter. If you skip them you have read a reference manual, not studied a textbook.

**The single most reliable test of whether this notebook worked:** delete `06-implementing-and-testing-the-harness/app/harness/` and rebuild it from memory, with the tests passing. If you can do that, everything else in the repo is commentary.

## Three paths

### Path A — Full course (4 weeks, ~6 h/week)

The intended experience. Read straight through, do every exercise.

| Week | Chapters | Deliverable at the end of the week |
|---|---|---|
| 1 | 1–4 | Explain tokens/context/temperature without notes; rewrite three vague prompts; diagnose a RAG failure as retrieval vs. generation. |
| 2 | **5–7** | **Build the harness from scratch. This is the week that matters.** |
| 3 | 8–10 | Write 4 golden cases (one per type); build a requirement→test traceability chain for one EU AI Act article. |
| 4 | 11–12, capstone | A CI gate design with justified thresholds; trace one incident end to end through structured logs. |

### Path B — Interview in two weeks

Compressed, targeting what gets asked.

1. **Days 1–3:** Chapters 5, 6, 7 — the harness and tool calling. Build the harness. Non-negotiable.
2. **Days 4–6:** Chapters 8, 9 — evaluation and golden sets. Do the metric-combination exercise until the diagnoses are automatic.
3. **Days 7–8:** Chapters 1, 3 — fundamentals and the agent loop, for vocabulary.
4. **Days 9–10:** Chapters 10, 11 — compliance chain and CI gates. Memorise one full traceability chain.
5. **Days 11–12:** Chapters 2, 4, 12 — read, do interview sections only.
6. **Days 13–14:** All interview sections, out loud, from memory.

### Path C — Reference

Already working on something specific:

- **Building an agent backend** → 5 → 6 → 7
- **The system gives wrong answers** → 2 → 8 → 9
- **Need to ship to a regulated environment** → 10 → 11 → 12
- **Deciding whether to use an LLM at all** → 1 → 6's rule-engine baseline argument

## How to read one chapter

Roughly 90 minutes for a chapter with code, 45 without.

1. **Read the intro and section headings first** (2 min). Know the shape before the detail.
2. **If the chapter ships code, run it before reading it** (10 min). Chapter 6's `python demo.py` and Chapter 7's `pytest` both work immediately. Understanding lands faster against observed behaviour.
3. **Read straight through, without notes** (25 min). Resist highlighting; it feels productive and mostly isn't.
4. **Do the exercises with the solutions collapsed** (30 min). This is the step that converts reading into knowledge. Write your answer down *before* expanding. An answer you thought but didn't write is an answer you didn't have.
5. **Read the interview section, then say each answer out loud from memory** (15 min). Out loud is not optional — fluent-in-your-head collapses under a real question.
6. **Write one paragraph in your own words** on what the chapter changed about how you'd build something.

### Marking your own exercises

Most solutions include reasoning beyond the answer. Score yourself on the **reasoning**, not the conclusion:

- **Got the answer and the reason** → understood.
- **Got the answer, missed the reason** → you pattern-matched. Re-read that section; this is the state that fails follow-up questions.
- **Missed the answer, reasoning was sound** → fine. Usually a missing fact, not a missing model.
- **Missed both** → do the exercise again in two days without re-reading.

## The five things to be able to do without notes

If you can do these, the notebook worked. Nothing else on this page matters as much.

1. **Draw the harness loop** — ACT → OBSERVE → RESOLVE, four verdicts, every exit an explicit terminal reason. *(Ch. 5–6)*
2. **Reproduce the failure taxonomy table** — observation → verdict → does the idempotency key change → why. *(Ch. 6)*
3. **Explain retry vs. correct** including why one reuses the key and the other must not. *(Ch. 6)*
4. **Name a failure that a single metric misses** — the faithful-but-wrong answer where faithfulness scores 1.0. *(Ch. 8)*
5. **Walk one compliance chain end to end** — requirement → behaviour → cases → metric → threshold with reasoning → CI gate → runtime evidence. *(Ch. 10)*

## Spaced repetition schedule

Recall decays. The cheapest defence is testing yourself at increasing intervals rather than re-reading.

| Interval | What to do (15 min) |
|---|---|
| Day 1 | Chapter's own exercises. |
| Day 3 | Reproduce the failure taxonomy table from memory. |
| Day 7 | Say all interview answers for that chapter out loud. |
| Day 21 | Rebuild one module from scratch (resolver, corrector, or dispatcher). |

## Common ways people get this wrong

**Reading Chapter 6 instead of building it.** The single biggest waste of the repo. The loop is 30 lines; understanding why each exit exists takes writing them.

**Skipping the exercises because the answer seems obvious.** The solutions frequently contain a second point the obvious answer misses — the *which failure is the incident* framing in Chapter 6's exercise 2, for instance. Obvious-seeming is precisely when to check.

**Treating the interview sections as summaries.** They're scripts to rehearse aloud. Reading them silently trains recognition, and recognition is what deserts you when someone asks "why not just let the model call the API directly?"

**Learning metric names without the confusable pairs.** Knowing what faithfulness *is* is worth much less than knowing why it can score 1.0 on a wrong answer. See [GLOSSARY.md](./GLOSSARY.md#the-confusable-pairs).

**Starting at Chapter 8.** Evaluation is the most job-relevant-*sounding* topic, so people start there. Without Chapters 5–7 you can recite metrics but can't explain what a harness is for — and the harness is the differentiator, because most candidates have the metrics.

## Self-assessment

Answer without looking. Chapter references are for checking afterwards.

**Foundations** — What breaks when you exceed the context window, and why is it dangerous? *(1)* · Why must documents and queries share an embedding model? *(2)* · What separates an agent from a chatbot with function calling? *(3)* · When is Chain-of-Thought worth its cost? *(4)*

**The harness** — Why is a tool call not an action? *(5)* · Why does the idempotency key exclude the attempt number? *(6)* · Why is the resolver's last line load-bearing? *(6)* · Why is the corrector separate from the resolver? *(6)* · Why does budget exhaustion get its own terminal reason? *(6)*

**Tools** — What are the three things sent to the model per tool? *(7)* · Why is the registry an authorisation boundary? *(7)* · Does MCP make tool calling safer? *(7)*

**Evaluation** — How can faithfulness score 1.0 on a wrong answer? *(8)* · Which metric combination indicates a generation rather than retrieval problem? *(8)* · Why does a poisoned golden case beat a missing one for damage? *(9)* · Why store tool *order*? *(9)*

**Shipping** — Name a full traceability chain. *(10)* · Why never 1.0 on a judge-scored threshold? *(10, 11)* · What goes in the fast gate vs. the eval gate? *(11)* · Why can't CI catch drift? *(12)*

Fewer than 12 of 19 with confident reasoning: re-read the weakest area before moving on.

## When you're done

Build the [capstone](./CAPSTONE.md). It's specified as requirements rather than instructions, which is the point — it's the closest thing here to the actual task of "sit down and build a harness system."
