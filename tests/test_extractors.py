from __future__ import annotations

import pytest

from llm_json.extractors import extract_direct, extract_fenced


class TestDirect:
    def test_returns_the_stripped_input(self):
        assert extract_direct('  {"a": 1}\n') == '{"a": 1}'

    @pytest.mark.parametrize("text", ["", "   ", "\n\t "])
    def test_blank_input_yields_nothing(self, text: str):
        assert extract_direct(text) is None


class TestFenced:
    def test_json_tagged_fence(self):
        text = '```json\n{"a": 1}\n```'
        assert extract_fenced(text) == '{"a": 1}'

    def test_untagged_fence(self):
        text = '```\n{"a": 1}\n```'
        assert extract_fenced(text) == '{"a": 1}'

    def test_fence_with_prose_around_it(self):
        text = 'Here is the result:\n\n```json\n{"a": 1}\n```\n\nAnything else?'
        assert extract_fenced(text) == '{"a": 1}'

    def test_fence_opened_but_never_closed(self):
        # What a response truncated at a token limit actually looks like.
        text = '```json\n{"a": 1, "b": 2'
        assert extract_fenced(text) == '{"a": 1, "b": 2'

    def test_first_fence_wins_when_several_are_present(self):
        text = '```json\n{"a": 1}\n```\nand\n```json\n{"b": 2}\n```'
        assert extract_fenced(text) == '{"a": 1}'

    def test_content_immediately_after_the_fence_is_not_eaten_as_a_tag(self):
        text = '```{"a": 1}```'
        assert extract_fenced(text) == '{"a": 1}'

    def test_long_first_line_is_treated_as_content_not_a_language_tag(self):
        text = '```\n{"a": 1}\n```'
        assert extract_fenced(text) == '{"a": 1}'

    def test_no_fence_yields_nothing(self):
        assert extract_fenced('{"a": 1}') is None

    def test_empty_fence_yields_nothing(self):
        assert extract_fenced("```\n\n```") is None
