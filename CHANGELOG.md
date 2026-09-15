# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-15

First release.

### Added

- `parse(text, *, repair=False, context=None)` — escalates through extraction
  stages and raises `ParseFailed` when all of them are exhausted.
- `try_parse(text, *, default=None, repair=False, context=None)` — never raises.
- `ParseFailed` carrying `.raw`, `.last_stage`, `.attempts` and `.context`. The
  raw response is stored complete; only the string form abbreviates it.
- `set_telemetry_hook(fn)` — receives a `FallbackEvent` whenever any stage
  beyond `direct` was reached, on failure as well as success.
- Extraction stages `direct`, `fenced` and `braces`, each retried against a
  repaired copy of its own candidate when `repair=True`.
- Truncation recovery that rewinds to the last completed member rather than
  appending closing delimiters, so an incomplete scalar is discarded rather
  than turned into a plausible wrong value.
- Optional repairs: trailing-comma removal, single-to-double quote
  normalisation, and closing an unterminated string.
- Zero runtime dependencies, enforced in CI by installing the built wheel into
  a bare environment.

### Known limitations

- A single-quoted string containing a structural `}` or `]`, with prose
  surrounding the object, is not recovered. See
  [DESIGN.md](DESIGN.md#the-limitation-this-creates-and-why-it-was-accepted).

[0.1.0]: https://github.com/VINOTH-RAJ-R/llm-json/releases/tag/v0.1.0
