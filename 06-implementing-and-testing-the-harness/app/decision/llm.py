"""An LLM-backed decision engine - and the validation that makes it safe.

Most of this file is not the model call. That is the lesson. The call itself
is four lines; everything around it exists because a model's output is
*untrusted input* and has to be treated with the same suspicion as a request
body from the public internet.

The pipeline:

    case -> prompt -> model -> raw text -> JSON -> validated ReviewDecision
                                   ^          ^            ^
                                   |          |            └─ closed-enum grounding
                                   |          └─ fenced-block / prose tolerance
                                   └─ the only part people usually think about

Every arrow can fail, and each failure raises ``DecisionError`` rather than
returning a plausible default. Chapter 10's hallucination defence is exactly
the third arrow: the model cannot invent a policy, because a rule id outside
``RuleId`` fails a membership test before it can reach a payment rail.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from ..schemas import ReviewAction, ReviewDecision, RuleId, TransactionCase
from .engine import DecisionError

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMClient(Protocol):
    """The narrowest possible model interface: text in, text out.

    Kept this small on purpose. A wider interface (streaming, tool calls,
    token counts) would make the decision engine harder to fake in tests for
    no benefit here - this engine needs exactly one completion.
    """

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str: ...


SYSTEM_PROMPT = """\
You are a transaction dispute reviewer for a payments company.

Decide what to do with the disputed transaction described below, and cite
exactly one rule from the allowed list. You may not invent rules.

ALLOWED RULES (use the identifier verbatim):
{rule_catalogue}

POLICY:
- Fraud signals present  -> escalate, ESCALATE_SUSPECTED_FRAUD
- More than {window} days old -> reject, REJECT_OUTSIDE_WINDOW
- More than {repeat} prior disputes -> escalate, ESCALATE_REPEAT_DISPUTER
- Amount above {high:.2f} -> escalate, ESCALATE_HIGH_VALUE
- Confirmed duplicate charge -> refund, REFUND_DUPLICATE_CHARGE
- Amount at or below {low:.2f} -> refund, AUTO_APPROVE_LOW_VALUE
- Otherwise, a genuine service failure -> refund, REFUND_SERVICE_FAILURE

Respond with a single JSON object and nothing else:
{{"action": "refund|reject|escalate",
  "rule_id": "<one identifier from the allowed list>",
  "amount": <number, 0 unless action is refund>,
  "rationale": "<one sentence>",
  "confidence": <number between 0 and 1>}}

CASE:
  case_id: {case_id}
  amount: {amount:.2f} {currency}
  merchant: {merchant}
  days_since_transaction: {days}
  prior_disputes: {priors}
  is_duplicate_charge: {duplicate}
  fraud_signals: {fraud}
  customer_claim: {claim}
"""


def build_prompt(case: TransactionCase) -> str:
    """Render the decision prompt for one case.

    Split out from ``decide`` so it can be tested, diffed, and version-pinned
    on its own. A prompt is a piece of production logic - it deserves the same
    treatment as any other function, not to be buried as an f-string inside a
    network call. Chapter 4 covers what makes the content of this prompt work;
    this function is about making it *maintainable*.
    """
    from .rules import (
        HIGH_VALUE_THRESHOLD,
        LOW_VALUE_THRESHOLD,
        REFUND_WINDOW_DAYS,
        REPEAT_DISPUTER_THRESHOLD,
    )

    return SYSTEM_PROMPT.format(
        rule_catalogue="\n".join(f"  - {r.value}" for r in RuleId),
        window=REFUND_WINDOW_DAYS,
        repeat=REPEAT_DISPUTER_THRESHOLD,
        high=HIGH_VALUE_THRESHOLD,
        low=LOW_VALUE_THRESHOLD,
        case_id=case.case_id,
        amount=case.amount,
        currency=case.currency,
        merchant=case.merchant,
        days=case.days_since_transaction,
        priors=case.prior_disputes,
        duplicate=case.is_duplicate_charge,
        fraud=case.fraud_signals or "none",
        claim=case.customer_claim,
    )


def parse_decision(raw: str) -> ReviewDecision:
    """Turn raw model text into a validated ``ReviewDecision``.

    Separated from the network call so every parsing edge case can be tested
    without a model: fenced blocks, leading prose, hallucinated rule ids,
    wrong types. These are the cases that actually break in production, and
    none of them need an LLM to reproduce.

    Raises
    ------
    DecisionError
        On anything that is not a valid, grounded decision.
    """
    cleaned = _FENCE.sub("", raw.strip())

    # Models routinely wrap JSON in explanation despite being told not to.
    # Tolerate it on the way in; do not tolerate anything that follows.
    match = _JSON_BLOCK.search(cleaned)
    if match is None:
        raise DecisionError(f"No JSON object found in model output: {raw[:200]!r}")

    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise DecisionError(f"Model output was not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise DecisionError("Model output JSON was not an object")

    raw_rule = payload.get("rule_id")
    if raw_rule not in {r.value for r in RuleId}:
        # THE grounding check. A model that invents 'REFUND_GOODWILL_GESTURE'
        # gets stopped here, before anything touches a payment rail. This is
        # a membership test, not a judgement call - which is why it can gate
        # a CI build (Chapter 11).
        raise DecisionError(
            f"Model cited a rule outside the closed set: {raw_rule!r}. "
            f"Allowed: {sorted(r.value for r in RuleId)}"
        )

    raw_action = payload.get("action")
    if raw_action not in {a.value for a in ReviewAction}:
        raise DecisionError(f"Model returned an unknown action: {raw_action!r}")

    try:
        decision = ReviewDecision(
            action=ReviewAction(raw_action),
            rule_id=RuleId(raw_rule),
            amount=float(payload.get("amount") or 0.0),
            rationale=str(payload.get("rationale", ""))[:2000],
            confidence=float(payload.get("confidence", 1.0)),
        )
    except (TypeError, ValueError) as exc:
        raise DecisionError(f"Model output failed schema validation: {exc}") from exc

    # Cross-field consistency: a non-refund that carries an amount is
    # incoherent, and an incoherent decision must not be quietly normalised
    # into a coherent-looking one.
    if decision.action is not ReviewAction.REFUND and decision.amount > 0:
        raise DecisionError(
            f"Action {decision.action.value!r} carries a non-zero amount "
            f"({decision.amount}) - refusing to normalise an incoherent decision."
        )

    return decision


class LLMDecisionEngine:
    """Decision engine backed by a text-completion model.

    ``temperature`` defaults to ``0.0`` for the reason Chapter 1 gives: a
    non-deterministic decision layer makes every downstream metric noisy, and
    a case that approves on Tuesday and escalates on Wednesday is not
    auditable.
    """

    name = "llm"

    def __init__(self, client: LLMClient, temperature: float = 0.0) -> None:
        self._client = client
        self._temperature = temperature

    def decide(self, case: TransactionCase) -> ReviewDecision:
        prompt = build_prompt(case)
        try:
            raw = self._client.complete(prompt, temperature=self._temperature)
        except DecisionError:
            raise
        except Exception as exc:  # transport failure, timeout, bad key
            raise DecisionError(f"Model call failed: {exc}") from exc
        return parse_decision(raw)


class OllamaClient:
    """Minimal Ollama adapter - the local, zero-cost default from Chapter 1.

    Requires a running Ollama (``ollama serve``) and the model pulled. Not
    exercised by the test suite on purpose: tests that need a decision use
    ``RuleBasedDecisionEngine`` or a fake ``LLMClient``, so the suite stays
    fast, offline, and deterministic.
    """

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        import httpx

        response = httpx.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["response"]
