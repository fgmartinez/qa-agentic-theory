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

`temperature=0.0` shows up by design in `OllamaJudge` (used across Chapter 7's evaluation suites) precisely because a judge that isn't deterministic makes every metric it produces noisy — the same test case could pass on one run and fail on the next for no reason connected to the system under test.

## Streamed vs. unstreamed responses

**Streaming** returns tokens to the caller as they're generated, rather than waiting for the full response. It's a UX choice — a chat interface feels far more responsive streaming token-by-token than waiting silently for a multi-second full response.

It's a UX choice, though, not an evaluation choice: metrics (Chapter 7) run against the **complete** response regardless of whether the end user saw it streamed or not. Evaluating partial, in-flight text doesn't make sense — faithfulness or relevancy can only be judged once the full claim is on the page.

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

For everything in this notebook's two trunk projects, prompt engineering plus a well-designed evaluation layer (Chapter 7) has been sufficient — fine-tuning hasn't been needed, and reaching for it before exhausting prompting would be solving the wrong problem with the more expensive tool.

## Pricing of common models (what actually varies)

The dimensions that drive cost, independent of which specific model is chosen at any given time (prices change too often to be worth memorizing exact numbers):

- **Input vs. output token price** — output is typically several times more expensive than input.
- **Context window size** — larger windows sometimes carry a price premium even at the same per-token rate.
- **Model tier** — a smaller/faster model in the same family is cheaper per token but weaker; the trade-off is the same "capability vs. cost" curve as the open/closed-weight decision above, just continuous instead of binary.
- **Local = zero marginal cost** — the reason this notebook defaults to Ollama for learning: the pricing question disappears entirely, which is worth more during learning than the capability gap costs.

## Next

[Chapter 2 — RAG Fundamentals](../02-rag-fundamentals/README.md) is where two of the mechanics from this chapter — the context window and the embedding-vs-generation model split — turn into an actual architecture: retrieval, chunking, and grounding.
