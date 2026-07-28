"""LLM decision-engine tests - with no LLM in sight.

Every failure mode below is a real one seen from real models, and every one is
reproducible with a four-line fake. That is the practical lesson: the
*parsing and validation* around a model call is ordinary deterministic code
and deserves ordinary deterministic tests. Reserve the expensive, statistical
machinery of Chapter 8 for the question those tests genuinely cannot answer -
"was the decision *good*?" - and handle "was the output *well-formed and
grounded*?" right here, in milliseconds.
"""

import pytest

from app.decision.engine import DecisionError
from app.decision.llm import LLMDecisionEngine, build_prompt, parse_decision
from app.schemas import ReviewAction, RuleId, TransactionCase


class FakeLLMClient:
    """Returns a canned completion and records the prompt it was given."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        self.prompts.append(prompt)
        return self._response


class ExplodingLLMClient:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        raise ConnectionError("ollama is not running")


SAMPLE_CASE = TransactionCase(
    case_id="C-4471",
    amount=120.0,
    merchant="Example Store",
    days_since_transaction=10,
    customer_claim="Charged twice for a single order.",
    is_duplicate_charge=True,
)

VALID = """{"action": "refund", "rule_id": "REFUND_DUPLICATE_CHARGE",
            "amount": 120.0, "rationale": "Duplicate confirmed.", "confidence": 0.9}"""


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_valid_response_parses_into_a_grounded_decision():
    engine = LLMDecisionEngine(FakeLLMClient(VALID))
    decision = engine.decide(SAMPLE_CASE)

    assert decision.action is ReviewAction.REFUND
    assert decision.rule_id is RuleId.REFUND_DUPLICATE_CHARGE
    assert decision.amount == 120.0


# ---------------------------------------------------------------------------
# Formatting tolerance - what models actually return
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        VALID,
        f"```json\n{VALID}\n```",
        f"```\n{VALID}\n```",
        f"Sure! Here is my decision:\n\n{VALID}",
        f"{VALID}\n\nLet me know if you need anything else.",
        f"  \n\t{VALID}\n  ",
    ],
)
def test_parser_tolerates_the_wrappers_models_add_anyway(raw):
    """Instructed not to add prose, models add prose. Tolerate it on the way
    in - the alternative is a service that 500s on a cosmetic variation."""
    assert parse_decision(raw).rule_id is RuleId.REFUND_DUPLICATE_CHARGE


# ---------------------------------------------------------------------------
# Grounding - the hallucination defence
# ---------------------------------------------------------------------------
def test_hallucinated_rule_id_is_rejected():
    """The single most important test in this file.

    ``REFUND_GOODWILL_GESTURE`` is exactly the kind of plausible, helpful,
    entirely invented policy a model produces. It reads as authoritative and
    it does not exist. The closed enum turns that from a judgement call into a
    membership test, and this is where the test runs.
    """
    hallucinated = """{"action": "refund", "rule_id": "REFUND_GOODWILL_GESTURE",
                       "amount": 120.0, "rationale": "Seems fair."}"""

    with pytest.raises(DecisionError, match="outside the closed set"):
        parse_decision(hallucinated)


@pytest.mark.parametrize(
    "rule_value",
    [
        "refund_duplicate_charge",   # right rule, wrong case
        "REFUND_DUPLICATE",          # truncated
        "REFUND-DUPLICATE-CHARGE",   # hyphens
        "",
        None,
        123,
    ],
)
def test_near_miss_rule_ids_are_rejected_too(rule_value):
    """Near misses are more dangerous than obvious inventions, because a
    lenient parser is tempting to write. Exact membership, no normalisation."""
    import json

    raw = json.dumps(
        {"action": "refund", "rule_id": rule_value, "amount": 10.0, "rationale": "x"}
    )
    with pytest.raises(DecisionError):
        parse_decision(raw)


# ---------------------------------------------------------------------------
# Malformed output
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        "I cannot help with that request.",          # refusal, no JSON at all
        "",                                          # empty completion
        "{ this is not json }",                      # looks like JSON, isn't
        '["refund", "REFUND_DUPLICATE_CHARGE"]',     # JSON, but not an object
        '{"rule_id": "REFUND_DUPLICATE_CHARGE"}',    # missing action
        '{"action": "wire_transfer", "rule_id": "REFUND_DUPLICATE_CHARGE"}',
    ],
)
def test_malformed_output_raises_rather_than_defaulting(raw):
    """No fallback value, ever.

    A parser that returned ``ESCALATE`` here would be indistinguishable
    downstream from a model that genuinely decided to escalate - and the
    monitoring would show a healthy service quietly escalating everything.
    """
    with pytest.raises(DecisionError):
        parse_decision(raw)


def test_incoherent_decision_is_not_silently_normalised():
    """An escalation carrying money is incoherent. Rounding it down to zero
    would hide a model that has misunderstood its own output format."""
    incoherent = """{"action": "escalate", "rule_id": "ESCALATE_HIGH_VALUE",
                     "amount": 900.0, "rationale": "Too big."}"""

    with pytest.raises(DecisionError, match="incoherent"):
        parse_decision(incoherent)


def test_transport_failure_becomes_a_decision_error():
    """A dead Ollama must not surface as a raw ConnectionError three layers
    up, where nothing knows what to do with it."""
    engine = LLMDecisionEngine(ExplodingLLMClient())

    with pytest.raises(DecisionError, match="Model call failed"):
        engine.decide(SAMPLE_CASE)


# ---------------------------------------------------------------------------
# The prompt itself is production logic
# ---------------------------------------------------------------------------
def test_prompt_lists_every_allowed_rule():
    """If a rule is added to the enum but never reaches the prompt, the model
    cannot cite it and the rule is silently dead. This test makes that
    omission impossible to ship."""
    prompt = build_prompt(SAMPLE_CASE)
    for rule in RuleId:
        assert rule.value in prompt


def test_prompt_carries_every_field_the_policy_depends_on():
    prompt = build_prompt(SAMPLE_CASE)
    assert "C-4471" in prompt
    assert "120.00" in prompt
    assert "Charged twice for a single order." in prompt
    assert "is_duplicate_charge: True" in prompt


def test_engine_requests_deterministic_sampling_by_default():
    class TemperatureRecorder:
        def __init__(self):
            self.temperatures = []

        def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
            self.temperatures.append(temperature)
            return VALID

    client = TemperatureRecorder()
    LLMDecisionEngine(client).decide(SAMPLE_CASE)

    assert client.temperatures == [0.0]
