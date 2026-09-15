# llm-json

[![ci](https://github.com/VINOTH-RAJ-R/llm-json/actions/workflows/ci.yml/badge.svg)](https://github.com/VINOTH-RAJ-R/llm-json/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-MIT-green)](LICENSE)

Extract a usable object from language model output, or fail with the raw
response attached.

Zero runtime dependencies.

## The problem

You asked for JSON. Most of the time you get JSON. The rest of the time you get
one of these, and each one is a different `json.JSONDecodeError`:

````text
```json                              a markdown fence
{"amount": 4200}
```

Sure, here is the analysis:          a conversational preamble
{"amount": 4200}

{"amount": 4200}                     trailing commentary
Hope that helps!

{"invoice": "INV-41", "amount": 42   truncated at a token limit

{'amount': 4200, 'currency': 'INR',} single quotes and a trailing comma

{"a": 1}{"b": 2}                     two objects when you asked for one
````

The usual handling is this:

```python
try:
    data = json.loads(response)
except json.JSONDecodeError:
    return None
```

which throws away the only artefact that would let anyone work out what
happened: what the model actually said.

## Install

```bash
pip install git+https://github.com/VINOTH-RAJ-R/llm-json
```

## Quickstart

```python
from llm_json import parse, try_parse, ParseFailed

parse('```json\n{"amount": 4200}\n```')  # {'amount': 4200}
parse('Sure!\n{"amount": 4200}\nHope that helps')  # {'amount': 4200}
parse("{'amount': 4200,}", repair=True)  # {'amount': 4200}

try_parse("not json", default={})  # {} — never raises

try:
    parse(response, context={"request_id": req_id})
except ParseFailed as err:
    log.error("unparseable", raw=err.raw, stage=err.last_stage, ctx=err.context)
```

## How it escalates

The ladder has two dimensions rather than one. An **extractor** decides which
substring of the response is meant to be JSON. A **repair** decides how to fix
text that is nearly JSON. Every extractor is tried against the response, and
then — only when `repair=True` — against a repaired copy of its own candidate.

| Stage | What it does | What it catches |
|---|---|---|
| `direct` | `json.loads` on the stripped string | The happy path |
| `fenced` | Takes the inside of the first markdown fence, closed or not | Fenced output, and fences cut off at a token limit |
| `braces` | Scans from the first structural `{` or `[` to its balanced close, tracking string and escape state | Preamble, trailing commentary, two objects, **truncation** |
| `…+repair` | Retries each candidate with trailing commas removed, quotes normalised and an open string closed | Single-quoted JSON, trailing commas, cut-off strings |
| fail | Raises `ParseFailed` carrying `.raw`, `.last_stage`, `.attempts`, `.context` | Everything else |

Unrepaired candidates are all tried before any repaired one, so a faithful parse
is always preferred over a rewritten one.

### Why the repair applies to the candidate, not the response

Repairing the whole response first looks simpler and is wrong. Quote
normalisation over this input:

```text
Here's the analysis:
{'amount': 4200}
```

reads the apostrophe in `Here's` as opening a string literal, swallows
everything up to the next quote character, and destroys the object. Extraction
has to narrow the text before any transform is allowed near it.

## Truncation, and the number that would have been wrong

This is the case worth reading the source for.

A response cut off at a token limit leaves delimiters open. The obvious recovery
is to append them:

```text
{"invoice": "INV-2026-0041", "amount": 42
```

Close that naively and you get `{"invoice": "INV-2026-0041", "amount": 42}`. It
parses. It validates. It reports an amount of **42** when the real figure was
**4200**, and nothing downstream can tell, because there is no error to catch.

So the scanner records the last offset at which a member had *completed*, and
rewinds to it before closing:

```python
parse('{"invoice": "INV-2026-0041", "amount": 42')
# {'invoice': 'INV-2026-0041'}
```

The amount is absent. Your schema validation catches an absence immediately. It
would never have caught ₹42.

**The guarantee**: no scalar is ever invented or completed. A value that comes
back is a value that appeared, complete, in the response.

**Not guaranteed**: a truncated array may come back short, because nothing in
the text says how many elements were coming. That is inherent to truncation
rather than a choice, and the test suite pins the guarantee by cutting a known
document at every offset and checking that every recovered value matches the
original.

## Why the raw response matters

Six weeks after deployment, extraction starts failing for about one request in
forty. Here is the difference the exception makes.

**Without:**

```
ERROR  extraction failed for request req-8813
```

You know something broke. You do not know what the model said, so you cannot
tell whether the prompt drifted, the model version changed, the input was
unusual, or your parser has a bug. The response is gone. You add logging and
wait for it to happen again.

**With:**

```python
except ParseFailed as err:
    log.error("extraction failed",
              raw=err.raw,          # the full response, exactly as received
              stage=err.last_stage, # where it gave up
              attempts=err.attempts,# every stage tried, and why each failed
              ctx=err.context)      # your request id, model, prompt version
```

```
ERROR  extraction failed  stage=braces
       raw='I can only provide this information if you confirm you are
            authorised to access invoice data.'
```

The model refused. No parser change would have helped, and you know that in
thirty seconds instead of a week.

`__str__` abbreviates to 200 characters so a log line stays readable. `err.raw`
is never truncated.

## Telemetry, and fallback rate as a drift signal

```python
from llm_json import set_telemetry_hook


def on_fallback(event):
    metrics.increment(
        "llm_json.fallback", tags={"stage": event.stage, "ok": event.succeeded}
    )


set_telemetry_hook(on_fallback)
```

The hook fires whenever any stage beyond `direct` was reached, successes and
failures alike.

No single event is interesting. **The rate is.** A pipeline that has always
resolved 2% of responses at `fenced` and now resolves 11% is telling you that
something changed upstream — a prompt edit, a model version rolled underneath
you, a new input distribution. That number moves *before* accuracy metrics do,
because accuracy is measured against labels you collect slowly and this is
measured against every request you serve.

A shift in which *stage* resolves is more diagnostic than the total. A jump in
`fenced` usually means prompt or formatting drift. A jump in `braces` means the
model has started talking around the answer. A jump in truncated recoveries
means responses are hitting the token ceiling and your `max_tokens` needs
raising before anyone notices missing fields.

The hook is wrapped so anything it raises is swallowed. A telemetry bug must
never become a parse bug.

## Non-goals

Deliberately absent, so the scope is a decision rather than an omission:

- **No schema validation.** Use pydantic. This library gets you a `dict`; what
  that dict ought to contain is a separate concern with better tools.
- **No streaming.** Partial parsing of a live stream is a different problem with
  different tradeoffs.
- **No LLM calls.** It never touches the network and has no opinion on your
  provider.
- **No dependencies.** CI installs the built wheel into a bare environment and
  fails if anything else appears.

### Known limitation

One input shape is not recovered: a single-quoted string containing a structural
`}` or `]`, **and** surrounding prose.

```python
parse("{'note': 'use } here'}", repair=True)  # works
parse("Sure:\n{'note': 'use } here'}", repair=True)  # ParseFailed
```

Either condition alone is fine. Together they are not, and the reason is the
ordering trade-off above. Without prose, `direct` hands the whole string to
quote normalisation, which then sees the brace is inside a string. With prose,
extraction must run first, and the brace extractor — reading strict JSON quoting
— treats that brace as structure and closes early.

Fixing it would mean normalising quotes before extraction, which reintroduces
the apostrophe bug on every response with a preamble. That is a far more common
input than this one, so the trade goes this way deliberately. Double-quoted
equivalents are handled correctly in all positions.

## Design notes

[DESIGN.md](DESIGN.md) records why the ladder is shaped the way it is, why
truncation rewinds rather than closes, and why one scanner is shared by three
consumers.

## Licence

MIT. See [LICENSE](LICENSE).
