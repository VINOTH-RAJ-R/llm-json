"""The cheap extractors: the whole string, and the inside of a markdown fence.

An extractor answers one question — which substring of this response is meant
to be JSON — and answers it without attempting to parse. Parsing is the caller's
job, which is what lets the same extractor be retried with repairs applied.
"""

from __future__ import annotations

__all__ = ["extract_direct", "extract_fenced"]

_FENCE = "```"
_MAX_LANGUAGE_TAG = 20


def extract_direct(text: str) -> str | None:
    """The whole input, stripped. The happy path."""
    stripped = text.strip()
    return stripped or None


def extract_fenced(text: str) -> str | None:
    """The contents of the first markdown code fence.

    Handles a fence opened but never closed, which is not an exotic case: it is
    what a response cut off at a token limit looks like, and it is precisely
    when the caller most needs the partial content rather than a parse error.
    """
    opening = text.find(_FENCE)
    if opening == -1:
        return None

    body_start = _skip_language_tag(text, opening + len(_FENCE))
    closing = text.find(_FENCE, body_start)
    body = text[body_start:] if closing == -1 else text[body_start:closing]

    stripped = body.strip()
    return stripped or None


def _skip_language_tag(text: str, after_fence: int) -> int:
    """Move past an optional ``json``-style tag on the opening fence line.

    Only a short alphanumeric run counts as a tag. Anything longer, or carrying
    punctuation, is content that happened to follow the fence directly and must
    not be eaten.
    """
    newline = text.find("\n", after_fence)
    if newline == -1:
        return after_fence

    tag = text[after_fence:newline].strip()
    if tag and (len(tag) > _MAX_LANGUAGE_TAG or not tag.isalnum()):
        return after_fence
    return newline + 1
