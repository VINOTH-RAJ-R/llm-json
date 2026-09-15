"""Extract a usable object from language model output, or fail with evidence.

    >>> from llm_json import parse
    >>> parse('Sure!\\n```json\\n{"amount": 4200}\\n```')
    {'amount': 4200}

Four public names, and the interesting one is the exception.
"""

from __future__ import annotations

from .core import parse, try_parse
from .errors import Attempt, ParseFailed
from .telemetry import FallbackEvent, set_telemetry_hook

__all__ = [
    "Attempt",
    "FallbackEvent",
    "ParseFailed",
    "parse",
    "set_telemetry_hook",
    "try_parse",
]

__version__ = "0.1.0"
