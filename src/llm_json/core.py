"""The escalation ladder.

The build spec for this library described a linear escalation — direct, then
fenced, then braces, then repair. Implemented literally that fails on input it
has enough information to handle::

    Sure, here's the analysis:
    {'amount': 4200, 'currency': 'INR',}

``braces`` isolates the object but cannot parse it, and ``repair`` then runs
against the original string with the preamble still attached, so it cannot
parse it either. The library reports total failure on a recoverable response.

The fix is to notice the ladder has two dimensions rather than one:

* an **extractor** decides *which substring* is supposed to be JSON —
  the whole thing, the inside of a fence, or a balanced delimiter run;
* a **repair** decides *how to fix* text that is nearly JSON.

Every extractor is tried against the original text. When ``repair=True`` every
extractor is then tried again against a repaired copy, which is what lets
preamble removal and quote normalisation apply to the same response.

Stage names stay flat strings — ``"braces"``, ``"braces+repair"`` — so the
public contract and the telemetry remain simple to aggregate.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .braces import extract_braces
from .errors import Attempt, ParseFailed
from .extractors import extract_direct, extract_fenced
from .repair import repair_text
from .telemetry import FallbackEvent, emit

__all__ = ["parse", "try_parse"]

_HAPPY_PATH = "direct"

_Extractor = Callable[[str], Optional[str]]


def _braces_text(text: str) -> str | None:
    candidate = extract_braces(text)
    return None if candidate is None else candidate.text


_EXTRACTORS: tuple[tuple[str, _Extractor], ...] = (
    ("direct", extract_direct),
    ("fenced", extract_fenced),
    ("braces", _braces_text),
)


def parse(
    text: str,
    *,
    repair: bool = False,
    context: Any = None,
) -> dict[str, Any] | list[Any]:
    """Extract a JSON object or array from a language model's output.

    Set ``repair=True`` to additionally attempt trailing-comma removal, quote
    normalisation and closing an unterminated string. ``context`` is carried
    through to :class:`~llm_json.errors.ParseFailed` and to telemetry untouched;
    a request id there is what makes a failure traceable later.

    Raises :class:`~llm_json.errors.ParseFailed` when every stage is exhausted.
    """
    attempts: list[Attempt] = []

    for stage, candidate in _candidates(text, repair=repair):
        if candidate is None:
            attempts.append(Attempt(stage, "no candidate found"))
            continue
        try:
            value = json.loads(candidate)
        except ValueError as exc:
            attempts.append(Attempt(stage, str(exc)))
            continue

        if not isinstance(value, (dict, list)):
            attempts.append(
                Attempt(
                    stage, f"parsed to {type(value).__name__}, not an object or array"
                )
            )
            continue

        if stage != _HAPPY_PATH:
            emit(FallbackEvent(stage=stage, raw=text, context=context, succeeded=True))
        return value

    last_stage = attempts[-1].stage if attempts else "none"
    emit(FallbackEvent(stage=last_stage, raw=text, context=context, succeeded=False))
    raise ParseFailed(raw=text, attempts=attempts, context=context)


def try_parse(
    text: str,
    *,
    default: Any = None,
    repair: bool = False,
    context: Any = None,
) -> Any:
    """Like :func:`parse`, but returns ``default`` instead of raising.

    Telemetry still fires, so choosing not to handle the exception does not
    also mean choosing not to see the failure rate.
    """
    try:
        return parse(text, repair=repair, context=context)
    except ParseFailed:
        return default


def _candidates(text: str, *, repair: bool):
    """Yield ``(stage, candidate)`` pairs in the order they should be tried.

    Repairs are applied to each extractor's candidate rather than to the whole
    response, and the distinction is load-bearing. Quote normalisation over the
    raw text would read the apostrophe in a preamble like "here's the analysis"
    as opening a string literal and corrupt everything after it. Extraction has
    to narrow the text to the part that is meant to be JSON before any transform
    is allowed near it.

    Unrepaired candidates are all tried first, so a faithful parse is always
    preferred over a rewritten one.
    """
    extracted = [(name, extract(text)) for name, extract in _EXTRACTORS]
    yield from extracted

    if not repair:
        return

    for name, candidate in extracted:
        repaired = None if candidate is None else repair_text(candidate)
        yield f"{name}+repair", repaired
