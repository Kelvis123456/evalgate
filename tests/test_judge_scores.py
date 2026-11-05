import pytest

from evalgate.errors import EvalGateError
from evalgate.evalset import Question
from evalgate.runner import run_evalset


class App:
    def answer(self, q):
        return {"answer": "256 KB", "cited_ids": ["p"], "retrieved_ids": ["p"]}


class J:
    def __init__(self, value):
        self.value = value

    def score(self, q, a, g):
        return self.value


QS = [Question("a", "?", True, ("p",), "256 KB")]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.5, "0.9", None, True])
def test_judge_scores_must_be_finite_numbers_in_unit_range(bad):
    with pytest.raises(EvalGateError, match="question a: judge returned"):
        run_evalset(App(), QS, judge=J(bad))


@pytest.mark.parametrize("ok", [0, 1, 0.0, 0.5, 1.0])
def test_judge_scores_at_the_edges_are_fine(ok):
    assert run_evalset(App(), QS, judge=J(ok)).metrics["judge_score"] == float(ok)
