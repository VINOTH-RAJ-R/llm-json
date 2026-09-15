from __future__ import annotations

import json

import pytest

from llm_json.braces import extract_braces


def parsed(text: str):
    candidate = extract_braces(text)
    assert candidate is not None, f"no candidate extracted from {text!r}"
    return json.loads(candidate.text)


class TestLocatingTheValue:
    def test_clean_object_is_returned_unchanged(self):
        assert parsed('{"a": 1}') == {"a": 1}

    def test_clean_array_is_returned_unchanged(self):
        assert parsed("[1, 2, 3]") == [1, 2, 3]

    def test_preamble_before_the_object_is_discarded(self):
        assert parsed('Sure, here is the analysis:\n{"amount": 4200}') == {
            "amount": 4200
        }

    def test_trailing_commentary_after_the_object_is_discarded(self):
        text = '{"amount": 4200}\n\nLet me know if you need anything else!'
        assert parsed(text) == {"amount": 4200}

    def test_prose_on_both_sides_is_discarded(self):
        text = 'Here you go:\n{"ok": true}\nHope that helps.'
        assert parsed(text) == {"ok": True}

    def test_two_consecutive_objects_yield_the_first_without_erroring(self):
        assert parsed('{"a": 1}{"b": 2}') == {"a": 1}

    def test_two_objects_separated_by_prose_yield_the_first(self):
        assert parsed('{"a": 1}\nand also\n{"b": 2}') == {"a": 1}

    def test_braces_inside_a_string_value_do_not_close_the_object(self):
        text = '{"note": "use {} for placeholders"}'
        assert parsed(text) == {"note": "use {} for placeholders"}

    def test_brackets_inside_a_string_do_not_close_an_array(self):
        assert parsed('["a ] b", "c"]') == ["a ] b", "c"]

    def test_escaped_quotes_inside_a_value_survive(self):
        text = r'{"say": "he said \"hi\""}'
        assert parsed(text) == {"say": 'he said "hi"'}

    def test_a_brace_inside_a_string_before_the_object_is_not_the_start(self):
        text = 'The model said "{ not json }" and then returned {"a": 1}'
        assert parsed(text) == {"a": 1}

    def test_nested_structures_are_walked_correctly(self):
        text = '{"a": {"b": [1, {"c": 2}]}, "d": 3}'
        assert parsed(text) == {"a": {"b": [1, {"c": 2}]}, "d": 3}

    def test_complete_input_is_not_flagged_as_truncated(self):
        candidate = extract_braces('{"a": 1}')
        assert candidate is not None
        assert candidate.truncated is False

    @pytest.mark.parametrize(
        "text",
        ["", "no json here at all", "just prose, nothing structural", "42", "null"],
    )
    def test_input_with_no_structural_opener_returns_none(self, text: str):
        assert extract_braces(text) is None


class TestTruncationRecovery:
    """The guarantee: no scalar is ever invented or completed.

    A truncated container may come back short, because the text does not say
    how many members were coming. A truncated scalar is dropped outright,
    because completing it would produce a plausible wrong value rather than a
    visible absence.
    """

    def test_truncated_number_is_discarded_not_completed(self):
        # The headline case. Closing this naively reports an amount of 42
        # when the real figure was 4200, and it parses cleanly, so no caller
        # can detect the corruption.
        text = '{"invoice": "INV-2026-0041", "amount": 42'
        assert parsed(text) == {"invoice": "INV-2026-0041"}

    def test_truncated_string_value_is_discarded(self):
        assert parsed('{"a": 1, "b": "hel') == {"a": 1}

    def test_truncated_array_drops_its_last_unterminated_element(self):
        # 3 might have been the start of 30, so it cannot be trusted.
        assert parsed('{"items": [1, 2, 3') == {"items": [1, 2]}

    def test_array_element_followed_by_whitespace_is_complete_and_kept(self):
        # The whitespace proves the number ended, so 3 is trustworthy here.
        assert parsed('{"items": [1, 2, 3 ') == {"items": [1, 2, 3]}

    def test_completed_nested_object_survives_truncation_after_it(self):
        assert parsed('{"a": {"b": 2}, "c": 3') == {"a": {"b": 2}}

    def test_dangling_key_with_no_value_is_dropped(self):
        assert parsed('{"a": 1, "b":') == {"a": 1}

    def test_trailing_comma_from_truncation_is_dropped(self):
        assert parsed('{"a": 1, ') == {"a": 1}

    def test_opened_but_empty_nested_object_does_not_become_an_empty_object(self):
        # {"a": 1, "b": {} would assert that b is empty, which is a claim the
        # text does not support. Dropping b says nothing about it instead.
        assert parsed('{"a": 1, "b": {') == {"a": 1}

    def test_truncation_before_any_member_completes_returns_none(self):
        # Nothing can be salvaged without inventing a value, so the brace
        # extractor declines rather than returning {}.
        assert extract_braces('{"a": ') is None
        assert extract_braces("{") is None
        assert extract_braces('{"partial_ke') is None

    def test_recovered_output_is_flagged_as_truncated(self):
        candidate = extract_braces('{"a": 1, "b": 2')
        assert candidate is not None
        assert candidate.truncated is True

    def test_recovered_output_is_always_valid_json(self):
        complete = '{"a": {"b": [1, 2, {"c": "x"}]}, "d": "y", "e": 12345}'
        for cut in range(1, len(complete)):
            candidate = extract_braces(complete[:cut])
            if candidate is not None:
                json.loads(candidate.text)  # must not raise at any cut point

    def test_no_recovered_prefix_ever_invents_a_scalar(self):
        # Every recovered value must be one that appears, complete, in the
        # original document.
        complete = '{"amount": 4200, "rate": 18.5, "flag": true}'
        original = json.loads(complete)
        for cut in range(1, len(complete)):
            candidate = extract_braces(complete[:cut])
            if candidate is None:
                continue
            for key, value in json.loads(candidate.text).items():
                assert original[key] == value, (
                    f"cut at {cut} produced {key}={value!r}, "
                    f"but the real value was {original[key]!r}"
                )
