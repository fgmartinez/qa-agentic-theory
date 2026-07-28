# Chapter 2 — RAG Fundamentals: What, Why, How

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 1 — LLM Fundamentals](../01-llm-fundamentals/README.md). Next: [Chapter 3 — AI Agents 101](../03-ai-agents-101/README.md). Feeds: [`fintech-support-ai-evaluator`](https://github.com/fgmartinez) (payment policy RAG tool) and [`clinic-ai-testing`](https://github.com/fgmartinez/llm-test-portfolio) (reference implementation, already built).*

## What RAG is, and why an LLM can't just answer from memory

**Retrieval-Augmented Generation (RAG)** retrieves relevant information from an external knowledge base and injects it into the prompt *before* the LLM generates a response, instead of relying only on what the model memorized during training.

Three limitations make this necessary:

1. **Knowledge cutoff** — the model only knows what it saw in training. If a payment policy changed last week, the model doesn't know, unless that policy is retrieved and handed to it at query time.
2. **Specificity** — the model knows general facts, not *your* specific policies, pricing, or internal documents. RAG injects the domain-specific context that makes an answer correct for your business, not just plausible in general.
3. **Verifiability** — an answer from memory can't be traced to a source. An answer built from retrieved chunks can: you know exactly which document, which paragraph, backed the claim. That traceability is what makes the answer auditable — and auditability is the whole point in a regulated domain.

> **Analogy — the open-book exam.** A plain LLM call is a closed-book exam: only what's memorized. RAG is an open-book exam: the model can look up the specific page before answering. It's slower and adds moving parts, but it means the answer can be checked against something concrete.

The trade-off is real: RAG adds a retrieval pipeline, a vector store, and a chunking strategy — each one a new place to introduce bugs. Reach for RAG only when the model's training data genuinely isn't enough for the use case. A payment-policy assistant needs it (policies are internal and change); a general knowledge chatbot usually doesn't.

## The pipeline, stage by stage

```
Documents → Chunking → Embedding → Vector Store → Retrieval → Prompt Grounding → Generation
```

### 1. Chunking

The document is split into fragments ("chunks") before anything else happens. Feeding a whole document to the retriever defeats the purpose — it mixes unrelated topics into one embedding and degrades retrieval precision.

| Choice | Effect |
|---|---|
| Chunks too large | High coverage per chunk, but retrieval precision drops — a chunk about three different policies gets pulled in for a question about only one of them. |
| Chunks too small | Better local precision, but risk of losing context — a sentence explaining *when* a rule applies gets separated from the rule itself. |
| Low overlap between chunks | Risk of cutting a critical sentence exactly at the boundary. |
| High overlap | Improves continuity across the cut, at the cost of redundant storage and slightly noisier retrieval. |

A practical starting point: split by document structure first (headers), then enforce a hard size limit within each section — this keeps a chunk anchored to "what section is this," not just "what fits in N characters."

```python
# Two-pass strategy: structure-aware, then size-bounded.
md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
    strip_headers=False,  # keep headers in the chunk for context
)
size_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,       # sweet spot for factual Q&A: enough for
                           # a complete answer, small enough for
                           # precise retrieval
    chunk_overlap=50,     # prevents cutting a sentence at the boundary
    separators=["\n\n", "\n", ". ", " ", ""],
)
```

### 2. Embeddings

Each chunk — and later, each query — is converted into a numeric vector that represents its meaning, not its exact wording. This is what lets a question like *"can I cancel my order?"* retrieve a chunk titled *"rescheduling and cancellation fees"* even though the words barely overlap: semantic similarity, not keyword match.

The same embedding model must embed both documents and queries, or the vector spaces won't be aligned and similarity scores become meaningless.

```python
# nomic-embed-text: runs locally via Ollama (no API key), 768-dim
# vectors, strong semantic-similarity performance, same model for
# both documents and queries.
from langchain_ollama import OllamaEmbeddings
embedding_model = OllamaEmbeddings(model="nomic-embed-text", base_url="http://localhost:11434")
```

### 3. Vector store

The embedded chunks need somewhere to live that supports fast similarity search.

| | ChromaDB | FAISS |
|---|---|---|
| Persistence | Built-in — survives restarts | In-memory only, no built-in persistence |
| Metadata filtering | Yes — search within a specific document | No |
| Scale | Good up to hundreds of thousands of vectors | Optimized for millions–billions, GPU-accelerated |
| API | Simple, built for prototyping | Lower-level, more setup |
| When to use | Default choice for a project like this | When retrieval scale genuinely outgrows a single-machine store |

For a policy knowledge base of a few hundred chunks, ChromaDB is the right default — the extra scale FAISS buys isn't needed, and persistence + metadata filtering are worth more day to day.

### 4. Retrieval

The retriever returns the top-`k` most similar chunks to the query's embedding.

- **Low `k`** — less noise in the prompt, but risk of missing a chunk that was actually needed.
- **High `k`** — better recall, but more irrelevant text competing for the model's attention, which can dilute the answer or push out something that mattered.

`k` is a tuning knob, not a constant — it's one of the first things to sweep when Context Precision or Context Recall (Chapter 8) come back low.

### 5. Prompt grounding

The retrieved chunks get inserted into the prompt as context. This is the step that draws the line between *"answering with documentary backing"* and *"answering from the model's own intuition."* A well-grounded prompt instructs the model explicitly to answer only from the provided context and to say so plainly when the context doesn't cover the question — the alternative is a model that fills the gap with something plausible-sounding and wrong.

### 6. Generation

The LLM produces the final answer. Even with perfect retrieval, generation can still fail on its own: summarizing poorly, answering a slightly different question than the one asked, adding a detail that wasn't in the context, or dropping a disclaimer the policy requires. This is precisely why retrieval quality and generation quality get evaluated as two separate things in Chapter 8 — a good retriever paired with a careless generator still produces a bad, unfaithful answer.

## Choosing the models: generator vs. embedder

A RAG system needs two different models doing two different jobs, and conflating them is a common early mistake.

| | Generator | Embedder |
|---|---|---|
| Job | Reads context + question, writes the answer | Converts text to a vector for similarity search |
| Example (local) | `llama3.1:8b` — 8B params, ~6GB RAM, good quality/speed balance | `nomic-embed-text` — 768-dim, purpose-built for semantic similarity |
| Lighter alternative | `llama3.2:3b` — less accurate, runs on 4GB RAM | — |
| Local vs. cloud | Local (Ollama): free, private, no rate limits, weaker than frontier cloud models. Cloud (GPT-4-class): far more capable, costs per call, data leaves the machine. | Same trade-off, usually a smaller decision since embedding models are cheaper and less differentiated at the top end. |

> **The trade-off to actually understand.** An 8B local model is nowhere near GPT-4-class capability. That's fine for *generation* in a learning/portfolio context — the gap is well understood and documented. It matters more when the *same* small model is also asked to judge outputs (Chapter 8) — a weak judge is a weak signal, not just a weak answer.

## Applied to `fintech-support-ai-evaluator`

The `get_payment_policy` tool is the RAG surface of that project: a question about a payment policy triggers retrieval over the policy knowledge base, the retrieved chunks ground the answer, and the agent decides whether that's enough or whether `check_invoice_status` also needs to be called first (a multi-hop case — see Chapter 9's golden set examples).

The reference implementation already built in `clinic-ai-testing` uses exactly this pipeline (LangChain + ChromaDB + Ollama, `nomic-embed-text` embeddings, `chunk_size=250` in its `MarkdownTextSplitter`) — including a documented real failure: at that chunk size, a specific availability block gets split across a chunk boundary, which shows up as a Context Precision failure, not a hallucination. That's the diagnostic distinction Chapter 8 formalizes.

## Worked example: the chunk boundary failure, traced

The `clinic-ai-testing` failure mentioned above is worth walking through in full, because it is the single most instructive RAG bug and it is routinely misdiagnosed.

Source document:

```markdown
## Consultation Availability
Dr. Ramirez sees patients Monday through Thursday.
Friday is reserved for surgery and no consultations are booked.
```

At `chunk_size=250` with structure-unaware splitting, the split lands mid-section:

```
CHUNK 41: "## Consultation Availability
           Dr. Ramirez sees patients Monday through Thursday."
CHUNK 42: "Friday is reserved for surgery and no consultations are booked."
```

Question: *"Can I book a consultation with Dr. Ramirez on Friday?"*

Retrieval embeds the query and returns the top-3. Chunk 41 scores highly — it has the doctor's name, "consultation", "availability". **Chunk 42 does not**: it has no doctor name, no "consultation" in the query's sense, and reads as a fragment about surgery. It never enters the prompt.

The model, correctly grounding itself in the only context it was given, answers:

> *"Dr. Ramirez sees patients Monday through Thursday."*

Technically true, answers a different question, and omits the one fact that mattered.

**Now the diagnosis, which is the point:**

| Metric | Result | Why |
|---|---|---|
| Faithfulness | **Passes** | Every claim in the answer is supported by the retrieved context. |
| Answer Relevancy | Often passes | It's about consultation availability for the right doctor. |
| **Context Recall** | **Fails** | The context needed to answer was not retrieved. |

> **This is a retrieval failure wearing a hallucination costume.** Every instinct says "the model gave a misleading answer, fix the prompt" — and prompt work will do nothing, because the model never saw the fact. Chapter 8 formalises this: measure retrieval and generation *separately*, or you will spend weeks tuning the wrong stage.

The fixes are all upstream: split on headers first so the section stays whole, raise `chunk_overlap` so the boundary sentence appears in both chunks, or raise `k`. None of them are prompt changes.

## Exercises

### 1 — Choose a chunk size, and say what it costs

Two corpora: (a) a 40-page payments policy PDF with numbered clauses and cross-references; (b) 8,000 support chat transcripts, 3–20 turns each.

Pick a chunking strategy for each. Name what you're giving up.

<details><summary>Solution</summary>

**(a) Policy PDF** — structure-aware first (split on clause headings), then a size cap around 512 with ~50 overlap. Clauses are the natural retrieval unit and a clause split in half is useless. *Cost:* cross-references ("subject to clause 7.2") break — the retrieved chunk cites a clause that wasn't retrieved. Mitigate by keeping heading text in every chunk, and accept that multi-hop questions need either higher `k` or an agent that can retrieve twice.

**(b) Transcripts** — chunk per conversation, not per turn, unless conversations run long. A single turn ("yes that's right") is meaningless without its neighbours. *Cost:* long conversations blow the size limit and mix topics, hurting precision. Splitting them mid-conversation is worse than the size cost.

The general rule: **chunk on the boundary that makes a fragment independently meaningful.** Character counts are a constraint you apply *after* that, not the primary axis.
</details>

### 2 — Diagnose three failures

For each, name the stage at fault and the metric that would catch it:

(a) Asked about refund timing, the system answers about chargeback fees.
(b) The answer is accurate but adds "contact us within 14 days" — nowhere in any document.
(c) The correct chunk is retrieved and ranked #1, but the answer omits the key condition.

<details><summary>Solution</summary>

(a) **Retrieval.** Wrong chunks entered the prompt — Context Precision, and likely a `k` or embedding-quality problem. Generation did its job with bad input.
(b) **Generation.** The model added an unsupported claim — Faithfulness. Retrieval may have been perfect. This is the actual hallucination, as distinct from the worked example above.
(c) **Generation.** The right context was there and the model summarised badly. Faithfulness might even pass if the omission isn't a false claim; this is where a custom GEval criterion ("does the answer preserve all qualifying conditions?") earns its place — Chapter 8.

The pattern worth internalising: **(a) is upstream, (b) and (c) are downstream, and they need completely different fixes.** Conflating them is the most expensive mistake in RAG debugging.
</details>

### 3 — Explain the shared-embedder rule

Why must the same embedding model embed both documents and queries? What breaks if you embed documents with `nomic-embed-text` and queries with OpenAI's `text-embedding-3-small`?

<details><summary>Solution</summary>

Different models produce vectors in **unrelated coordinate spaces**. Dimension 200 in one model doesn't mean what dimension 200 means in the other, and the two aren't even necessarily the same length (768 vs. 1536).

Cosine similarity between vectors from different spaces is arithmetically computable and semantically meaningless — you get numbers, they rank, and the ranking is noise. That's the trap: it doesn't crash. Retrieval quietly returns near-random chunks and every downstream metric degrades in a way that looks like "the model is bad".

Practical implication: **changing the embedding model means re-embedding the entire corpus.** It's a migration, not a config change, and treating it as a one-line swap silently corrupts the index.
</details>

### 4 — Argue for `k`

Retrieval currently uses `k=3`. Context Recall is 0.62. A colleague proposes `k=20`. What do you expect to happen to each metric, and what would you actually do?

<details><summary>Solution</summary>

**Expected:** Context Recall goes up — more chunks, more chance the needed one is included. Context *Precision* goes down, since most of the 20 are irrelevant. Faithfulness may drop as the model's attention is diluted across noise. Cost and latency rise; token budget (Chapter 1) tightens against history and answer length.

**What I'd do:** treat 0.62 recall as a *symptom* first. Inspect the failing cases — if the needed chunk exists but ranks 4th–6th, `k=5` fixes it cheaply. If the needed chunk doesn't exist in retrievable form at all (the worked example above), **no value of `k` helps** and the fix is chunking. Raising `k` to 20 to paper over a chunking bug buys a metric improvement and a worse system.
</details>

## Interview preparation

**"What is RAG and why not just fine-tune?"**

> Retrieval-augmented generation: retrieve relevant documents at query time and put them in the prompt, so the model answers from provided text rather than from what it absorbed in training. Versus fine-tuning: RAG updates by editing a document, gives you citations, and keeps a clear line between what the system was told and what it inferred. Fine-tuning bakes knowledge into weights — expensive to update, impossible to cite, and it doesn't actually stop the model inventing things. For a policy knowledge base that changes monthly, RAG is the obvious answer.

**"Walk me through the pipeline."**

> Chunk the documents, embed each chunk into a vector, store them in a vector database, embed the incoming query with the *same* model, retrieve the top-k most similar chunks, insert them into the prompt with instructions to answer only from that context, generate. Two stages fail independently, which is the important part — good retrieval with careless generation still produces a bad answer, so I evaluate them separately.

**"How do you tell a retrieval failure from a hallucination?"**

> By checking whether the needed fact was in the retrieved context at all. If it wasn't, it's retrieval — Context Recall fails while Faithfulness *passes*, because every claim in the answer is supported by what the model actually saw. That's the case people misdiagnose most: the answer is misleading, so the instinct is to fix the prompt, but the model was never shown the fact and no prompt work will help. A real hallucination is the opposite signature: the context was sufficient and the model added something unsupported. I've seen exactly this from a chunk boundary splitting a policy sentence in half.

**"ChromaDB or FAISS?"**

> Chroma by default — built-in persistence and metadata filtering, which matter day to day at the scale most projects actually run at. FAISS when retrieval genuinely outgrows a single machine or needs GPU acceleration; it's faster at millions of vectors but you're building persistence and filtering yourself. For a few hundred policy chunks, choosing FAISS is optimising a constraint you don't have.

**"What's the most common mistake you see?"**

> Tuning chunk size against retrieval scores without noticing it's a context-budget decision. Chunks compete directly with conversation history and answer length for the same window — so "more chunks improved recall" often means "and pushed the last three turns out of context". Close second: changing the embedding model without re-embedding the corpus, which doesn't crash, it just makes similarity scores meaningless.

## Next

A RAG pipeline is a tool the LLM can call — `get_payment_policy` in `fintech-support-ai-evaluator` is exactly that. [Chapter 3 — AI Agents 101](../03-ai-agents-101/README.md) is where "tool" gets defined properly, and where this pipeline's place inside a larger agent loop becomes explicit.
