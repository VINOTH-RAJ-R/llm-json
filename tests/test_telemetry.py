from __future__ import annotations

import dataclasses

import pytest

from llm_json import FallbackEvent, ParseFailed, parse, set_telemetry_hook, try_parse


@pytest.fixture
def events():
    captured: list[FallbackEvent] = []
    set_telemetry_hook(captured.append)
    yield captured
    set_telemetry_hook(None)


class TestWhenTheHookFires:
    def test_the_happy_path_is_silent(self, events):
        parse('{"a": 1}')
        assert events == []

    def test_a_fenced_response_reports_the_fenced_stage(self, events):
        parse('```json\n{"a": 1}\n```')
        assert [e.stage for e in events] == ["fenced"]

    def test_a_preamble_reports_the_braces_stage(self, events):
        parse('Sure:\n{"a": 1}')
        assert [e.stage for e in events] == ["braces"]

    def test_a_repaired_response_reports_the_repair_suffix(self, events):
        parse('{"a": 1,}', repair=True)
        assert [e.stage for e in events] == ["direct+repair"]

    def test_success_is_reported_as_such(self, events):
        parse('```json\n{"a": 1}\n```')
        assert events[0].succeeded is True

    def test_failure_fires_too(self, events):
        # A fallback rate computed only from successes hides the trend it
        # exists to surface.
        with pytest.raises(ParseFailed):
            parse("not json at all")
        assert len(events) == 1
        assert events[0].succeeded is False
        assert events[0].stage == "braces"

    def test_try_parse_still_reports_the_failure_it_swallows(self, events):
        assert try_parse("not json at all") is None
        assert [e.succeeded for e in events] == [False]

    def test_one_event_per_call_not_one_per_stage(self, events):
        parse('Sure:\n{"a": 1}')
        assert len(events) == 1


class TestEventContents:
    def test_raw_response_is_carried(self, events):
        text = 'Sure:\n{"a": 1}'
        parse(text)
        assert events[0].raw == text

    def test_context_is_carried_untouched(self, events):
        context = {"request_id": "req-9", "model": "some-model"}
        parse('Sure:\n{"a": 1}', context=context)
        assert events[0].context is context

    def test_context_defaults_to_none(self, events):
        parse('Sure:\n{"a": 1}')
        assert events[0].context is None

    def test_event_is_immutable(self, events):
        parse('Sure:\n{"a": 1}')
        with pytest.raises(dataclasses.FrozenInstanceError):
            events[0].stage = "tampered"


class TestHookIsolation:
    def test_a_hook_that_raises_does_not_break_parsing(self):
        def exploding_hook(event: FallbackEvent) -> None:
            raise RuntimeError("the metrics backend is down")

        set_telemetry_hook(exploding_hook)
        try:
            # A telemetry bug must never become a parse bug.
            assert parse('Sure:\n{"a": 1}') == {"a": 1}
        finally:
            set_telemetry_hook(None)

    def test_a_hook_that_raises_does_not_mask_a_genuine_failure(self):
        def exploding_hook(event: FallbackEvent) -> None:
            raise RuntimeError("the metrics backend is down")

        set_telemetry_hook(exploding_hook)
        try:
            with pytest.raises(ParseFailed):
                parse("not json at all")
        finally:
            set_telemetry_hook(None)

    def test_clearing_the_hook_stops_delivery(self):
        captured: list[FallbackEvent] = []
        set_telemetry_hook(captured.append)
        parse('Sure:\n{"a": 1}')
        set_telemetry_hook(None)
        parse('Sure:\n{"b": 2}')
        assert len(captured) == 1


class TestAggregationIsThePoint:
    def test_stage_distribution_is_countable_across_many_responses(self, events):
        responses = [
            '{"a": 1}',  # direct, silent
            '{"a": 1}',  # direct, silent
            '```json\n{"a": 1}\n```',  # fenced
            'Sure:\n{"a": 1}',  # braces
            'Sure:\n{"a": 1}',  # braces
        ]
        for response in responses:
            parse(response)

        counts: dict[str, int] = {}
        for event in events:
            counts[event.stage] = counts.get(event.stage, 0) + 1

        # Three of five responses needed a fallback; that ratio is the drift
        # signal the hook exists to produce.
        assert counts == {"fenced": 1, "braces": 2}
        assert len(events) / len(responses) == 0.6
