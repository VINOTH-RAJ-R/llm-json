from __future__ import annotations

import pytest

from llm_json.scanner import ends_inside_string, scan


def structural(text: str, *, single_quotes: bool = False) -> str:
    """The characters the scanner considers structure rather than string text."""
    tokens = scan(text, single_quotes=single_quotes)
    return "".join(t.char for t in tokens if not t.in_string)


def test_plain_object_exposes_only_its_punctuation_as_structural():
    assert structural('{"a": 1}') == "{: 1}"


def test_braces_inside_a_string_value_are_not_structural():
    assert structural('{"note": "use {} for placeholders"}') == "{: }"


def test_braces_inside_a_key_are_not_structural():
    assert structural('{"{weird}": 1}') == "{: 1}"


def test_escaped_quote_does_not_terminate_the_string():
    text = r'{"say": "he said \"hi\" loudly"}'
    assert structural(text) == "{: }"


def test_escaped_backslash_before_quote_does_terminate_the_string():
    # The backslash escapes itself, so the following quote is a real delimiter.
    text = r'{"path": "C:\\"}'
    assert structural(text) == "{: }"
    assert ends_inside_string(text) is False


def test_escaped_character_is_flagged():
    tokens = [t for t in scan(r'"a\nb"') if t.escaped]
    assert [t.char for t in tokens] == ["n"]


def test_single_quotes_are_structural_by_default():
    # Strict JSON has no single-quoted strings, so the scanner must not treat
    # an apostrophe as a delimiter unless explicitly asked to.
    assert structural("{'a': 1}") == "{'a': 1}"


def test_single_quotes_open_strings_when_enabled():
    assert structural("{'a': 1}", single_quotes=True) == "{: 1}"


def test_apostrophe_inside_a_double_quoted_string_is_not_a_delimiter():
    text = "{'note': \"it's fine\"}"
    assert structural(text, single_quotes=True) == "{: }"
    assert ends_inside_string(text, single_quotes=True) is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", False),
        ("{}", False),
        ('{"a": "closed"}', False),
        ('{"a": "open', True),
        ('{"a": "open\\"', True),  # trailing quote is escaped, string still open
        ('"', True),
        ('""', False),
    ],
)
def test_ends_inside_string(text: str, expected: bool):
    assert ends_inside_string(text) is expected


def test_open_after_distinguishes_closing_quote_from_unterminated():
    closed = list(scan('"ab"'))
    assert closed[-1].char == '"'
    assert closed[-1].in_string is True
    assert closed[-1].open_after is None

    unterminated = list(scan('"ab'))
    assert unterminated[-1].open_after == '"'


def test_every_character_is_yielded_exactly_once_in_order():
    text = '{"a": [1, "b\\"c"], "d": null}'
    tokens = list(scan(text))
    assert [t.index for t in tokens] == list(range(len(text)))
    assert "".join(t.char for t in tokens) == text
