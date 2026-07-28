"""Structured logging - Chapter 12's Layer 1, built here rather than promised.

Chapter 12 argues that structured logging is the layer to build *first*,
because tracing, metrics, and alerting are all derived from it and none of
them can be retrofitted onto unparseable prose. This module is that argument
honoured in code: the harness already emits machine-readable events, so
Chapter 12's later layers have something to sit on.

The rule that makes it useful: **every log line carries the correlation id.**
A refund that timed out, retried, and settled produces several lines across
several modules; without a shared id, reconstructing that sequence from
production logs means guessing at timestamps.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar

#: Set per request, read by the log filter. A ContextVar rather than a global
#: so concurrent requests cannot read each other's id.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"asctime", "message", "taskName"}


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    Anything passed via ``extra=`` is merged into the object, which is what
    makes ``logger.info("harness.attempt", extra={...})`` in ``service.py``
    produce a queryable event rather than a sentence someone has to regex.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "correlation_id":
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter(
            "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s %(message)s"
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
