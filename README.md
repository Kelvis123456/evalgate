# evalgate

evalgate is a CI gate for RAG and LLM apps. You keep a versioned eval set in
JSONL and a committed `baseline.json` of scores. `evalgate run` executes the
set against your app, compares the metrics to the baseline, prints a Markdown
table, and exits non-zero if quality dropped by more than a tolerance.

## Why I built it

Prompt and retriever changes tend to merge with "looks fine on the three
examples I tried". I wanted the same check for answer quality that a test
suite gives for code: a number in CI that moves when something breaks. It
also had to run with no API keys and give the same result every time, or I
would stop trusting it.

So the repo ships a small reference RAG app (an original 25-passage corpus about
a made-up job-queue product, a stdlib BM25 retriever, and an extractive
answerer) and 41 eval questions. You can watch the gate work before pointing it
at your own app.

## Run it

Python 3.12 or newer, no runtime dependencies.

```
pip install -e ".[dev]"
python -m pytest
evalgate run
```

To see it fail, degrade the reference app from the command line:

```
evalgate run --param tokenizer=whitespace
```

That exits 1 and prints a table with the dropped metrics marked FAIL. Real
output for several degraded settings is in [docs/demo-regression.md](docs/demo-regression.md).

Other commands:

```
evalgate baseline                      # run the set and rewrite baseline.json
evalgate run --tolerance 0.05          # override every tolerance
evalgate run --report-file report.md   # also write the report (CI uses $GITHUB_STEP_SUMMARY)
```

Exit codes: 0 pass, 1 regression, 2 bad input (malformed JSONL with the line
number, duplicate ids, missing baseline, bad app spec).

## Plug in your own app

Write a factory that returns an object with `answer(question)`:

```python
class MyApp:
    def answer(self, question: str) -> dict:
        return {"answer": "...", "cited_ids": ["doc-7"], "retrieved_ids": ["doc-7", "doc-2"]}

def build(**params):
    return MyApp()
```

Then `evalgate run --app mypackage.mymodule:build --param top_k=5`. `--param`
values become keyword arguments to the factory (numbers and `true`/`false` are
converted). An empty `answer` string means the app abstained. Eval set lines
look like this; unanswerable questions leave out the gold fields:

```json
{"id": "q01", "question": "What is the maximum size of a job payload?", "gold_ids": ["p02"], "gold_fact": "256 KB"}
{"id": "u01", "question": "Does Tessera offer a GraphQL API?", "answerable": false}
```

## How the gate decides

Metrics, all computed offline:

- `hit_at_k`: a gold passage is in the first k retrieved ids (k is stored in the baseline, 3 here).
- `mrr`: mean of 1/rank of the first gold passage in the retrieved list.
- `citation_correct`: the answer is not an abstention and cites a gold passage id.
- `answer_contains_fact`: the gold fact appears in the answer after casefolding, NFKC normalization and whitespace collapsing.
- `abstention_accuracy`: on unanswerable questions, the app returned an empty answer.

Each metric is a mean over the questions it applies to, rounded to 6 places. A
metric fails when `baseline - current` is strictly greater than its tolerance,
so a drop exactly equal to the tolerance passes. Improvements always pass. A
metric that is in the baseline but missing from the run fails. The default
tolerance is 0.02 and `baseline.json` can set per-metric values under
`tolerances`.

The optional judge metric is off by default and is not used in CI. Setting
`EVALGATE_JUDGE=module:factory` loads an object with
`score(question, answer, gold_fact) -> float` and adds a `judge_score` metric.
I only ship the interface and `OverlapStubJudge`, a word-overlap stub that is
not an LLM. There is no vendor client in this repo.

CI is in `.github/workflows/ci.yml`: pytest, then the gate, with the report
written to the job summary. `security.yml` comes from my usual security kit
(gitleaks, semgrep, zizmor, bandit, osv). I could not run either workflow here
because nothing has been pushed yet.

## Limitations

- The reference app is a toy. Its corpus is 25 short passages and its 41
  questions are easy for BM25, so hit@3 is 1.0. The numbers show the gate
  works, not that this is a good RAG system.
- The metrics are lexical. A correct answer in different words fails
  `answer_contains_fact`, and a wrong answer that quotes the gold fact passes.
- Citation correctness checks the id the app reports, not whether the cited
  text supports the answer.
- With 41 questions, one question moves hit@3 by about 0.03, more than the 0.02
  default tolerance. Tolerance only makes sense once you know your set size.
- The baseline is only as good as the person who last ran `evalgate baseline`.
  Refreshing it after a regression hides the regression.
- The eval set is not checked for leakage into the app, and there is no
  statistical test, only a fixed tolerance.
- Single-turn questions only. No multi-turn, no tool use, no latency or cost
  budgets.
- Tested on Windows with Python 3.14. CI targets 3.12 but has not run yet.

## Layout

```
src/evalgate/        runner, metrics, gate, CLI, judge interface
src/evalgate/refapp/ reference app and its corpus
evals/questions.jsonl
baseline.json
docs/decisions.md    why it is built this way
docs/demo-regression.md
tests/
```

MIT licensed. See `LICENSE`.
