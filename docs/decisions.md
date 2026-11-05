# Decisions

Short dated entries: what I decided, what else I considered, why.

## 2026-11-04: stdlib only, no vector store, no LLM in the default path

Alternatives: sentence-transformers or an embeddings API for retrieval, an LLM
for answering and judging.
Why: the point of the project is the gate, not the RAG app. Anything that needs
a key or downloads a model makes CI flaky, slow or paid, and a flaky gate gets
ignored. BM25 and an extractive answerer are enough to produce metrics that can
actually move when something breaks. The cost is that the reference app is a toy.

## 2026-11-04: the gate fails only on drops larger than the tolerance, strictly

Alternatives: fail on any change, fail on any drop, compare against a fixed
absolute threshold instead of a baseline.
Why: a committed baseline means the bar rises only when someone updates it on
purpose, in a reviewable diff. Strictly greater means a drop exactly equal to
the tolerance passes, which is the one rule that is easy to state and test.
Improvements never fail, they just show up in the diff of `baseline.json` when
someone refreshes it.

## 2026-11-04: round to 6 places before comparing

Alternatives: compare raw floats, use `fractions.Fraction`, add an epsilon.
Why: 0.7 - 0.6 is 0.09999999999999998 in floats, so a tolerance of exactly 0.1
would flip on rounding noise. Rounding both metrics and deltas to 6 places is
two lines and the baseline file stores the same rounded values.

## 2026-11-04: a baseline metric missing from the current run fails

Alternatives: skip it with a warning.
Why: the easiest way to pass a gate is to stop measuring the thing that
regressed. Metrics that are not applicable (no unanswerable questions in the
set) are stored as absent in the baseline, so this only bites when something was
measured before and is not now.

## 2026-11-04: abstention means an empty answer string

Alternatives: an explicit `abstained` flag in the app result, a magic refusal
phrase.
Why: it keeps the `App` protocol at three keys and a user's app can adopt it
without learning a flag. A magic phrase would have to be matched against
free text, which breaks the first time someone rewords it.

## 2026-11-04: exit codes 0, 1, 2

Alternatives: one non-zero code for everything.
Why: a bad JSONL line or a missing baseline is not a quality regression, and a
CI log should say which one happened. 1 is a regression, 2 is bad input.

## 2026-11-04: apps are plugged in as `module:factory` plus `--param`

Alternatives: a config file, subclassing a base class, a plugin entry point.
Why: it needs no registry and no config format, and `--param top_k=1` is what
makes the regression demo reproducible without editing code.

## 2026-11-04: the LLM judge is an interface and a stub, nothing more

Alternatives: ship an OpenAI or Anthropic client.
Why: I cannot test a vendor call in CI without a key, and shipping untested
network code in a tool whose job is trust would undercut it. The stub is a word
overlap score and says so. It is off unless `EVALGATE_JUDGE` is set.

## 2026-11-04: setuptools and a plain console script instead of a uv project

Alternatives: uv with a lockfile, hatchling.
Why: there are no runtime dependencies, so a lockfile would only pin pytest.
`pip install -e ".[dev]"` works everywhere the CI runner and a reviewer already
have Python.
