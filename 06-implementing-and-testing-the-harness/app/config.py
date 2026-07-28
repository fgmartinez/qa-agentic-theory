"""Configuration, in one place, read from the environment.

Small file, real point: every operational lever the harness has - retry
budget, backoff, whether a model is involved at all - is a named setting with
a default, not a literal buried three files deep. When an incident review asks
"how many times did it retry?", the answer should be readable in one place and
changeable without a code deploy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Frozen - config should not drift mid-process."""

    #: Loop budget. See ``ReviewHarness.max_attempts``.
    max_attempts: int = 3

    #: Linear backoff base, in seconds. 0 disables waiting.
    backoff_base_seconds: float = 0.0

    #: When False (the default), the service runs entirely on the rule engine:
    #: no model, no network, no API key. The walking skeleton works out of the
    #: box, and enabling the model is a deliberate act.
    use_llm: bool = False

    ollama_model: str = "llama3.1:8b"
    ollama_base_url: str = "http://localhost:11434"

    #: Emit one JSON object per log line instead of human-readable text.
    json_logs: bool = True

    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_attempts=int(os.getenv("HARNESS_MAX_ATTEMPTS", "3")),
            backoff_base_seconds=float(os.getenv("HARNESS_BACKOFF_BASE", "0")),
            use_llm=_env_bool("HARNESS_USE_LLM", False),
            ollama_model=os.getenv("HARNESS_OLLAMA_MODEL", "llama3.1:8b"),
            ollama_base_url=os.getenv(
                "HARNESS_OLLAMA_URL", "http://localhost:11434"
            ),
            json_logs=_env_bool("HARNESS_JSON_LOGS", True),
            log_level=os.getenv("HARNESS_LOG_LEVEL", "INFO"),
        )
