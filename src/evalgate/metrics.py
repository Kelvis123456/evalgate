"""Deterministic, offline metrics.

Each metric is a mean over the questions it applies to, rounded to 6 places
so float noise never decides a gate. A metric with no applicable questions is
None (for example abstention_accuracy on an eval set with no unanswerable
questions) and is left out of the gate.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .app import Result
from .evalset import Question

METRIC_NAMES = ("hit_at_k", "mrr", "citation_correct", "answer_contains_fact", "abstention_accuracy")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", text).strip()


def _contains_fact(fact: str, answer: str) -> bool:
    """Whole-token match: '7 days' must not hit '17 days' or '1.7 days', '429' not '4290'."""
    pattern = r"(?<!\w)(?<!\d[.,])" + re.escape(_norm(fact)) + r"(?!\w)(?![.,]\d)"
    return re.search(pattern, _norm(answer)) is not None


@dataclass(frozen=True)
class QuestionScore:
    id: str
    hit: float | None
    rr: float | None
    cited: float | None
    fact: float | None
    abstained_ok: float | None


def score_question(q: Question, r: Result, k: int) -> QuestionScore:
    if not q.answerable:
        return QuestionScore(q.id, None, None, None, None, 1.0 if r.abstained else 0.0)
    gold = set(q.gold_ids)
    hit = 1.0 if any(i in gold for i in r.retrieved_ids[:k]) else 0.0
    rr = 0.0
    for rank, pid in enumerate(r.retrieved_ids, start=1):
        if pid in gold:
            rr = 1 / rank
            break
    cited = 1.0 if not r.abstained and any(i in gold for i in r.cited_ids) else 0.0
    fact = 1.0 if q.gold_fact and _contains_fact(q.gold_fact, r.answer) else 0.0
    return QuestionScore(q.id, hit, rr, cited, fact, None)


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 6) if vals else None


def aggregate(scores: list[QuestionScore]) -> dict[str, float | None]:
    return {
        "hit_at_k": _mean([s.hit for s in scores]),
        "mrr": _mean([s.rr for s in scores]),
        "citation_correct": _mean([s.cited for s in scores]),
        "answer_contains_fact": _mean([s.fact for s in scores]),
        "abstention_accuracy": _mean([s.abstained_ok for s in scores]),
    }
