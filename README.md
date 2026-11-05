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
evalgate baseline --allow-regression   # accept lower scores on purpose
evalgate run --tolerance 0.05          # override every tolerance
evalgate run --report-file report.md   # also write the report (CI uses $GITHUB_STEP_SUMMARY)
```

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | pass |
| 1 | regression: a metric dropped by more than its tolerance |
| 2 | bad input or an error outside the gate's verdict: malformed JSONL or baseline, non-finite numbers, eval set changed since the baseline, missing baseline, bad app spec or `--param`, an app, factory, judge or imported module that raises, unreadable or unwritable files |

Exit 1 only ever means a regression. An error exits 2 with a one-line message
and no traceback; set `EVALGATE_DEBUG=1` to get the traceback.

`evalgate baseline` keeps the existing `k`, `default_tolerance` and per-metric
`tolerances` unless you pass `--k` or `--tolerance`. It refuses to write a
baseline that has any metric lower than the current one unless you pass
`--allow-regression`. `judge_score` is only written with `--with-judge`.

## Plug in your own app

Write a factory that returns an object with `answer(question)`:

```python
class MyApp:
    def answer(self, question: str) -> dict:
        return {"answer": "...", "cited_ids": ["doc-7"], "retrieved_ids": ["doc-7", "doc-2"]}

def build(**params):
    return MyApp()
```

Then `evalgate run --app mypackage.mymodule:build --param top_k=5`. The current
directory is put on `sys.path` for both `evalgate` and `python -m evalgate`.
Importing the module named by `--app` (and by `EVALGATE_JUDGE`) runs its
import-time code with your permissions, so only point it at code you trust. `--param`
values become keyword arguments to the factory (numbers and `true`/`false` are
converted; `true`/`false` in any case; `nan` and `inf` are rejected). An empty
`answer` string means the app abstained. Eval set lines
look like this; unanswerable questions leave out the gold fields:

```json
{"id": "q01", "question": "What is the maximum size of a job payload?", "gold_ids": ["p02"], "gold_fact": "256 KB"}
{"id": "u01", "question": "Does Tessera offer a GraphQL API?", "answerable": false}
```

## How the gate decides

Metrics, all computed offline (with the reference app, `abstention_accuracy`
is the weak one, see Limitations):

- `hit_at_k`: a gold passage is in the first k retrieved ids (k is stored in the baseline, 3 here).
- `mrr`: mean of 1/rank of the first gold passage in the retrieved list.
- `citation_correct`: the answer is not an abstention and cites a gold passage id.
- `citation_precision`: the share of distinct cited ids that are gold ids. An abstention or an answer with no citations scores 0 on an answerable question. On an unanswerable question it is 1 when nothing is cited and 0 when anything is. This is what stops an app from citing every passage.
- `answer_contains_fact`: the gold fact appears in the answer after casefolding, NFKC normalization and whitespace collapsing, as a whole token (`7 days` does not match `17 days`, `429` does not match `4290`). Answers longer than 600 normalized characters (`MAX_ANSWER_CHARS` in `metrics.py`) never count, so dumping a passage or the corpus does not score.
- `abstention_accuracy`: on unanswerable questions, the app returned an empty answer. An empty answer is the only thing that counts as abstaining.

Each metric is a mean over the questions it applies to, rounded to 6 places. A
metric fails when `baseline - current` is strictly greater than its tolerance,
so a drop exactly equal to the tolerance passes. Improvements always pass. A
metric that is in the baseline but missing from the run fails. A metric the
run produces but the baseline does not have is shown as `new (not gated)`.
Tolerances and metric values must be finite; `NaN` and infinity are rejected
with exit 2. The default tolerance is 0.02 and `baseline.json` can set
per-metric values under `tolerances`.

`baseline.json` also records a sha256 of the eval set (line endings, outer
spaces and blank lines normalized) and its question count. If the eval set
differs, `evalgate run` exits 2 naming the old and new hash and counts, and
you have to run `evalgate baseline` and commit the new file. Deleting hard
questions therefore shows up in review instead of passing silently.

The optional judge metric is off by default and is not used in CI. Setting
`EVALGATE_JUDGE=module:factory` loads an object with
`score(question, answer, gold_fact) -> float` and adds a `judge_score` metric.
Judge scores must be numbers in [0, 1]. I only ship the interface and `OverlapStubJudge`, a word-overlap stub that is
not an LLM. There is no vendor client in this repo.

CI is in `.github/workflows/ci.yml`: pytest, then the gate, with the report
written to the job summary. `security.yml` comes from my usual security kit
(gitleaks, semgrep, zizmor, bandit, osv). I could not run either workflow here
because nothing has been pushed yet.

## Limitations

- The baseline for `abstention_accuracy` is 0.7143, which is weak: the
  reference answerer gives a made-up answer on 2 of the 7 unanswerable
  questions. The gate only stops it from getting worse.
- An empty answer is the only abstention. A real LLM app that replies "I don't
  know" is scored as having answered, so it fails on unanswerable questions
  unless your wrapper returns an empty string in that case.
- Determinism holds for the reference app only. A real LLM app, or a judge
  backed by a model, can change between runs, and the fixed tolerance is not
  a statistical test.
- The reference app is a toy. Its corpus is 25 short passages and its 41
  questions are easy for BM25, so hit@3 is 1.0. The numbers show the gate
  works, not that this is a good RAG system.
- The answer length cap and `citation_precision` make the cheapest ways of
  gaming the gate fail, but a determined wrapper can still game lexical metrics.
- The metrics are lexical. A correct answer in different words fails
  `answer_contains_fact`, and a wrong answer that quotes the gold fact passes.
- Citation correctness checks the id the app reports, not whether the cited
  text supports the answer.
- Of the 41 questions, 34 are answerable, so one question moves hit@3 by about 0.03, more than the 0.02
  default tolerance. Tolerance only makes sense once you know your set size.
- The baseline is only as good as the person who last ran `evalgate baseline`.
  `evalgate baseline` now refuses lower scores without `--allow-regression`,
  but anyone can pass that flag, so review the diff of `baseline.json`.
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
