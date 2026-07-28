"""Tool-calling tests.

Same discipline as Chapter 6: every one of these runs without a model. Schema
generation, argument validation, dispatch, and error shaping are all ordinary
deterministic code, and the failure modes they cover - hallucinated tool
names, wrong argument types, malformed JSON, exploding tools - are the ones
that actually break agents in production.
"""

import json
from enum import Enum

import pytest

from toolkit import (
    ToolCall,
    ToolCallStatus,
    ToolDispatcher,
    ToolRegistry,
    ToolSchemaError,
    build_schema,
    validate_arguments,
)
from toolkit.example_tools import PolicyTopic, registry


@pytest.fixture
def dispatcher() -> ToolDispatcher:
    return ToolDispatcher(registry)


def call(name: str, args: dict | str, call_id: str = "call_1") -> ToolCall:
    return ToolCall(
        id=call_id,
        name=name,
        arguments=args if isinstance(args, str) else json.dumps(args),
    )


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------
def test_schema_is_derived_from_type_hints():
    def send(recipient: str, amount: float, urgent: bool = False) -> str:
        """Send money."""

    schema = build_schema(send)
    assert schema["properties"]["recipient"] == {"type": "string"}
    assert schema["properties"]["amount"] == {"type": "number"}
    assert schema["properties"]["urgent"] == {"type": "boolean"}
    # Defaulted parameters are optional; the rest are required.
    assert schema["required"] == ["recipient", "amount"]
    assert schema["additionalProperties"] is False


def test_enum_becomes_a_json_schema_enum():
    """The highest-value schema feature for reliability."""
    schema = registry.get("get_payment_policy").parameters
    assert schema["properties"]["topic"]["enum"] == [
        "refunds",
        "chargebacks",
        "fees",
        "payout_schedule",
    ]


def test_list_annotations_become_arrays():
    def tag(labels: list[str]) -> str:
        """Tag something."""

    assert build_schema(tag)["properties"]["labels"] == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_optional_is_expressed_through_required_not_through_type():
    def maybe(note: str | None = None) -> str:
        """Optional note."""

    schema = build_schema(maybe)
    assert schema["properties"]["note"] == {"type": "string"}
    assert schema["required"] == []


def test_unannotated_parameter_is_rejected_at_registration():
    """Fail at import, not at 3am when a request routes here."""

    def broken(thing) -> str:
        """Does something."""

    with pytest.raises(ToolSchemaError, match="no type annotation"):
        build_schema(broken)


def test_undescribable_type_is_rejected_rather_than_defaulted_to_string():
    class Custom:
        pass

    def broken(thing: Custom) -> str:
        """Does something."""

    with pytest.raises(ToolSchemaError, match="cannot derive"):
        build_schema(broken)


def test_tool_without_a_docstring_is_refused():
    """The description IS the prompt. Shipping without one ships a tool the
    model will misuse."""
    local = ToolRegistry()

    with pytest.raises(ToolSchemaError, match="no docstring"):

        @local.register
        def mystery(x: int) -> int:
            return x


def test_registry_renders_both_provider_dialects():
    openai = registry.as_openai_schemas()[0]
    anthropic = registry.as_anthropic_schemas()[0]

    assert openai["type"] == "function"
    assert "parameters" in openai["function"]
    assert "input_schema" in anthropic       # same data, different key
    assert openai["function"]["name"] == anthropic["name"]


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------
SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_id": {"type": "string"},
        "count": {"type": "integer"},
        "topic": {"type": "string", "enum": ["refunds", "fees"]},
    },
    "required": ["invoice_id"],
    "additionalProperties": False,
}


def test_valid_payload_produces_no_errors():
    assert validate_arguments(SCHEMA, {"invoice_id": "INV-1"}) == []


@pytest.mark.parametrize(
    "payload,fragment",
    [
        ({}, "missing required"),
        ({"invoice_id": 42}, "expected string"),
        ({"invoice_id": "INV-1", "count": "3"}, "expected integer"),
        ({"invoice_id": "INV-1", "topic": "refund"}, "not one of"),
        ({"invoice_id": "INV-1", "surprise": 1}, "unexpected argument"),
    ],
)
def test_invalid_payloads_are_caught(payload, fragment):
    errors = validate_arguments(SCHEMA, payload)
    assert any(fragment in e for e in errors), errors


def test_boolean_is_not_accepted_as_an_integer():
    """``bool`` subclasses ``int`` in Python, so a naive isinstance check lets
    ``True`` through as a number - and ``amount=True`` becomes ``amount=1``
    somewhere downstream."""
    errors = validate_arguments(SCHEMA, {"invoice_id": "INV-1", "count": True})
    assert any("boolean" in e for e in errors)


# ---------------------------------------------------------------------------
# Dispatch - the happy path
# ---------------------------------------------------------------------------
def test_valid_call_executes_and_returns_ok(dispatcher):
    result = dispatcher.dispatch(call("get_payment_policy", {"topic": "refunds"}))
    assert result.ok
    assert "5 business days" in result.content


def test_result_is_shaped_as_a_tool_message(dispatcher):
    """This dict is literally how step 4 of the agent loop is implemented."""
    result = dispatcher.dispatch(call("check_invoice_status", {"invoice_id": "INV-1001"}))
    message = result.as_message()

    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_1"
    assert message["name"] == "check_invoice_status"
    assert json.loads(message["content"])["status"] == "paid"


def test_default_arguments_do_not_need_to_be_supplied(dispatcher):
    result = dispatcher.dispatch(call("escalate_to_human", {"reason": "angry customer"}))
    assert result.ok
    assert "normal" in result.content


# ---------------------------------------------------------------------------
# Dispatch - the failure modes that actually happen
# ---------------------------------------------------------------------------
def test_hallucinated_tool_name_is_refused_and_the_model_is_told_what_exists(dispatcher):
    """An agent told only "unknown tool" tends to invent a second one."""
    result = dispatcher.dispatch(call("issue_refund_immediately", {"amount": 500}))

    assert result.status is ToolCallStatus.UNKNOWN_TOOL
    body = json.loads(result.content)["error"]
    assert "issue_refund_immediately" in body
    assert "check_invoice_status" in body    # the alternatives


def test_malformed_json_arguments_do_not_crash_the_loop(dispatcher):
    result = dispatcher.dispatch(call("get_payment_policy", "{'topic': refunds"))
    assert result.status is ToolCallStatus.INVALID_ARGUMENTS


def test_wrong_enum_value_is_rejected_before_execution(dispatcher):
    result = dispatcher.dispatch(call("get_payment_policy", {"topic": "refund"}))
    assert result.status is ToolCallStatus.INVALID_ARGUMENTS
    assert "not one of" in json.loads(result.content)["error"]


def test_missing_required_argument_is_rejected(dispatcher):
    result = dispatcher.dispatch(call("check_invoice_status", {}))
    assert result.status is ToolCallStatus.INVALID_ARGUMENTS


def test_exploding_tool_becomes_a_result_not_an_exception(dispatcher):
    """A tool failure is information for the model, not a dead request."""
    result = dispatcher.dispatch(call("check_invoice_status", {"invoice_id": "NOPE"}))

    assert result.status is ToolCallStatus.EXECUTION_ERROR
    assert result.ok is False
    assert "KeyError" in json.loads(result.content)["error"]


def test_error_content_is_still_valid_json_for_the_model(dispatcher):
    """Every path returns something the model can parse. An error that breaks
    the model's own parsing turns one failure into two."""
    for bad in [
        call("nope", {}),
        call("get_payment_policy", "not json"),
        call("check_invoice_status", {"invoice_id": "NOPE"}),
    ]:
        result = dispatcher.dispatch(bad)
        assert "error" in json.loads(result.content)


# ---------------------------------------------------------------------------
# Parallel calls
# ---------------------------------------------------------------------------
def test_parallel_calls_preserve_order_and_ids(dispatcher):
    """One result per call id, in order - a mismatch is a hard API error on
    the next request, not a degraded answer."""
    calls = [
        call("get_payment_policy", {"topic": "fees"}, call_id="a"),
        call("check_invoice_status", {"invoice_id": "INV-1002"}, call_id="b"),
        call("get_payment_policy", {"topic": "nope"}, call_id="c"),
    ]

    results = dispatcher.dispatch_all(calls)

    assert [r.call_id for r in results] == ["a", "b", "c"]
    assert [r.ok for r in results] == [True, True, False]


def test_one_failing_call_does_not_prevent_the_others(dispatcher):
    results = dispatcher.dispatch_all(
        [
            call("nonexistent", {}, call_id="a"),
            call("get_payment_policy", {"topic": "refunds"}, call_id="b"),
        ]
    )
    assert results[0].ok is False
    assert results[1].ok is True


# ---------------------------------------------------------------------------
# The authorisation property
# ---------------------------------------------------------------------------
def test_only_registered_tools_can_ever_be_invoked():
    """The registry is the authorisation boundary.

    Whatever the model emits - through prompt injection, confusion, or a
    jailbreak - it cannot reach a callable that was never registered.
    """
    empty = ToolDispatcher(ToolRegistry())
    for name in ["get_payment_policy", "os.system", "__import__", "escalate_to_human"]:
        assert empty.dispatch(call(name, {})).status is ToolCallStatus.UNKNOWN_TOOL
