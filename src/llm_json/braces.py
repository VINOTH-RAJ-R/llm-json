"""Locate a JSON value inside surrounding text, and recover it when truncated.

Two jobs, one walk.

The first is finding the object at all. A response may carry a preamble
("Sure, here is the analysis:"), trailing commentary, or both. Matching from the
first ``{`` to the *last* ``}`` in the string is the usual shortcut and it is
wrong twice over: it swallows trailing prose that happens to contain a brace,
and it returns nothing at all when the response was cut off before its closing
brace ever arrived.

The second is truncation. The naive recovery is to append whatever closers are
still open, and it fails in the dangerous direction::

    {"invoice": "INV-2026-0041", "amount": 42

Closing that yields an amount of 42. The real figure was 4200. Nothing
downstream can tell, because the result parses cleanly.

So this module tracks, as it walks, the last offset at which the document had
just *completed* a member, and recovers to there. An incomplete scalar is
discarded, never completed: a missing field is a visible failure, and a wrong
number is an invisible one.

What recovery does not promise is completeness. A truncated array may come back
short, because nothing in the text says how many elements were coming. That
outcome is flagged via :attr:`Candidate.truncated` so a caller can treat a
reconstruction differently from a clean parse.
"""

from __future__ import annotations

from typing import NamedTuple

from .scanner import scan

__all__ = ["Candidate", "extract_braces"]

_CLOSER_FOR = {"{": "}", "[": "]"}
_WHITESPACE = " \t\r\n"
_VALUE_TERMINATORS = ",}] \t\r\n"

_EXPECT_KEY = "expect_key"
_EXPECT_COLON = "expect_colon"
_EXPECT_VALUE = "expect_value"
_AFTER_VALUE = "after_value"


class Candidate(NamedTuple):
    """A substring believed to be JSON, and how it was arrived at."""

    text: str
    truncated: bool
    """True when the source ended mid-document and this was reconstructed by
    rewinding to the last completed member and closing what remained open."""


class _Frame:
    """One open container and what the parser expects next inside it."""

    __slots__ = ("kind", "state")

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.state = _EXPECT_KEY if kind == "{" else _EXPECT_VALUE


def extract_braces(text: str) -> Candidate | None:
    """Return the first complete JSON value in ``text``, recovering if truncated.

    Returns None when no structural ``{`` or ``[`` is present, or when the input
    was truncated before a single member had completed and there is therefore
    nothing that can be salvaged without inventing a value.
    """
    start = _first_structural_opener(text)
    if start is None:
        return None

    stack: list[_Frame] = []
    safe_end: int | None = None
    safe_stack: tuple[str, ...] = ()
    scalar_open = False
    previous_quote: str | None = None

    for token in scan(text[start:]):
        index, char = token.index, token.char
        opened_string = previous_quote is None and token.open_after is not None
        closed_string = previous_quote is not None and token.open_after is None
        previous_quote = token.open_after

        if token.in_string:
            if opened_string and stack:
                scalar_open = False
            if closed_string and stack:
                frame = stack[-1]
                if frame.state == _EXPECT_KEY:
                    frame.state = _EXPECT_COLON
                else:
                    frame.state = _AFTER_VALUE
                    safe_end, safe_stack = index + 1, _kinds(stack)
            continue

        if scalar_open and char in _VALUE_TERMINATORS:
            scalar_open = False
            if stack:
                stack[-1].state = _AFTER_VALUE
                safe_end, safe_stack = index, _kinds(stack)

        if char in _CLOSER_FOR:
            stack.append(_Frame(char))
            continue

        if char in ("}", "]"):
            if not stack:
                break
            stack.pop()
            if not stack:
                return Candidate(text[start : start + index + 1], truncated=False)
            stack[-1].state = _AFTER_VALUE
            safe_end, safe_stack = index + 1, _kinds(stack)
            continue

        if not stack:
            continue

        frame = stack[-1]
        if char == ":":
            frame.state = _EXPECT_VALUE
        elif char == ",":
            frame.state = _EXPECT_KEY if frame.kind == "{" else _EXPECT_VALUE
        elif char not in _WHITESPACE:
            scalar_open = True

    if safe_end is None:
        return None
    return Candidate(_close(text[start : start + safe_end], safe_stack), truncated=True)


def _first_structural_opener(text: str) -> int | None:
    """Index of the first ``{`` or ``[`` that is not inside a string literal."""
    for token in scan(text):
        if not token.in_string and token.char in _CLOSER_FOR:
            return token.index
    return None


def _kinds(stack: list[_Frame]) -> tuple[str, ...]:
    return tuple(frame.kind for frame in stack)


def _close(body: str, stack: tuple[str, ...]) -> str:
    return body + "".join(_CLOSER_FOR[kind] for kind in reversed(stack))
