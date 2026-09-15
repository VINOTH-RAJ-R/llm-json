from __future__ import annotations

import pytest

from llm_json import ParseFailed, parse, try_parse


class TestHappyPath:
    def test_clean_object(self):
        assert parse('{"amount": 4200}') == {"amount": 4200}

    def test_clean_array(self):
        assert parse('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]

    def test_surrounding_whitespace(self):
        assert parse('\n\n  {"a": 1}  \n') == {"a": 1}


class TestRealWorldMalformations:
    """Every case here is a shape seen from a production model."""

    def test_markdown_fenced_output(self):
        assert parse('```json\n{"amount": 4200}\n```') == {"amount": 4200}

    def test_untagged_fence(self):
        assert parse('```\n{"amount": 4200}\n```') == {"amount": 4200}

    def test_fence_opened_and_never_closed(self):
        assert parse('```json\n{"amount": 4200}') == {"amount": 4200}

    def test_conversational_preamble(self):
        text = 'Sure, here is the analysis:\n\n{"amount": 4200}'
        assert parse(text) == {"amount": 4200}

    def test_trailing_commentary(self):
        text = '{"amount": 4200}\n\nLet me know if you would like a breakdown.'
        assert parse(text) == {"amount": 4200}

    def test_preamble_and_commentary_and_fence_together(self):
        text = 'Here you go:\n\n```json\n{"amount": 4200}\n```\n\nHope that helps!'
        assert parse(text) == {"amount": 4200}

    def test_two_objects_returns_the_first_without_erroring(self):
        assert parse('{"a": 1}\n{"b": 2}') == {"a": 1}

    def test_braces_inside_string_values(self):
        text = '{"note": "use {} for placeholders"}'
        assert parse(text) == {"note": "use {} for placeholders"}

    def test_truncated_mid_object_recovers_completed_members_only(self):
        text = '{"invoice": "INV-2026-0041", "amount": 42'
        assert parse(text) == {"invoice": "INV-2026-0041"}


class TestRepairIsOptional:
    @pytest.mark.parametrize(
        "malformed",
        [
            '{"a": 1,}',
            "{'a': 1}",
            "{'a': 'hello'}",
            '{"a": [1, 2,],}',
        ],
    )
    def test_malformed_input_fails_without_repair(self, malformed: str):
        with pytest.raises(ParseFailed):
            parse(malformed)

    @pytest.mark.parametrize(
        ("malformed", "expected"),
        [
            ('{"a": 1,}', {"a": 1}),
            ("{'a': 1}", {"a": 1}),
            ("{'a': 'hello'}", {"a": "hello"}),
            ('{"a": [1, 2,],}', {"a": [1, 2]}),
            ("{'note': \"it's fine\"}", {"note": "it's fine"}),
        ],
    )
    def test_same_input_succeeds_with_repair(self, malformed: str, expected: dict):
        assert parse(malformed, repair=True) == expected

    def test_preamble_and_single_quotes_and_trailing_comma_together(self):
        # The case a strictly linear ladder cannot handle: extraction and
        # repair must both apply to the same response.
        text = "Sure, here's the analysis:\n{'amount': 4200, 'currency': 'INR',}"
        assert parse(text, repair=True) == {"amount": 4200, "currency": "INR"}

    def test_apostrophe_in_the_preamble_does_not_corrupt_repair(self):
        # Regression. Repairing the whole response instead of the extracted
        # candidate reads the apostrophe in "here's" as opening a single-quoted
        # string, which swallows everything up to the next quote character and
        # destroys the object. Extraction must narrow the text first.
        text = "Here's what I found, and here's the rest:\n{'amount': 4200}"
        assert parse(text, repair=True) == {"amount": 4200}

    def test_unrepaired_parse_is_preferred_over_a_repaired_one(self):
        # A valid object with a trailing single-quoted decoy after it must
        # resolve from the faithful parse, not a rewritten variant.
        assert parse("{\"a\": 1}\nnote: {'b': 2}", repair=True) == {"a": 1}


class TestFailure:
    @pytest.mark.parametrize(
        "garbage",
        [
            "",
            "   ",
            "I'm sorry, I can't help with that.",
            "<html><body>502</body></html>",
        ],
    )
    def test_unparseable_input_raises(self, garbage: str):
        with pytest.raises(ParseFailed):
            parse(garbage)

    def test_raw_response_survives_exactly(self):
        # The entire reason the library exists.
        garbage = "I'm sorry, I can't produce that.\n\nWould you like me to try again?"
        with pytest.raises(ParseFailed) as caught:
            parse(garbage)
        assert caught.value.raw == garbage

    def test_context_is_carried_through_untouched(self):
        context = {"request_id": "req-abc-123", "model": "some-model"}
        with pytest.raises(ParseFailed) as caught:
            parse("not json", context=context)
        assert caught.value.context == context

    def test_attempts_record_every_stage_tried(self):
        with pytest.raises(ParseFailed) as caught:
            parse("not json")
        stages = [a.stage for a in caught.value.attempts]
        assert stages == ["direct", "fenced", "braces"]

    def test_attempts_include_repair_stages_when_enabled(self):
        with pytest.raises(ParseFailed) as caught:
            parse("not json", repair=True)
        stages = [a.stage for a in caught.value.attempts]
        assert stages[-3:] == ["direct+repair", "fenced+repair", "braces+repair"]

    def test_last_stage_names_where_it_gave_up(self):
        with pytest.raises(ParseFailed) as caught:
            parse("not json")
        assert caught.value.last_stage == "braces"

    def test_message_abbreviates_raw_but_the_attribute_does_not(self):
        long_raw = "x" * 5000
        with pytest.raises(ParseFailed) as caught:
            parse(long_raw)
        assert len(caught.value.raw) == 5000
        assert len(str(caught.value)) < 500

    def test_attempts_unpack_as_plain_tuples(self):
        with pytest.raises(ParseFailed) as caught:
            parse("not json")
        stage, error = caught.value.attempts[0]
        assert stage == "direct"
        assert isinstance(error, str)


class TestScalarsAreNotObjects:
    @pytest.mark.parametrize("scalar", ["42", '"a string"', "true", "null", "3.14"])
    def test_a_bare_scalar_is_not_accepted_as_a_result(self, scalar: str):
        # It would parse, but it is not what the caller asked for, and letting
        # it through pushes the type error somewhere less obvious.
        with pytest.raises(ParseFailed):
            parse(scalar)


class TestTryParse:
    def test_returns_the_value_on_success(self):
        assert try_parse('{"a": 1}') == {"a": 1}

    def test_returns_none_by_default_on_failure(self):
        assert try_parse("not json") is None

    def test_returns_the_supplied_default_on_failure(self):
        sentinel = {"fallback": True}
        assert try_parse("not json", default=sentinel) is sentinel

    def test_never_raises(self):
        for garbage in ["", "nope", "{", "```", "\x00"]:
            assert try_parse(garbage, default="fallback") == "fallback"

    def test_honours_repair(self):
        assert try_parse('{"a": 1,}') is None
        assert try_parse('{"a": 1,}', repair=True) == {"a": 1}
