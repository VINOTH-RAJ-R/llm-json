from __future__ import annotations

import json

import pytest

from llm_json.repair import (
    close_unterminated_string,
    normalise_quotes,
    repair_text,
    strip_trailing_commas,
)


class TestTrailingCommas:
    def test_comma_before_closing_brace_is_removed(self):
        assert strip_trailing_commas('{"a": 1,}') == '{"a": 1}'

    def test_comma_before_closing_bracket_is_removed(self):
        assert strip_trailing_commas("[1, 2,]") == "[1, 2]"

    def test_comma_separated_from_the_brace_by_whitespace_is_removed(self):
        assert strip_trailing_commas('{"a": 1,\n  }') == '{"a": 1\n  }'

    def test_nested_trailing_commas_are_all_removed(self):
        assert strip_trailing_commas('{"a": [1, 2,], "b": {"c": 3,},}') == (
            '{"a": [1, 2], "b": {"c": 3}}'
        )

    def test_comma_inside_a_string_value_is_untouched(self):
        # The regex form of this transform corrupts exactly this input.
        text = '{"msg": "first, } second"}'
        assert strip_trailing_commas(text) == text

    def test_separating_commas_are_untouched(self):
        text = '{"a": 1, "b": 2}'
        assert strip_trailing_commas(text) == text


class TestQuoteNormalisation:
    def test_single_quoted_keys_and_values_become_double_quoted(self):
        assert normalise_quotes("{'a': 'hello'}") == '{"a": "hello"}'

    def test_apostrophe_inside_a_double_quoted_value_survives(self):
        # The case that rules out a regular expression.
        assert normalise_quotes("{'note': \"it's fine\"}") == ('{"note": "it\'s fine"}')

    def test_escaped_apostrophe_in_a_single_quoted_value_loses_its_escape(self):
        assert json.loads(normalise_quotes(r"{'a': 'it\'s here'}")) == {
            "a": "it's here"
        }

    def test_double_quote_inside_a_single_quoted_value_gains_an_escape(self):
        assert json.loads(normalise_quotes("{'a': 'say \"hi\"'}")) == {"a": 'say "hi"'}

    def test_already_valid_json_is_unchanged(self):
        text = '{"a": "hello", "b": "it\'s fine"}'
        assert normalise_quotes(text) == text

    def test_backslash_escapes_other_than_apostrophe_are_preserved(self):
        assert json.loads(normalise_quotes(r"{'a': 'line\nbreak'}")) == {
            "a": "line\nbreak"
        }


class TestUnterminatedStrings:
    def test_open_string_is_closed(self):
        assert close_unterminated_string('{"a": "hel') == '{"a": "hel"'

    def test_closed_string_is_untouched(self):
        text = '{"a": "hello"}'
        assert close_unterminated_string(text) == text

    def test_string_ending_on_an_escaped_quote_is_still_open(self):
        assert close_unterminated_string('{"a": "he said \\"') == (
            '{"a": "he said \\""'
        )


class TestRepairTextTogether:
    @pytest.mark.parametrize(
        ("malformed", "expected"),
        [
            (
                "{'total': 4200, 'note': \"it's fine\",}",
                {"total": 4200, "note": "it's fine"},
            ),
            ('{"a": 1, "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),
            ("{'a': 'hello'}", {"a": "hello"}),
            ("{'a': 'say \"hi\"'}", {"a": 'say "hi"'}),
        ],
    )
    def test_combined_repairs_produce_parseable_json(self, malformed, expected):
        assert json.loads(repair_text(malformed)) == expected

    def test_valid_input_passes_through_unchanged(self):
        text = '{"a": 1, "b": "it\'s fine"}'
        assert repair_text(text) == text
