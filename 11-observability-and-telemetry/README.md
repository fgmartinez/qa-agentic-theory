# Chapter 11 — Observability & Telemetry for AI Systems

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 10 — CI/CD Quality Gates](../10-ci-cd-quality-gates/README.md). This is the last chapter in the current notebook — see the [README](../README.md#roadmap--not-yet-written) for what's queued next.*

Chapter 7's metrics run in CI, on a golden set, before deploy. This chapter is about the same questions — is it faithful? is retrieval good? — asked continuously, on real traffic, after deploy. Evaluation is a quality gate; observability is what tells you the gate is still holding once the system is live.

## The four-layer stack

```
Structured Logging → Trace Spans → Metrics Collection → Dashboard / Alerting
```

Each layer is buildable independently, and each one is a real, working piece of a project — not a diagram to gesture at in an interview.

### Layer 1 — Structured logging (build first)

Every pipeline call logs: the question, retrieval latency, number of chunks retrieved, generation latency, answer length, and a correlation ID that ties one request's log lines together end to end.

```python
import structlog, uuid
from functools import wraps
from time import perf_counter

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),  # JSON: compatible with Splunk/ELK
    ]
)
logger = structlog.get_logger()

def traced(operation_name: str):
    """Adds logging + timing to any function. This is the simplest
    form of tracing — Layer 2 replaces this with real spans, but
    the correlation_id pattern stays the same."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            correlation_id = kwargs.pop("correlation_id", str(uuid.uuid4())[:8])
            log = logger.bind(operation=operation_name, correlation_id=correlation_id)
            start = perf_counter()
            log.info("started")
            try:
                result = func(*args, **kwargs)
                log.info("completed", duration_ms=round((perf_counter() - start) * 1000, 2))
                return result
            except Exception as e:
                log.error("failed", duration_ms=round((perf_counter() - start) * 1000, 2), error=str(e))
                raise
        return wrapper
    return decorator
```

A privacy note that matters in a FinTech context specifically: log metadata (input hash, chunk count, latency), not full request/response content by default. `hash(pregunta) % 100000` in a log line is enough to correlate without persisting the actual customer question in plaintext logs.

### Layer 2 — Trace spans (build next)

Distributed tracing shows the full lifecycle of one request as a tree of timed spans: `embed query → vector search → LLM call → response`. Where Layer 1 tells you *that* something was slow, Layer 2 tells you *which step*.

| Component | Span |
|---|---|
| `chain.py → query_rag()` | Root span: `assistant.ask` |
| `vectorstore.py → get_retriever()` | Child span: `rag.retrieve` |
| `embeddings.py` | Child span: `rag.embed` |

Tools: OpenTelemetry (self-hosted, e.g. with Jaeger) or Langfuse (purpose-built for LLM tracing, free tier). LangChain has built-in OpenTelemetry instrumentation, which is most of the integration cost already paid for.

### Layer 3 — Metrics collection (build after tracing)

Prometheus-style counters and histograms, aggregated over time rather than per-request: requests per second, latency percentiles (p50/p95/p99), error rate, and — specific to an LLM system — hallucination rate sampled over live traffic, not just the CI golden set.

```
rag_queries_total          (counter)
retrieval_latency_ms       (histogram)
embedding_latency_ms       (histogram)
eval_pass_rate             (gauge, from a live sample)
```

### Layer 4 — Dashboard and alerting (production)

Dashboards answer "is the system healthy right now" at a glance. Two established framings for what to show:

- **RED** — Rate, Errors, Duration (request-centric; good for an API surface).
- **USE** — Utilization, Saturation, Errors (resource-centric; good for infrastructure underneath).

> **The golden rule for alerts.** Alert on symptoms that affect the user (high latency, elevated error rate), not on internal causes that may be perfectly normal (CPU spiking during a batch job isn't automatically an incident). Too many low-value alerts produce alert fatigue — the state where the one alert that matters gets ignored along with the noise.

For an AI system specifically, the dashboard extends past infrastructure health into **output quality**: faithfulness and relevancy scores sampled continuously (not 100% of traffic — too costly against a judge model), plotted over time, with an alert when the rolling average crosses below the CI threshold from Chapter 7.

## What to actually watch

| Category | Examples |
|---|---|
| Golden signals | Latency (p50/p95/p99), traffic (req/sec), error rate (%5xx), saturation |
| Business metrics | Payments completed/sec, disputes resolved/sec — a technically "green" system with payments silently failing is still an incident |
| Dependencies | DB health, queue depth / dead-letter queue size, external service latency |
| AI-specific quality | Faithfulness / relevancy sampled in production, hallucination rate trend, drift in the question distribution (users starting to ask things the corpus doesn't cover) |

## Investigating an incident

The mental sequence worth being able to say out loud in an interview:

```
1. Detect (alert fires) → 2. Bound the blast radius → 3. Mitigate
(rollback / feature flag) → 4. Diagnose (traces + logs) → 5. Blameless postmortem
```

The order matters: **mitigate before you fully understand.** If a rollback stops the bleeding, do it immediately — root cause gets investigated afterward, with the system back in a stable state, not while it's actively degraded. And the postmortem stays blameless on purpose: the goal is finding the system or process gap, not a person to blame — blaming people is *why* the next near-miss doesn't get reported.

## Drift — the failure mode unique to AI systems

A system can pass every CI gate and still degrade in production because the world it's answering questions about moved. Two forms:

- **Query drift** — users start asking things the corpus was never built to cover (a new policy nobody documented yet).
- **Score drift** — average faithfulness/relevancy trends down gradually, with no single bad deploy to point to.

Neither shows up in a one-time CI run against a static golden set — both require sampling live traffic against the same metrics over time, which is exactly what Layer 3+4 are for.

## Applied to the portfolio

The narrative this chapter supports: *"I built a RAG/agent system, evaluated it pre-deploy with DeepEval/RAGAS (Chapter 7), and designed — with Layer 1 actually implemented — the observability architecture for keeping that same evaluation signal alive in production."* Layer 1 (structured logging with `structlog`, correlation IDs) is buildable now, in an afternoon, on top of the harness from Chapters 3, 5–6 or the RAG pipeline from Chapter 2. Layers 2–4 are where the roadmap points next, and this chapter is what lets that be a specific, defensible plan instead of a hand-wave.

## Where this notebook closes, for now

Eleven chapters, one continuous story: what a model is mechanically (1), how it answers from outside knowledge (2) as a tool (3) it reasons its way into using well or badly (4), what actually has to happen once it decides to act (5–6), how to know if any of that was good (7–9), and how to keep all of it true automatically, before and after deploy (10–11). The [README](../README.md#roadmap--not-yet-written) tracks what's queued next.
