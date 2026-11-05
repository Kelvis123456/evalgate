# Demo: breaking the retriever and watching the gate fail

Everything below is the real output of the commands shown, run from the repo
root against the committed `baseline.json` (2026-11-05, Windows, Python 3.14;
the numbers are deterministic for the reference app, so you get the same ones).
`main` stays green: the degraded settings are passed on the command line and
never committed.

Reproduce:

```
pip install -e ".[dev]"
evalgate run                                    # exit 0
evalgate run --param tokenizer=whitespace       # exit 1
evalgate run --param top_k=1                    # exit 1
evalgate run --param min_coverage=0.9           # exit 1
```

`--param` passes keyword arguments to the app factory, so the same trick works
for your own app.

## 1. Unchanged app

```
## evalgate: PASS

| Metric | Baseline | Current | Delta | Tolerance | Status |
| --- | ---: | ---: | ---: | ---: | :---: |
| hit_at_k | 1.0000 | 1.0000 | +0.0000 | 0.0200 | PASS |
| mrr | 0.9853 | 0.9853 | +0.0000 | 0.0200 | PASS |
| citation_correct | 0.9412 | 0.9412 | +0.0000 | 0.0200 | PASS |
| citation_precision | 0.9024 | 0.9024 | +0.0000 | 0.0200 | PASS |
| answer_contains_fact | 0.8824 | 0.8824 | +0.0000 | 0.0200 | PASS |
| abstention_accuracy | 0.7143 | 0.7143 | +0.0000 | 0.0200 | PASS |

No metric dropped more than its tolerance below the baseline.
```

Exit code 0. A clean run. Note abstention_accuracy: 0.7143 is the committed baseline, and it is a weak number. The reference answerer answers 2 of the 7 unanswerable questions instead of abstaining. The gate protects that level, it does not say it is good.

## 2. Broken tokenization (`tokenizer=whitespace`)

A tokenizer that splits on whitespace only, so `payload?` no longer matches `payload`.

```
## evalgate: FAIL

| Metric | Baseline | Current | Delta | Tolerance | Status |
| --- | ---: | ---: | ---: | ---: | :---: |
| hit_at_k | 1.0000 | 0.9412 | -0.0588 | 0.0200 | FAIL |
| mrr | 0.9853 | 0.8725 | -0.1127 | 0.0200 | FAIL |
| citation_correct | 0.9412 | 0.5000 | -0.4412 | 0.0200 | FAIL |
| citation_precision | 0.9024 | 0.5854 | -0.3171 | 0.0200 | FAIL |
| answer_contains_fact | 0.8824 | 0.5000 | -0.3824 | 0.0200 | FAIL |
| abstention_accuracy | 0.7143 | 1.0000 | +0.2857 | 0.0200 | PASS |

Regressed beyond tolerance: hit_at_k, mrr, citation_correct, citation_precision, answer_contains_fact.
```

Exit code 1. Note that abstention_accuracy went up: an app that finds nothing refuses everything, which looks good on that one metric. This is why the gate checks every metric in the baseline instead of one headline score.

## 3. Smaller `top_k` (`top_k=1`)

```
## evalgate: FAIL

| Metric | Baseline | Current | Delta | Tolerance | Status |
| --- | ---: | ---: | ---: | ---: | :---: |
| hit_at_k | 1.0000 | 0.9706 | -0.0294 | 0.0200 | FAIL |
| mrr | 0.9853 | 0.9706 | -0.0147 | 0.0200 | PASS |
| citation_correct | 0.9412 | 0.9412 | +0.0000 | 0.0200 | PASS |
| citation_precision | 0.9024 | 0.9024 | +0.0000 | 0.0200 | PASS |
| answer_contains_fact | 0.8824 | 0.8824 | +0.0000 | 0.0200 | PASS |
| abstention_accuracy | 0.7143 | 0.7143 | +0.0000 | 0.0200 | PASS |

Regressed beyond tolerance: hit_at_k.
```

Exit code 1. A small regression: one question out of 34 loses its gold passage, and the 0.02 tolerance still catches it through hit_at_k. The mrr drop of 0.0147 stays inside tolerance, which is the intended behavior of a tolerance.

## 4. Answerer too picky (`min_coverage=0.9`)

```
## evalgate: FAIL

| Metric | Baseline | Current | Delta | Tolerance | Status |
| --- | ---: | ---: | ---: | ---: | :---: |
| hit_at_k | 1.0000 | 1.0000 | +0.0000 | 0.0200 | PASS |
| mrr | 0.9853 | 0.9853 | +0.0000 | 0.0200 | PASS |
| citation_correct | 0.9412 | 0.3529 | -0.5882 | 0.0200 | FAIL |
| citation_precision | 0.9024 | 0.4634 | -0.4390 | 0.0200 | FAIL |
| answer_contains_fact | 0.8824 | 0.3529 | -0.5294 | 0.0200 | FAIL |
| abstention_accuracy | 0.7143 | 1.0000 | +0.2857 | 0.0200 | PASS |

Regressed beyond tolerance: citation_correct, citation_precision, answer_contains_fact.
```

Exit code 1. Retrieval is untouched, so hit_at_k and mrr pass; the answerer starts refusing questions it could answer.

