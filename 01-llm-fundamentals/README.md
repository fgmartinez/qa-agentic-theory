# Chapter 1 — LLM Fundamentals

*Part of [qa-agentic-theory](../README.md). Next: [Chapter 2 — RAG Fundamentals](../02-rag-fundamentals/README.md).*

Everything else in this notebook — RAG, agents, evaluation, compliance — sits on top of a small set of mechanical facts about how an LLM actually works. This chapter is that foundation, kept deliberately short: enough to make every later decision (which model, what temperature, when to fine-tune) a reasoned choice instead of a guess.

## What a transformer actually does, in one paragraph

An LLM predicts the next token given everything before it, one token at a time, using a mechanism called **attention** that lets every token in the input weigh every other token when deciding what comes next — which is what allows the model to connect "it" on page three back to a noun from page one. That's the whole trick. Everything else (chat formatting, tool calling, reasoning) is scaffolding built on top of "predict the next token, informed by attention over everything so far."

## Tokenization and context windows

Text isn't processed as characters or whole words — it's split into **tokens**, sub-word units that are the actual unit of computation, pricing, and the context limit.

- A token is roughly 3–4 characters of English on average — not a word, not a character.
- The **context window** is the maximum number of tokens (input + output combined) a model can attend to in one call. Exceed it and the oldest content simply falls out of view — the model doesn't "remember less well," it stops seeing that content at all.
- **Token-based pricing**: cloud APIs charge per token, and input/output tokens are usually priced differently (output is typically more expensive — it costs more compute to generate than to read). This is also why local models (Ollama) remove pricing entirely as a variable during learning: no per-token cost means no incentive to under-test to save money.

> **Why this matters for RAG (Chapter 2) before you get there.** Chunk size decisions aren't arbitrary — they're a direct consequence of the context window. Retrieve too many large chunks and you either blow the context budget or push earlier, still-relevant chunks out of the window entirely. The chunking trade-offs in Chapter 2 are a token-budget problem wearing a retrieval-quality costume.

## Generation controls

These parameters shape *how* the next token gets picked, and they matter for both what a system generates and how reproducible its evaluation is.

| Control | What it does | Practical guidance |
|---|---|---|
| **Temperature** | Scales randomness in the next-token choice. `0` = always the highest-probability token (deterministic). Higher = more variation. | `0.0` for judges, extraction, anything that needs to be reproducible. Higher (`0.7`+) for creative or brainstorming tasks where variety is the point. |
| **Top-p** (nucleus sampling) | Restricts sampling to the smallest set of tokens whose cumulative probability exceeds `p`. `top_p=0.9` means "only consider tokens covering the top 90% of probability mass." | Often left at a sane default (`0.9`–`1.0`) and temperature used as the primary lever; the two interact, so tune one at a time. |
| **Frequency penalty** | Reduces the probability of tokens proportional to how often they've *already* appeared in the output so far. | Higher values reduce literal repetition — useful for longer generations that tend to loop. |
| **Presence penalty** | Reduces the probability of any token that has appeared *at all*, regardless of how many times. | Encourages introducing new topics/words rather than sticking to a narrow vocabulary. |
| **Stopping criteria** | What ends generation: a stop token/string, hitting `max_length`, or — specific to agents — the model deciding it has no more tool calls left to make. | Set explicit stop sequences when parsing structured output; an unbounded generation is a bug waiting to happen, not a feature. |
| **Max length** | A hard ceiling on output tokens. | Set deliberately, not left at a framework default — too low silently truncates a real answer; too high wastes budget and slows response time. |

`temperature=0.0` shows up by design in `OllamaJudge` (used across Chapter 8's evaluation suites) precisely because a judge that isn't deterministic makes every metric it produces noisy — the same test case could pass on one run and fail on the next for no reason connected to the system under test.

## Streamed vs. unstreamed responses

**Streaming** returns tokens to the caller as they're generated, rather than waiting for the full response. It's a UX choice — a chat interface feels far more responsive streaming token-by-token than waiting silently for a multi-second full response.

It's a UX choice, though, not an evaluation choice: metrics (Chapter 8) run against the **complete** response regardless of whether the end user saw it streamed or not. Evaluating partial, in-flight text doesn't make sense — faithfulness or relevancy can only be judged once the full claim is on the page.

## Model families: open weight vs. closed weight

| | Open weight (Llama, Mistral, Qwen, DeepSeek) | Closed weight (GPT-, Claude-, Gemini-class) |
|---|---|---|
| Access | Download and run anywhere, including fully offline | API only — the weights themselves are never available |
| Cost | Free to run (hardware cost only); no per-token API fees | Per-token pricing, usage-based |
| Data privacy | Data never leaves the machine running it | Data goes to the provider's servers |
| Capability ceiling | Generally behind the frontier at comparable size | Frontier-class capability available |
| Customization | Fine-tunable, fully inspectable | Limited to prompting (mostly) and provider-exposed fine-tuning APIs |

For a FinTech-adjacent learning project, open-weight local models (`llama3.1:8b` as generator, `nomic-embed-text` for embeddings, `deepseek-r1:7b` as judge) are the right default: zero cost, and the privacy property — data never leaving the machine — is directly relevant to the domain, not just convenient for a portfolio budget.

## Reasoning models vs. standard models

A **reasoning model** (e.g. `deepseek-r1`, OpenAI's o-series) is trained to spend extra computation generating an internal chain of intermediate reasoning steps before producing a final answer — effectively trading latency and token cost for better performance on multi-step logical or mathematical tasks. A **standard model** produces its answer directly, token by token, with no separate reasoning phase.

The practical decision: use a reasoning model where the task genuinely requires multi-step logical inference and the extra latency/cost is acceptable — judging (`deepseek-r1:7b` as the evaluation judge across this notebook is exactly this choice: judging faithfulness or correctness benefits from working through the comparison step by step) is a good fit. A standard model is the right default for straightforward generation, classification, or extraction where there's no chain of reasoning to walk through.

## Fine-tuning vs. prompt engineering

Two different levers for changing model behavior, and reaching for the wrong one first wastes real time:

- **Prompt engineering** (Chapter 3) changes behavior through the input alone — no training, no infrastructure, iterate in minutes. This is always the first lever to pull.
- **Fine-tuning** changes the model's weights through additional training on task-specific examples — infrastructure-heavy, slow to iterate, and only worth it once prompting has been pushed as far as it goes and a specific, measurable gap remains that better instructions can't close (e.g. a very particular output format the model won't reliably hold to, or domain vocabulary a general-purpose model consistently gets wrong).

For everything in this notebook's two trunk projects, prompt engineering plus a well-designed evaluation layer (Chapter 8) has been sufficient — fine-tuning hasn't been needed, and reaching for it before exhausting prompting would be solving the wrong problem with the more expensive tool.

## Pricing of common models (what actually varies)

The dimensions that drive cost, independent of which specific model is chosen at any given time (prices change too often to be worth memorizing exact numbers):

- **Input vs. output token price** — output is typically several times more expensive than input.
- **Context window size** — larger windows sometimes carry a price premium even at the same per-token rate.
- **Model tier** — a smaller/faster model in the same family is cheaper per token but weaker; the trade-off is the same "capability vs. cost" curve as the open/closed-weight decision above, just continuous instead of binary.
- **Local = zero marginal cost** — the reason this notebook defaults to Ollama for learning: the pricing question disappears entirely, which is worth more during learning than the capability gap costs.

## Worked example: a token budget that doesn't fit

Numbers make this concrete in a way the prose above cannot. A RAG request against a model with an **8,192-token** context window:

| Component | Tokens | Note |
|---|---|---|
| System prompt | 350 | Fixed cost, every single call |
| Conversation history (6 turns) | 1,400 | Grows every turn |
| Retrieved chunks (8 × 512) | 4,096 | The tunable part |
| User question | 60 | |
| **Input subtotal** | **5,906** | |
| Reserved for the answer | 1,000 | `max_tokens` |
| **Total** | **6,906** | 1,286 to spare |

Now the user asks a follow-up. History grows to 1,900, and retrieval returns 10 chunks instead of 8:

```
350 + 1,900 + 5,120 + 60 = 7,430 input + 1,000 output = 8,430  →  over by 238
```

Something has to go, and **the model does not choose gracefully** — whatever falls outside the window is simply not seen. Three levers, each with a real cost:

- **Fewer chunks** (10 → 8): risks dropping the chunk that held the answer.
- **Truncate history**: the model forgets what the user said three turns ago.
- **Smaller `max_tokens`**: the answer gets cut off mid-sentence.

> **The insight to carry into Chapter 2.** Chunk size is not a retrieval-quality parameter that happens to have a cost — it is a **budget allocation** competing directly against history and answer length. A team that tunes `chunk_size` looking only at retrieval scores is optimising one term of a constraint they haven't written down.

## Exercises

### 1 — Estimate before you measure

A support agent's system prompt is 1,200 characters of English. Roughly how many tokens? If the model charges $3/1M input and $15/1M output, and it handles 50,000 requests/day with an average 400-token answer, what does the *system prompt alone* cost per month?

<details><summary>Solution</summary>

At ~3.5 chars/token, 1,200 chars ≈ **345 tokens**.

- System prompt: 345 × 50,000 × 30 = 517.5M tokens/month → **~$1,553/month**
- Answers: 400 × 50,000 × 30 = 600M output tokens → **~$9,000/month**

Two things worth noticing. First, trimming the system prompt by 40% saves ~$620/month for an afternoon's work — prompt length is an operating cost, not just a style question. Second, **output dominates**: at 5× the price and comparable volume, answer length is the bigger lever. "Be concise" in a system prompt is a cost control.
</details>

### 2 — Pick the temperature, and justify it

Choose a temperature for each and give the reason in one sentence:

(a) An LLM judge scoring faithfulness. (b) Generating 20 paraphrases of a test question for a golden set. (c) Extracting `{merchant, amount}` from a receipt. (d) The dispute-review decision engine in Chapter 6.

<details><summary>Solution</summary>

(a) **0.0** — a judge that isn't reproducible makes every metric noisy; the same case could pass one run and fail the next for reasons unrelated to the system under test.
(b) **0.8–1.0** — variety is the entire product here. Twenty near-identical paraphrases test nothing.
(c) **0.0** — there is one correct extraction; creativity is pure defect surface.
(d) **0.0** — a case that approves on Tuesday and escalates on Wednesday is not auditable, and Chapter 10's traceability requirements assume a decision can be reproduced.

The pattern: **temperature > 0 only when variety is the goal**, not when it is a tolerable side effect.
</details>

### 3 — Diagnose a silent truncation

A summariser works fine on short documents and returns confident, fluent summaries on long ones that omit the entire second half. No errors, no warnings. Two candidate causes from this chapter — which is which, and how would you tell them apart in ten minutes?

<details><summary>Solution</summary>

**Cause A: input overflow.** The document exceeded the context window, so the tail was never seen. **Cause B: `max_tokens` too low.** The model saw everything but was cut off mid-generation.

Ten-minute test: look at where the summary stops. If it ends **mid-sentence**, it's `max_tokens` (B). If it ends **fluently but only covers the start**, the tail was never in the window (A) — the model wrote a complete summary of what it could see.

Cheaper still: count the input tokens and compare against the window. The reason this matters is that both produce *confident, fluent* output — there is no error to catch, which is exactly why token accounting is worth instrumenting rather than assuming.
</details>

### 4 — Argue against fine-tuning

A stakeholder wants to fine-tune a model because it "keeps using the wrong tone." Make the case for prompting first, and name the one condition under which you'd change your mind.

<details><summary>Solution</summary>

Tone is close to the *ideal* case for prompting: it is a stylistic constraint, easy to state explicitly, and iterable in minutes. Fine-tuning costs a training pipeline, a labelled dataset, versioned artefacts, and re-tuning on every base-model upgrade — to solve something a system prompt plus three few-shot examples usually fixes in an afternoon.

**Change my mind when:** prompting has been pushed hard and a *specific, measured* gap remains that instructions cannot close — typically a rigid output format the model won't reliably hold, or domain vocabulary a general model consistently gets wrong. The condition is a **measurement**, not a frustration: without an eval set (Chapter 8), "it keeps using the wrong tone" is unfalsifiable, and you cannot tell whether fine-tuning helped.
</details>

## Interview preparation

**"What's a token, and why should I care?"**

> A sub-word unit — roughly 3–4 characters of English. It's the unit of three things at once: computation, pricing, and the context limit. That's why it matters practically: chunk sizes, conversation history, and answer length all compete for the same budget, and output tokens usually cost several times input. "Be concise" in a system prompt is a cost control, not a style note.

**"What happens when you exceed the context window?"**

> The excess isn't seen at all. The model doesn't degrade gracefully or "remember less well" — content outside the window is simply absent, and the model will answer confidently from what remains. That's what makes it dangerous: there's no error, just a fluent answer with a hole in it. It's why I'd instrument token counts rather than wait for someone to notice.

**"Why temperature 0 for an LLM judge?"**

> Because a non-deterministic judge makes every metric it produces noisy. If the same test case can pass one run and fail the next for reasons unrelated to the system under test, you can't set a CI threshold on it and you can't tell a regression from sampling variance. Temperature 0 doesn't make the judge *correct* — it makes it *reproducible*, which is the precondition for measuring anything.

**"Open-weight or closed-weight?"**

> Depends on which constraint binds. Open weight runs offline with zero marginal cost and the data never leaves the machine — which in a FinTech context is a compliance property, not a convenience. Closed weight buys frontier capability with per-token pricing and data going to a third party. For learning and for anything privacy-sensitive I default to local open-weight models; for a genuinely hard reasoning task where the capability gap shows up in the eval numbers, I'd pay for the frontier model. The point is that it's a measurable decision, not a preference.

**"When would you use a reasoning model?"**

> When the task needs multi-step inference and I can afford the latency and tokens. Judging is a good fit — assessing faithfulness benefits from working through the comparison step by step. Straightforward generation, classification, or extraction doesn't need it, and paying reasoning-model latency for an extraction task is spending money to be slower.

## Next

[Chapter 2 — RAG Fundamentals](../02-rag-fundamentals/README.md) is where two of the mechanics from this chapter — the context window and the embedding-vs-generation model split — turn into an actual architecture: retrieval, chunking, and grounding.
