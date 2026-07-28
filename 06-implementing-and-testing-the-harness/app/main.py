"""The HTTP surface: ``GET /health`` and ``POST /review``.

This module is deliberately thin. It wires components together, translates
between HTTP and domain types, and owns exactly one piece of policy - what to
do when the decision layer fails - which is stated explicitly below rather
than left to a framework default.

The endpoint implements the orchestration Chapter 5's ADR-002 specified::

    request -> decision engine -> harness loop -> response

and honours Chapter 6's central constraint: **the response reflects
``next_action``, not just the original decision.** A refund that the model
proposed and the rail refused must not read as a success.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .decision import DecisionError, LLMDecisionEngine, OllamaClient, RuleBasedDecisionEngine
from .decision.engine import DecisionEngine
from .harness import InMemoryPaymentGatewayClient, ReviewHarness
from .harness.types import HarnessOutcome
from .logging_setup import configure_logging, correlation_id_var, new_correlation_id
from .schemas import (
    AttemptView,
    HealthResponse,
    ReviewAction,
    ReviewDecision,
    ReviewResponse,
    RuleId,
    TransactionCase,
)

logger = logging.getLogger("api")

settings = Settings.from_env()


def build_decision_engine(config: Settings) -> DecisionEngine:
    if config.use_llm:
        return LLMDecisionEngine(
            OllamaClient(model=config.ollama_model, base_url=config.ollama_base_url)
        )
    return RuleBasedDecisionEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)
    logger.info(
        "service.start",
        extra={"use_llm": settings.use_llm, "max_attempts": settings.max_attempts},
    )
    yield


app = FastAPI(
    title="Review Harness",
    version="1.0.0",
    description=(
        "Chapter 6 of qa-agentic-theory: a dispute-review service where the "
        "model proposes and a deterministic harness executes, observes, and "
        "corrects."
    ),
    lifespan=lifespan,
)

# Module-level singletons. The gateway holds the in-memory ledger, so it has
# to outlive a single request for idempotency to mean anything.
gateway = InMemoryPaymentGatewayClient()
decision_engine: DecisionEngine = build_decision_engine(settings)


def get_harness() -> ReviewHarness:
    return ReviewHarness(
        gateway=gateway,
        max_attempts=settings.max_attempts,
        backoff_base_seconds=settings.backoff_base_seconds,
    )


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Assign every request an id, echo it back, and bind it to the logs.

    Accepts a caller-supplied ``X-Correlation-ID`` so a trace can span more
    than this service - the cheapest possible step toward Chapter 12's
    distributed tracing layer.
    """
    incoming = request.headers.get("X-Correlation-ID")
    cid = incoming or new_correlation_id()
    token = correlation_id_var.set(cid)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
    finally:
        correlation_id_var.reset(token)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness plus the two facts that actually change behaviour: which
    gateway and which decision engine this process is running."""
    return HealthResponse(
        status="ok",
        gateway=type(gateway).__name__,
        decision_engine=decision_engine.name,
    )


@app.get("/rules")
def rules() -> dict[str, list[str]]:
    """The closed rule set, exposed.

    Publishing it is a compliance affordance, not a convenience: an auditor
    asking "what is this system allowed to decide?" gets a complete,
    machine-readable answer rather than a code walkthrough.
    """
    return {"rules": [r.value for r in RuleId]}


@app.post("/review", response_model=ReviewResponse)
def review(case: TransactionCase) -> ReviewResponse | JSONResponse:
    """Decide, execute, observe, correct - and report all four honestly."""
    cid = correlation_id_var.get()

    # --- 1. DECIDE -----------------------------------------------------
    try:
        decision = decision_engine.decide(case)
    except DecisionError as exc:
        # The one piece of policy this module owns. A decision layer that
        # failed produced no decision; the safe response is a human, not a
        # guess and not a 500 that hides the case.
        logger.warning(
            "decision.failed", extra={"case_id": case.case_id, "error": str(exc)}
        )
        return JSONResponse(
            status_code=200,
            content=ReviewResponse(
                case_id=case.case_id,
                correlation_id=cid,
                decision=ReviewDecision(
                    action=ReviewAction.ESCALATE,
                    rule_id=RuleId.ESCALATE_SUSPECTED_FRAUD,
                    amount=0.0,
                    rationale=f"Decision layer failed and was not trusted: {exc}",
                    confidence=0.0,
                ),
                executed=False,
                resolved=False,
                terminal_reason="decision_layer_failure",
                requires_human_review=True,
            ).model_dump(),
        )

    logger.info(
        "decision.made",
        extra={
            "case_id": case.case_id,
            "action": decision.action.value,
            "rule_id": decision.rule_id.value,
            "engine": decision_engine.name,
        },
    )

    # --- 2. EXECUTE (only refunds touch the rail) ----------------------
    if decision.action is not ReviewAction.REFUND:
        # REJECT and ESCALATE have no side effect to execute. Saying so
        # explicitly beats running the harness with amount=0 and pretending
        # the resulting no-op means something.
        return ReviewResponse(
            case_id=case.case_id,
            correlation_id=cid,
            decision=decision,
            executed=False,
            resolved=decision.action is ReviewAction.REJECT,
            terminal_reason=f"no_execution_required:{decision.action.value}",
            requires_human_review=decision.action is ReviewAction.ESCALATE,
        )

    outcome: HarnessOutcome = get_harness().run(
        case_id=case.case_id, amount=decision.amount
    )

    logger.info(
        "harness.finished",
        extra={
            "case_id": case.case_id,
            "terminal_reason": outcome.terminal_reason.value,
            "attempts": outcome.attempt_count,
        },
    )

    # --- 3. REPORT WHAT ACTUALLY HAPPENED ------------------------------
    return ReviewResponse(
        case_id=case.case_id,
        correlation_id=cid,
        decision=decision,
        executed=True,
        resolved=outcome.succeeded,
        terminal_reason=outcome.terminal_reason.value,
        final_status=outcome.execution.status.value,
        total_executed_amount=sum(
            a.execution.executed_amount or 0.0
            for a in outcome.attempts
            if not a.execution.replayed
        ),
        attempts=[
            AttemptView(
                number=a.number,
                requested_amount=a.command.amount,
                idempotency_key=a.command.idempotency_key,
                status=a.execution.status.value,
                executed_amount=a.execution.executed_amount,
                replayed=a.execution.replayed,
                next_action=a.next_action.value,
            )
            for a in outcome.attempts
        ],
        requires_human_review=outcome.needs_human,
    )
