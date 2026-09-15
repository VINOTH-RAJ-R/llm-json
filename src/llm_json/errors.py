"""The failure type, and the evidence it carries.

The reason this library exists is mostly in this file. ``json.loads`` raises a
``JSONDecodeError`` that names a line and column in a string nobody kept, so the
usual handler degrades to::

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return None

which throws away the only artefact that would let anyone diagnose the failure
three days later: what the model actually said.
"""

from __future__ import annotations

from typing import Any, NamedTuple

__all__ = ["Attempt", "ParseFailed"]

_PREVIEW_CHARS = 200


class Attempt(NamedTuple):
    """One stage that was tried, and why it did not work.

    A plain ``(stage, error)`` tuple for any caller that wants to unpack it,
    with attribute access for callers that would rather read than index.
    """

    stage: str
    error: str


class ParseFailed(Exception):
    """Every parse strategy was exhausted.

    The raw response is attached deliberately and is never truncated on the
    instance itself; only :meth:`__str__` abbreviates it, so that a log line
    stays readable while ``err.raw`` remains complete for whoever has to work
    out what changed.
    """

    def __init__(
        self,
        raw: str,
        attempts: list[Attempt],
        context: Any = None,
    ) -> None:
        self.raw = raw
        self.attempts = attempts
        self.context = context
        self.last_stage = attempts[-1].stage if attempts else "none"
        super().__init__(str(self))

    def __str__(self) -> str:
        preview = self.raw[:_PREVIEW_CHARS]
        if len(self.raw) > _PREVIEW_CHARS:
            preview += f"... [{len(self.raw)} chars total]"
        stages = " -> ".join(a.stage for a in self.attempts) or "none"
        return (
            f"could not parse model output; gave up at {self.last_stage!r} "
            f"after trying {stages}. raw: {preview!r}"
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(last_stage={self.last_stage!r}, "
            f"attempts={len(self.attempts)}, raw_len={len(self.raw)})"
        )
