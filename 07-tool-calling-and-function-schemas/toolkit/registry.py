"""A tool registry that derives JSON Schema from Python type hints.

Every framework (OpenAI SDK, LangChain, LangGraph, MCP servers) has a version
of this. Writing one yourself once - in about 120 lines - is the fastest way
to stop treating tool calling as magic, because it makes plain that a "tool"
is nothing more than:

    a name + a description + a JSON Schema + a callable

The model never sees the callable. It sees the other three, and it emits a
JSON blob asking for the callable to be run. That is the whole mechanism.
"""

from __future__ import annotations

import inspect
import types
import typing
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, get_args, get_origin

#: Python type -> JSON Schema type. Anything not here needs an explicit
#: mapping rather than a silent fallback to "string", because a wrong schema
#: teaches the model to send the wrong shape and the failure surfaces later,
#: at call time, looking like a model problem.
_PRIMITIVES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


class ToolSchemaError(TypeError):
    """Raised at registration time for a tool that cannot be described.

    Deliberately eager: a tool with an underivable schema fails when the
    process starts, not when a customer's request happens to route to it.
    """


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]

    def as_openai_schema(self) -> dict[str, Any]:
        """The wire format most providers accept (OpenAI-style function
        calling). Anthropic's differs cosmetically - ``input_schema`` instead
        of ``parameters`` - which is exactly why the registry keeps the schema
        as data and renders it per provider rather than hard-coding one."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def as_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


def _json_type(annotation: Any, tool_name: str, param: str) -> dict[str, Any]:
    """Translate one annotation into a JSON Schema fragment."""
    if annotation in _PRIMITIVES:
        return {"type": _PRIMITIVES[annotation]}

    # Enums become a JSON Schema `enum`. This is the single highest-value
    # schema feature for reliability: an open `str` invites the model to pass
    # "refunds", "refund", "Refund policy" and hope; an enum makes the set of
    # acceptable values part of what the model is shown.
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        return {
            "type": "string",
            "enum": [member.value for member in annotation],
        }

    origin = get_origin(annotation)

    if origin is list:
        (inner,) = get_args(annotation) or (str,)
        return {"type": "array", "items": _json_type(inner, tool_name, param)}

    # Optional[X] is Union[X, None]; describe X and let `required` carry the
    # optionality, which is how JSON Schema expects it to be expressed.
    #
    # Both spellings must be handled: `Optional[str]` gives `typing.Union`,
    # while the modern `str | None` gives `types.UnionType`. They are
    # different objects, and checking only one silently rejects half the
    # type hints a real codebase contains.
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _json_type(args[0], tool_name, param)

    raise ToolSchemaError(
        f"Tool {tool_name!r}: cannot derive a JSON Schema for parameter "
        f"{param!r} of type {annotation!r}. Add an explicit mapping rather "
        f"than letting it default to string."
    )


def build_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Derive a JSON Schema object from a function's signature.

    ``additionalProperties: False`` is set deliberately. Without it a model
    may pass extra keys that are silently dropped, which hides a real
    misunderstanding of the tool - better to reject the call and see it.
    """
    signature = inspect.signature(func)
    hints = typing.get_type_hints(func)
    name = func.__name__

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in signature.parameters.items():
        if param_name in {"self", "cls"}:
            continue
        if param_name not in hints:
            raise ToolSchemaError(
                f"Tool {name!r}: parameter {param_name!r} has no type "
                f"annotation. The model is shown this schema - an unannotated "
                f"parameter is an undocumented one."
            )
        properties[param_name] = _json_type(hints[param_name], name, param_name)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


class ToolRegistry:
    """Holds the tools an agent is allowed to call.

    The registry is also the *authorisation boundary*: a tool that is not
    registered cannot be invoked, no matter what the model emits. That check
    lives in ``dispatcher.py``.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator. The docstring becomes the description the model reads."""
        doc = inspect.getdoc(func)
        if not doc:
            raise ToolSchemaError(
                f"Tool {func.__name__!r} has no docstring. The description is "
                f"how the model decides *when* to call this tool - shipping "
                f"without one is shipping a tool the model will misuse."
            )
        tool = Tool(
            name=func.__name__,
            description=doc,
            parameters=build_schema(func),
            func=func,
        )
        if tool.name in self._tools:
            raise ToolSchemaError(f"Duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool
        return func

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def as_openai_schemas(self) -> list[dict[str, Any]]:
        return [self._tools[n].as_openai_schema() for n in self.names()]

    def as_anthropic_schemas(self) -> list[dict[str, Any]]:
        return [self._tools[n].as_anthropic_schema() for n in self.names()]

    def __len__(self) -> int:
        return len(self._tools)
