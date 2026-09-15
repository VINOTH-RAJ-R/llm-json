# Design notes

Why this library is shaped the way it is. The README says what it does; this
says what was decided and what was given up.

## The ladder has two dimensions

The original spec described a linear escalation: `direct`, then `fenced`, then
`braces`, then `repair`. Implemented literally it fails on input it has enough
information to handle:

```text
Sure, here's the analysis:
{'amount': 4200, 'currency': 'INR',}
```

`braces` isolates the object but cannot parse it — single quotes, trailing
comma. `repair` then runs against the original string with the preamble still
attached, so it cannot parse it either. Total failure on a recoverable response.

The observation that fixes it is that two independent questions were being
answered by one list:

- **Which substring is meant to be JSON?** — `direct`, `fenced`, `braces`
- **How do we fix text that is nearly JSON?** — the repairs

So extraction and repair compose rather than queue. Every extractor is tried
against the response; when `repair=True` every extractor's candidate is then
tried again repaired. About fifteen lines, strictly more capable.

Stage names stay flat strings (`"braces+repair"`) rather than becoming a pair,
because the telemetry consumer wants a single low-cardinality label to group by,
and a tuple would push that formatting decision onto every caller.

## Repairs apply to the candidate, not the response

Found by a test rather than by reasoning, which is the honest version of events.

Repairing the whole response before extracting reads the apostrophe in a
preamble like `Here's the analysis:` as opening a single-quoted string literal.
Everything up to the next quote character is swallowed, and the object that
follows is destroyed. Extraction has to narrow the text to the part that is
meant to be JSON before any transform is allowed near it.

Unrepaired candidates are all tried before any repaired one, so a faithful parse
is always preferred over a rewritten one. A response containing a valid object
followed by a single-quoted decoy resolves from the valid object.

### The limitation this creates, and why it was accepted

Ordering extraction first means the brace extractor reads strict JSON quoting,
so a single-quoted string containing a structural `}` closes the object early:

```python
parse("{'note': 'use } here'}", repair=True)         # works — direct wins
parse("Sure:\n{'note': 'use } here'}", repair=True)  # ParseFailed
```

The alternative — normalise quotes first — reintroduces the apostrophe bug on
every response with a conversational preamble. Preambles are common; single
quotes around a brace-bearing string are rare. The trade goes this way
deliberately, and `TestKnownLimitation` in `tests/test_parse.py` pins it so that
anyone who changes the ordering has to state that they meant to.

## Truncation rewinds rather than closes

The algorithm the library exists for.

A truncated response leaves the delimiter stack non-empty. The obvious recovery
is to append the closers, and it fails in the dangerous direction:

```text
{"invoice": "INV-2026-0041", "amount": 42
```

Closed naively this yields an amount of 42 where the real figure was 4200. It
parses, it validates against a schema expecting an integer, and no caller can
detect the corruption because there is no error to catch. The library has not
failed; it has lied.

So the walk records the offset immediately after every *completed* member, and
recovery rewinds there before closing what remains open. The trailing incomplete
token is discarded outright.

**The rule: an incomplete scalar is discarded, never completed.** A missing
field is a visible failure. A wrong number is an invisible one.

### What "completed" means

The walk runs a small state machine per open container — `expect_key`,
`expect_colon`, `expect_value`, `after_value` — and records a safe point only on
entry to `after_value`. That distinction is what separates these two cases:

```text
{"items": [1, 2, 3     ->  {"items": [1, 2]}    3 might have been 30
{"items": [1, 2, 3     ->  {"items": [1, 2, 3]} the space proves 3 ended
```

A terminator after a scalar is proof the scalar finished. Without one it is a
prefix of an unknown value.

An opened-but-empty container is deliberately *not* a safe point:

```python
parse('{"a": 1, "b": {')   # {'a': 1}, not {'a': 1, 'b': {}}
```

`{"b": {}}` asserts that `b` is an empty object, which is a claim the text does
not support. Dropping `b` asserts nothing about it.

### What is not guaranteed

A truncated array can come back short. Nothing in the text says how many
elements were coming, so this is inherent to truncation rather than a choice.
`Candidate.truncated` flags the outcome so a caller can treat a reconstruction
differently from a clean parse.

The guarantee that *is* made — no invented scalars — is pinned by a test that
cuts a known document at every offset and asserts every recovered value equals
the original. That test would have failed on the naive implementation.

## One scanner, three consumers

The brace extractor, the quote normaliser and the unterminated-string closer all
need the same thing: for a given character, is it structure or is it text inside
a string literal?

Each has a tempting regular-expression form, and each of those is wrong on real
input. `,\s*}` corrupts a comma inside a string value. Swapping `'` for `"`
corrupts the apostrophe in `it's`. The answer depends on quote state carried
across the whole input, which a regex cannot hold.

`scanner.py` yields `(index, char, in_string, quote, escaped, open_after)` and
every consumer reads state off it. One tested implementation of the hard part
rather than three that disagree at the edges.

`open_after` — the quote still open *after* consuming this character — is what
distinguishes a string's closing quote from an unterminated one. Both are
`in_string=True`; only the closing quote reports `open_after=None`.

## Telemetry fires on failure too

A fallback rate computed only from successes hides the trend it exists to
surface. The event carries `succeeded` so a consumer can separate them, but both
are delivered.

One event per `parse()` call, not one per stage attempted, so the count of
events over the count of calls is directly the fallback rate with no
deduplication needed at the aggregation layer.

The hook is wrapped in a total exception suppressor. The caller asked for their
data back, not for observability; a telemetry bug must never become a parse bug.

## Rejected: returning a partial result on failure

Considered and dropped. When every stage fails, `ParseFailed` carries the raw
response and nothing else — no best-effort dict, no partial object.

Returning a partial would make the failure path look like the success path, and
the entire argument of the library is that a failure should be impossible to
mistake for a result. A caller who wants best-effort behaviour has `try_parse`
with an explicit default, which is a decision they made rather than one made for
them.

## Rejected: schema validation

pydantic exists and is better at it. A library that gets you a `dict` and a
library that says what the dict must contain are different concerns, and merging
them would mean either a dependency or a worse validator.
