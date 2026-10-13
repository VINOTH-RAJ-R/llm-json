# llm-json

[![ci](https://github.com/VINOTH-RAJ-R/llm-json/actions/workflows/ci.yml/badge.svg)](https://github.com/VINOTH-RAJ-R/llm-json/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)

Extract a usable object from language model output, or fail with the raw response attached. Zero runtime dependencies.

## The problem

You asked a model for JSON. Most of the time you get it. The rest of the time you get this:

````text
Sure, here's the analysis:

```json
{"amount": 4200, "currency": "INR"}
```
````

Or a response that stops mid-object because it hit a token limit. Or single quotes. Or two objects when you asked for one.

The usual handling throws away the one thing you need later:

```python
try:
    data = json.loads(response)
except json.JSONDecodeError:
    return None      # what did the model actually say?
```

Three days after the incident, `expecting value at line 1 column 1` tells you nothing. The raw text tells you the model started apologising instead of answering.

## Install

```bash
pip install llm-json
```

## Quickstart

```python
from llm_json import parse, try_parse, ParseFailed

data = parse(response_text)                      # raises ParseFailed
data = parse(response_text, repair=True)         # also attempts repairs
data = try_parse(response_text, default={})      # never raises

try:
    data = parse(response_text, context={"prompt": "extract_v3"})
except ParseFailed as e:
    log.warning("parse failed",
                stage=e.last_stage,   # where it gave up
                raw=e.raw,            # the actual response
                context=e.context)
```

## How it escalates

| Stage | What it does | What it catches |
|---|---|---|
| `direct` | `json.loads` on the stripped text | The happy path |
| `fenced` | Strips markdown fences, retries | ` ```json ` wrapping, including unclosed fences |
| `braces` | Scans from the first `{` or `[` to its balanced close, string- and escape-aware | Preamble, trailing prose, truncation |

With `repair=True`, each stage also retries against a repaired copy of its own candidate: trailing commas removed, single quotes normalised, one unterminated string closed. Unrepaired candidates are always tried first.

## Truncation

When a response is cut off mid-object, the scanner rewinds to the last completed member rather than appending closing delimiters.

That matters for one specific reason. A response truncated inside the number `4200` would, under a closing strategy, come back as `42` — valid JSON, plausible, and wrong. This library drops the incomplete member instead. No scalar is ever invented or completed.

Truncated arrays may therefore come back short. That is the intended trade: missing data announces itself, wrong data does not.

## Telemetry

```python
from llm_json import set_telemetry_hook

def on_fallback(event):
    metrics.increment("llm_json.fallback", tags={"stage": event.stage})

set_telemetry_hook(on_fallback)
```

The hook fires whenever a stage beyond `direct` was reached, on failure as well as success. Tracked over time, a rising fallback rate is an early signal that a prompt is drifting, a model version changed underneath you, or responses are hitting a token limit. It usually moves before accuracy metrics do.

A hook that raises cannot break parsing.

## Non-goals

No schema validation — use pydantic on the result. No streaming. No LLM calls. No dependencies.

There is one known input this does not recover: a single-quoted string containing a structural `}` or `]`, with prose around the object. [Why that was accepted](DESIGN.md#the-limitation-this-creates-and-why-it-was-accepted).

## Design notes

[DESIGN.md](DESIGN.md) covers the decisions behind the ladder, why repairs apply to the candidate rather than the whole response, how truncation recovery works in detail, and two approaches that were considered and rejected.

## Licence

MIT.
