# Chapter 12 — Observability & Telemetry for AI Systems

*Part of [qa-agentic-theory](../README.md). Previous: [Chapter 11 — CI/CD Quality Gates](../11-ci-cd-quality-gates/README.md). This is the last chapter in the current notebook — see the [README](../README.md#roadmap--not-yet-written) for what's queued next.*

Chapter 8's metrics run in CI, on a golden set, before deploy. This chapter is about the same questions — is it faithful? is retrieval good? — asked continuously, on real traffic, after deploy. Evaluation is a quality gate; observability is what tells you the gate is still holding once the system is live.

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

For an AI system specifically, the dashboard extends past infrastructure health into **output quality**: faithfulness and relevancy scores sampled continuously (not 100% of traffic — too costly against a judge model), plotted over time, with an alert when the rolling average crosses below the CI threshold from Chapter 8.

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

The narrative this chapter supports: *"I built a RAG/agent system, evaluated it pre-deploy with DeepEval/RAGAS (Chapter 8), and designed — with Layer 1 actually implemented — the observability architecture for keeping that same evaluation signal alive in production."* Layer 1 (structured logging with `structlog`, correlation IDs) is buildable now, in an afternoon, on top of the harness from Chapters 3, 5–6 or the RAG pipeline from Chapter 2. Layers 2–4 are where the roadmap points next, and this chapter is what lets that be a specific, defensible plan instead of a hand-wave.

## Worked example: one incident, traced end to end

Layer 1 is already built — Chapter 6's service emits it. Here is what it buys, using real captured output.

**02:14** — alert fires: `requires_human_review` rate jumped from 4% to 31% over 20 minutes.

**Step 1, bound the blast radius.** Filter the escalation events by `terminal_reason`:

```
escalated_budget_exhausted   2,847      ← almost all of it
escalated_by_gateway           118
escalated_uncorrectable          9
```

This is precisely why Chapter 6 gave budget exhaustion its own `TerminalReason` rather than folding it into `ESCALATE`. **The distinction between "the rail refused" and "we never got an answer" is the entire diagnosis, available in one query.** A single escalate value would have meant reading individual cases at 2am.

**Step 2, mitigate.** Gateway timeouts, not business refusals — an infrastructure problem. Raise `HARNESS_MAX_ATTEMPTS` from 3 to 5 (config, no deploy) to buy headroom while the rail recovers, and page the payments provider. Mitigate before understanding.

**Step 3, diagnose.** Pull one correlation id and read the whole life of the request:

```json
{"event":"decision.made","correlation_id":"f3153b428ef6","case_id":"C-4471","action":"refund","rule_id":"REFUND_DUPLICATE_CHARGE"}
{"event":"harness.attempt","correlation_id":"f3153b428ef6","attempt":1,"idempotency_key":"75a32b563cbb6862","status":"timeout","next_action":"retry"}
{"event":"harness.attempt","correlation_id":"f3153b428ef6","attempt":2,"idempotency_key":"75a32b563cbb6862","status":"timeout","next_action":"retry"}
{"event":"harness.attempt","correlation_id":"f3153b428ef6","attempt":3,"idempotency_key":"75a32b563cbb6862","status":"timeout","next_action":"retry"}
{"event":"harness.finished","correlation_id":"f3153b428ef6","terminal_reason":"escalated_budget_exhausted","attempts":3}
```

**Step 4, the question that actually matters.** Did any customer get double-refunded?

The idempotency key is **identical across all three attempts**, so the rail deduplicated them — at most one effect per case. That question is answerable from the logs in seconds because Chapter 6 logged the key on every attempt rather than only the case id.

> **This is what "observability" buys that "logging" doesn't.** Logging tells you something went wrong. This trail answered four distinct questions — how many, which kind, what to change, and whether customers were harmed — without attaching a debugger or guessing from timestamps. The design decisions that made it possible (a correlation id on every line, distinct terminal reasons, the idempotency key in the attempt event) were all made in Chapter 6, before there was anything to observe.

**Step 5, blameless postmortem.** The gap isn't "the provider had an outage" — that will happen again. It's that a 3-attempt budget was tuned for a healthy rail with no alert on the *approach* to exhaustion. The action item is an alert on attempt-count p95 rising, which fires before escalations spike.

## Exercises

### 1 — Design the log line

You can add one field to `harness.attempt`. Which, and why?

<details><summary>Solution</summary>

**`duration_ms`** — the strongest single addition. It separates "the rail is slow" from "the rail is down", makes p95 latency per attempt available, and is the leading indicator for the alert the postmortem above asked for. Without it you know *that* something timed out, not how close to the threshold normal traffic runs.

Strong runners-up: `gateway_reference` (reconciling against the provider's own records during a dispute) and `attempt_budget_remaining` (makes "approaching exhaustion" queryable without joining to config).

The reasoning to internalise: **the best field is the one that answers the question you'll have at 2am**, and you find it by writing the incident story first and noticing which query you couldn't run.
</details>

### 2 — Separate the two drifts

Faithfulness averaged 0.94 for six months and now sits at 0.86. No deploys in three weeks. Which drift, and how do you tell?

<details><summary>Solution</summary>

Could be either, and the distinguishing evidence is the **question distribution**, not the score.

- **Query drift:** users are asking about things the corpus doesn't cover — a new fee introduced by the business and never documented. Test by clustering recent questions and comparing against the topic distribution from six months ago. If new clusters appear with low retrieval scores, it's query drift, and the fix is *content*, not the model.
- **Score drift:** the same questions score worse. Test by re-running the static golden set against production. **If the golden set still passes at 0.94 while live traffic sits at 0.86, the system didn't change — the traffic did**, which is query drift again.

The trap: with no deploy, the instinct is "the model provider changed something". Possible, but check the cheaper explanation first. Neither drift is visible from a one-time CI run against a static set — that's exactly the gap Layers 3–4 exist to close.
</details>

### 3 — Order the build

A team has no observability and wants dashboards "because that's what management sees". Argue the order.

<details><summary>Solution</summary>

Layer 1 first, always. **A dashboard is a view over data that must already exist and already be structured.** Building dashboards over unstructured prose logs means regexing sentences into metrics — brittle, and it breaks whenever someone rewords a log message.

The concrete argument: with structured logs and correlation ids, a dashboard is an afternoon's work over a query. Without them, it's a parsing project that produces a number nobody trusts. Same for tracing — a trace is correlated events, so correlation ids are the prerequisite, not an enhancement.

The version that lands with management: *"the dashboard you're asking for is three days of work if we spend one day on log structure first, or three weeks if we don't."* And note Chapter 6's service already emits Layer 1 — the cost was near zero because it was designed in rather than retrofitted.
</details>

### 4 — Sample sensibly

Judge-scoring 100% of production traffic is too expensive. Design a sampling strategy.

<details><summary>Solution</summary>

Not uniform random — stratify by what you'd regret missing:

- **100%** of escalations and any `terminal_reason != resolved`. Low volume, highest signal, and these are the compliance-relevant cases (Chapter 10's Art. 14 chain).
- **100%** of cases matching critical golden-set patterns (legal notices, chargeback declarations).
- **~1–5%** uniform random of the happy path, for the trend line.
- **100%** of anything with an anomalously long attempt trail or unusual retrieval scores.

Two properties: the trend line stays statistically usable while the tail is fully covered, and cost scales with *interesting* traffic rather than total traffic.

The mistake to avoid is uniform sampling at a rate low enough to be affordable — at 1% uniform, a rare-but-critical failure mode is almost certainly invisible, and you've paid real money for a dataset that omits precisely the cases you built the system to handle correctly.
</details>

## Interview preparation

**"What does observability mean for an AI system specifically?"**

> The four layers are the same as any service — structured logs, traces, metrics, dashboards — but there's a fifth concern that doesn't exist elsewhere: output *quality* as a production signal. Faithfulness and relevancy sampled continuously and trended, because an AI system can be perfectly healthy on every infrastructure metric and be answering worse than it did last month. Latency and error rate won't show that. It's the same question Chapter 8 asks pre-deploy, asked continuously afterward.

**"How would you debug a production incident in your harness?"**

> Filter escalations by terminal reason first — that immediately separates "the rail refused" from "we never got an answer", which are completely different problems with different fixes. Then mitigate before diagnosing: if raising the attempt budget or rolling back stops the bleeding, do that first. Then pull one correlation id and read the whole request — decision, every attempt with its idempotency key and status, terminal reason. The question I'd care most about is whether any customer was double-refunded, and I can answer it from the logs because the idempotency key is on every attempt event: same key across retries means the rail deduplicated.

**"What's drift and why doesn't CI catch it?"**

> Two kinds. Query drift is users asking about things the corpus never covered — a new policy nobody documented. Score drift is average quality trending down with no single bad deploy. CI can't catch either, because CI runs a static golden set: the set still passes while live traffic degrades. That's the structural gap — pre-deploy evaluation tests the system against questions you thought of, and drift is by definition about the ones you didn't. Catching it needs live sampling against the same metrics over time.

**"Which layer do you build first, and why?"**

> Structured logging, always. Tracing is correlated events, metrics are aggregated events, and a dashboard is a view over both — so all three are derived from log structure and none can be retrofitted onto unparseable prose. The rule that makes it useful is a correlation id on every line, so a request that spans several modules can be reassembled with one query instead of guessing at timestamps. In the harness I built, that layer was near-free because it was designed in from the start rather than added after an incident.

**"How do you handle the cost of judging production traffic?"**

> Stratified sampling rather than uniform. 100% of escalations and non-resolved outcomes — low volume, highest signal, and they're the compliance-relevant ones. 100% of anything matching a critical pattern. A few percent of the happy path for the trend line. Uniform sampling at an affordable rate is the trap: at 1% you almost certainly never see the rare critical failure, so you've paid for a dataset that omits the cases you most needed to watch.

## Where this notebook closes, for now

Twelve chapters, one continuous story: what a model is mechanically (1), how it answers from outside knowledge (2) as a tool (3) it reasons its way into using well or badly (4), what actually has to happen once it decides to act (5–6), how it is told what it may do in the first place (7), how to know if any of that was good (8–10), and how to keep all of it true automatically, before and after deploy (11–12). The [README](../README.md#roadmap--not-yet-written) tracks what's queued next.
