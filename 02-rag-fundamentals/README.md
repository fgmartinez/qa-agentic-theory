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

`k` is a tuning knob, not a constant — it's one of the first things to sweep when Context Precision or Context Recall (Chapter 7) come back low.

### 5. Prompt grounding

The retrieved chunks get inserted into the prompt as context. This is the step that draws the line between *"answering with documentary backing"* and *"answering from the model's own intuition."* A well-grounded prompt instructs the model explicitly to answer only from the provided context and to say so plainly when the context doesn't cover the question — the alternative is a model that fills the gap with something plausible-sounding and wrong.

### 6. Generation

The LLM produces the final answer. Even with perfect retrieval, generation can still fail on its own: summarizing poorly, answering a slightly different question than the one asked, adding a detail that wasn't in the context, or dropping a disclaimer the policy requires. This is precisely why retrieval quality and generation quality get evaluated as two separate things in Chapter 7 — a good retriever paired with a careless generator still produces a bad, unfaithful answer.

## Choosing the models: generator vs. embedder

A RAG system needs two different models doing two different jobs, and conflating them is a common early mistake.

| | Generator | Embedder |
|---|---|---|
| Job | Reads context + question, writes the answer | Converts text to a vector for similarity search |
| Example (local) | `llama3.1:8b` — 8B params, ~6GB RAM, good quality/speed balance | `nomic-embed-text` — 768-dim, purpose-built for semantic similarity |
| Lighter alternative | `llama3.2:3b` — less accurate, runs on 4GB RAM | — |
| Local vs. cloud | Local (Ollama): free, private, no rate limits, weaker than frontier cloud models. Cloud (GPT-4-class): far more capable, costs per call, data leaves the machine. | Same trade-off, usually a smaller decision since embedding models are cheaper and less differentiated at the top end. |

> **The trade-off to actually understand.** An 8B local model is nowhere near GPT-4-class capability. That's fine for *generation* in a learning/portfolio context — the gap is well understood and documented. It matters more when the *same* small model is also asked to judge outputs (Chapter 7) — a weak judge is a weak signal, not just a weak answer.

## Applied to `fintech-support-ai-evaluator`

The `get_payment_policy` tool is the RAG surface of that project: a question about a payment policy triggers retrieval over the policy knowledge base, the retrieved chunks ground the answer, and the agent decides whether that's enough or whether `check_invoice_status` also needs to be called first (a multi-hop case — see Chapter 8's golden set examples).

The reference implementation already built in `clinic-ai-testing` uses exactly this pipeline (LangChain + ChromaDB + Ollama, `nomic-embed-text` embeddings, `chunk_size=250` in its `MarkdownTextSplitter`) — including a documented real failure: at that chunk size, a specific availability block gets split across a chunk boundary, which shows up as a Context Precision failure, not a hallucination. That's the diagnostic distinction Chapter 7 formalizes.

## Next

A RAG pipeline is a tool the LLM can call — `get_payment_policy` in `fintech-support-ai-evaluator` is exactly that. [Chapter 3 — AI Agents 101](../03-ai-agents-101/README.md) is where "tool" gets defined properly, and where this pipeline's place inside a larger agent loop becomes explicit.
