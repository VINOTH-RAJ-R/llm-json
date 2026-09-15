"""A character scanner that knows when it is inside a string literal.

Three separate problems in this library reduce to the same question: for a given
character, is it structural, or is it text inside a string?

    {"note": "use {} for placeholders"}   the inner braces are not structure
    {'total': "it's fine"}                the apostrophe is not a quote
    {"label": "unterminated               the string never closes

A regular expression cannot answer that question, because the answer depends on
quote state carried across the whole input. Rather than write three subtly
different ad-hoc loops, every consumer walks the text through :func:`scan` and
reads the state off each token.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import NamedTuple

__all__ = ["Token", "ends_inside_string", "scan"]

_DOUBLE = '"'
_SINGLE = "'"
_BACKSLASH = "\\"


class Token(NamedTuple):
    """One character of the input, tagged with the state it was read in."""

    index: int
    char: str
    in_string: bool
    """True when this character belongs to a string literal, delimiting quotes
    included. Structural characters are the ones where this is False."""
    quote: str | None
    """The quote character delimiting the string this character belongs to, or
    None when the character is structural."""
    escaped: bool
    """True when this character was consumed as the target of a backslash."""
    open_after: str | None
    """The quote left open once this character has been consumed. None means the
    scanner is back outside a string; the closing quote of a literal reports
    None here, which is what distinguishes it from an unterminated one."""


def scan(text: str, *, single_quotes: bool = False) -> Iterator[Token]:
    """Walk ``text`` character by character, tracking string and escape state.

    Set ``single_quotes`` to treat ``'`` as a string delimiter as well. Strict
    JSON has no single-quoted strings, so this is off by default and enabled
    only by the repair stage, which has to understand malformed input in order
    to correct it.
    """
    quote: str | None = None
    pending_escape = False

    for index, char in enumerate(text):
        if quote is None:
            if char == _DOUBLE or (single_quotes and char == _SINGLE):
                quote = char
                yield Token(index, char, True, quote, False, quote)
            else:
                yield Token(index, char, False, None, False, None)
            continue

        if pending_escape:
            pending_escape = False
            yield Token(index, char, True, quote, True, quote)
            continue

        if char == _BACKSLASH:
            pending_escape = True
            yield Token(index, char, True, quote, False, quote)
            continue

        if char == quote:
            yield Token(index, char, True, quote, False, None)
            quote = None
            continue

        yield Token(index, char, True, quote, False, quote)


def ends_inside_string(text: str, *, single_quotes: bool = False) -> bool:
    """True when ``text`` finishes with a string literal still open.

    Used by the repair stage to decide whether an unterminated string is the
    only thing standing between the input and a successful parse.
    """
    open_after: str | None = None
    for token in scan(text, single_quotes=single_quotes):
        open_after = token.open_after
    return open_after is not None
