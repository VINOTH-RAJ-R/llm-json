"""Optional transforms that correct common malformations.

Off by default. Repair changes the bytes the model produced, and a caller who
wants strict fidelity should be able to have it, so ``repair=True`` is an
explicit decision rather than the default.

Every transform here is quote-state aware, because every one of them has a
tempting regular-expression form that is wrong on real input::

    {'total': 4200, 'note': "it's fine",}

A pattern that swaps ``'`` for ``"`` corrupts the apostrophe in ``it's``. A
pattern that strips ``,\\s*}`` corrupts a comma inside a string value. Both
questions need the quote state that :mod:`llm_json.scanner` already tracks.
"""

from __future__ import annotations

from .scanner import scan

__all__ = [
    "close_unterminated_string",
    "normalise_quotes",
    "repair_text",
    "strip_trailing_commas",
]

_WHITESPACE = " \t\r\n"


def close_unterminated_string(text: str, *, single_quotes: bool = False) -> str:
    """Close a string literal the response ended in the middle of."""
    open_quote: str | None = None
    for token in scan(text, single_quotes=single_quotes):
        open_quote = token.open_after
    return text if open_quote is None else text + open_quote


def normalise_quotes(text: str) -> str:
    """Rewrite single-quoted string literals as double-quoted ones.

    Apostrophes inside double-quoted strings are left alone, which is the whole
    difficulty: ``{'note': "it's fine"}`` must become ``{"note": "it's fine"}``
    and not ``{"note": "it"s fine"}``.
    """
    tokens = list(scan(text, single_quotes=True))
    out: list[str] = []

    for position, token in enumerate(tokens):
        if token.quote != "'":
            out.append(token.char)
            continue

        is_delimiter = token.char == "'" and not token.escaped
        if is_delimiter:
            out.append('"')
        elif token.char == '"' and not token.escaped:
            out.append('\\"')
        elif token.char == "\\" and _escapes_an_apostrophe(tokens, position):
            continue  # an apostrophe needs no escape inside a double-quoted string
        else:
            out.append(token.char)

    return "".join(out)


def strip_trailing_commas(text: str) -> str:
    """Remove a comma that is immediately followed by ``}`` or ``]``."""
    tokens = list(scan(text))
    dropped: set[int] = set()

    for position, token in enumerate(tokens):
        if token.in_string or token.char != ",":
            continue
        if _next_structural_char(tokens, position) in ("}", "]"):
            dropped.add(position)

    return "".join(t.char for i, t in enumerate(tokens) if i not in dropped)


def repair_text(text: str) -> str:
    """Apply every repair, in the order that keeps each one's assumptions true.

    Quote normalisation runs first so the later passes see well-formed string
    boundaries; the unterminated-string close runs last so it observes the
    quote characters actually in play.
    """
    repaired = normalise_quotes(text)
    repaired = strip_trailing_commas(repaired)
    return close_unterminated_string(repaired)


def _escapes_an_apostrophe(tokens: list, position: int) -> bool:
    following = position + 1
    return (
        following < len(tokens)
        and tokens[following].char == "'"
        and tokens[following].escaped
    )


def _next_structural_char(tokens: list, position: int) -> str | None:
    for token in tokens[position + 1 :]:
        if token.in_string:
            return None
        if token.char not in _WHITESPACE:
            return token.char
    return None
