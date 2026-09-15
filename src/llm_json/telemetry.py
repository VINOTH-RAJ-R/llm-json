"""A hook that fires whenever the happy path was not enough.

The useful signal is not any single fallback — it is the rate. A pipeline that
has always resolved 2% of responses at the ``fenced`` stage and now resolves 11%
is telling you something changed: a prompt was edited, a model version rolled
underneath you, or a new input distribution arrived. That number moves before
accuracy metrics do, because accuracy is measured against labels and this is
measured against every request.

Failures fire too. A fallback rate computed only from successes hides exactly
the trend it exists to surface.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["FallbackEvent", "TelemetryHook", "emit", "set_telemetry_hook"]


@dataclass(frozen=True)
class FallbackEvent:
    """One parse that needed more than :func:`json.loads` on the raw string."""

    stage: str
    """The stage that resolved it, or the last one attempted if none did."""
    raw: str
    context: Any
    succeeded: bool


TelemetryHook = Callable[[FallbackEvent], None]

_hook: TelemetryHook | None = None


def set_telemetry_hook(fn: TelemetryHook | None) -> None:
    """Register a callable to receive every fallback event, or None to clear.

    Process-wide and intended to be set once at start-up. Reconfiguring it from
    several threads concurrently is not supported; firing is.
    """
    global _hook
    _hook = fn


def emit(event: FallbackEvent) -> None:
    """Deliver an event, swallowing anything the hook raises.

    A telemetry bug must never become a parse bug. The caller asked for their
    data back, not for observability, and the hook failing is not their problem.
    """
    hook = _hook
    if hook is None:
        return
    with contextlib.suppress(Exception):  # deliberately total
        hook(event)
