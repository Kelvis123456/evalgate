from __future__ import annotations

from dataclasses import dataclass

from .app import App, normalize_result
from .errors import EvalGateError
from .evalset import Question
from .judge import Judge
from .metrics import QuestionScore, aggregate, score_question


@dataclass(frozen=True)
class RunResult:
    metrics: dict[str, float | None]
    scores: list[QuestionScore]


def _judge_score(judge: Judge, q: Question, answer: str) -> float:
    try:
        value = judge.score(q.question, answer, q.gold_fact)
    except Exception as exc:
        raise EvalGateError(f"question {q.id}: judge raised {type(exc).__name__}: {exc}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        # NaN fails the range check too, since every comparison with it is false
        raise EvalGateError(f"question {q.id}: judge returned {value!r}, expected a number in [0, 1]")
    return float(value)


def run_evalset(
    app: App, questions: list[Question], k: int = 3, judge: Judge | None = None
) -> RunResult:
    if k < 1:
        raise EvalGateError("k must be at least 1")
    scores: list[QuestionScore] = []
    judged: list[float] = []
    for q in questions:
        try:
            result = normalize_result(app.answer(q.question))
        except EvalGateError as exc:
            raise EvalGateError(f"question {q.id}: {exc}") from exc
        except Exception as exc:
            raise EvalGateError(f"question {q.id}: app raised {type(exc).__name__}: {exc}") from exc
        scores.append(score_question(q, result, k))
        if judge is not None and q.answerable and q.gold_fact:
            judged.append(_judge_score(judge, q, result.answer))
    metrics = aggregate(scores)
    if judge is not None and judged:
        metrics["judge_score"] = round(sum(judged) / len(judged), 6)
    return RunResult(metrics, scores)
