"""Executing a tool call the model asked for - safely.

This module is the direct ancestor of Chapter 6's harness, one level down. The
harness asks "the action executed, now what?"; the dispatcher asks the earlier
question: **"should this call run at all, and what do we tell the model if it
doesn't?"**

Three rules drive everything here:

1. **A tool call is untrusted input.** The model can emit a tool that does not
   exist, arguments of the wrong type, or arguments that are missing entirely.
   Validate before dispatch, never after.
2. **A tool failure is not a program failure.** It is *information for the
   model*. A raised exception kills the loop; a structured error result lets
   the agent read "invoice not found" and try something sensible.
3. **The error must not leak.** "Connection refused to
   postgres://user:pw@10.0.1.5" goes in the log, not into a context window
   that may be shown to a user or replayed to a third-party model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .registry import ToolRegistry

logger = logging.getLogger("toolkit.dispatcher")


class ToolCallStatus(str, Enum):
    OK = "ok"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    EXECUTION_ERROR = "execution_error"


@dataclass(frozen=True)
class ToolCall:
    """What the model emitted. ``arguments`` arrives as a JSON *string* on the
    wire, which is a detail worth preserving rather than hiding: malformed
    JSON from the model is a real and common failure, and a type that pretends
    it is already a dict cannot represent it."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    status: ToolCallStatus
    content: str

    @property
    def ok(self) -> bool:
        return self.status is ToolCallStatus.OK

    def as_message(self) -> dict[str, str]:
        """The result, shaped as the ``role: "tool"`` message that goes back
        into the conversation. This is how step 4 of the agent loop
        (Observation) is physically implemented."""
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "name": self.name,
            "content": self.content,
        }


_JSON_TYPE_CHECKS = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate_arguments(schema: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """Minimal JSON Schema check: required keys, types, enums, extra keys.

    Deliberately hand-rolled and small. In production use ``jsonschema`` or
    Pydantic - the point of writing it out here is that "the schema is
    enforced" should mean something specific to you, not be a library call you
    have never looked inside.
    """
    errors: list[str] = []
    properties: dict[str, Any] = schema.get("properties", {})

    for key in schema.get("required", []):
        if key not in payload:
            errors.append(f"missing required argument: {key!r}")

    for key, value in payload.items():
        if key not in properties:
            if not schema.get("additionalProperties", True):
                errors.append(f"unexpected argument: {key!r}")
            continue

        spec = properties[key]
        expected = spec.get("type")
        checker = _JSON_TYPE_CHECKS.get(expected)

        # bool is a subclass of int in Python; without this, True passes as an
        # integer and a downstream `amount=True` becomes `amount=1`.
        if expected in {"integer", "number"} and isinstance(value, bool):
            errors.append(f"{key!r}: expected {expected}, got boolean")
            continue

        if checker and not isinstance(value, checker):
            errors.append(
                f"{key!r}: expected {expected}, got {type(value).__name__}"
            )
            continue

        if "enum" in spec and value not in spec["enum"]:
            errors.append(
                f"{key!r}: {value!r} is not one of {spec['enum']}"
            )

    return errors


class ToolDispatcher:
    """Validates and executes tool calls against a registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def dispatch(self, call: ToolCall) -> ToolResult:
        # --- 1. Does this tool exist? ---------------------------------
        tool = self._registry.get(call.name)
        if tool is None:
            # A hallucinated tool name. Note the response tells the model what
            # *does* exist - an agent that gets "unknown tool" with no
            # alternatives tends to invent another one.
            return self._error(
                call,
                ToolCallStatus.UNKNOWN_TOOL,
                f"No tool named {call.name!r}. Available tools: "
                f"{', '.join(self._registry.names())}.",
            )

        # --- 2. Is the payload even JSON? -----------------------------
        try:
            payload = json.loads(call.arguments or "{}")
        except json.JSONDecodeError as exc:
            return self._error(
                call,
                ToolCallStatus.INVALID_ARGUMENTS,
                f"Arguments were not valid JSON: {exc.msg}.",
            )

        if not isinstance(payload, dict):
            return self._error(
                call,
                ToolCallStatus.INVALID_ARGUMENTS,
                "Arguments must be a JSON object.",
            )

        # --- 3. Does it match the schema? -----------------------------
        errors = validate_arguments(tool.parameters, payload)
        if errors:
            return self._error(
                call,
                ToolCallStatus.INVALID_ARGUMENTS,
                "Invalid arguments: " + "; ".join(errors) + ".",
            )

        # --- 4. Run it -------------------------------------------------
        try:
            output = tool.func(**payload)
        except Exception as exc:
            # The tool blew up. That is information for the model, not a
            # reason to kill the request - but the model gets a summary, and
            # the operator gets the detail.
            logger.exception(
                "tool.failed", extra={"tool": call.name, "call_id": call.id}
            )
            return self._error(
                call,
                ToolCallStatus.EXECUTION_ERROR,
                f"{call.name} failed: {type(exc).__name__}. "
                f"Do not retry with identical arguments.",
            )

        return ToolResult(
            call_id=call.id,
            name=call.name,
            status=ToolCallStatus.OK,
            content=output if isinstance(output, str) else json.dumps(output, default=str),
        )

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Execute a batch of parallel tool calls, preserving order.

        Order matters even when execution is conceptually parallel: most APIs
        require one ``role: "tool"`` message per call id, and a mismatch
        between calls issued and results returned is a hard error on the next
        request rather than a degraded answer.
        """
        return [self.dispatch(call) for call in calls]

    @staticmethod
    def _error(call: ToolCall, status: ToolCallStatus, message: str) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            name=call.name,
            status=status,
            content=json.dumps({"error": message}),
        )
