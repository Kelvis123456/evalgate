import pytest

from evalgate.app import Result
from evalgate.evalset import Question
from evalgate.metrics import score_question

Q = Question("q", "?", True, ("g1", "g2"), "7 days")


def res(answer="it is 7 days", cited=("g1",), retrieved=("g1",)):
    return Result(answer, tuple(cited), tuple(retrieved))


@pytest.mark.parametrize("answer", ["it is 17 days", "about 1.7 days", "27 days", "7 daysx"])
def test_fact_needs_word_boundaries(answer):
    assert score_question(Q, res(answer=answer), k=3).fact == 0.0


@pytest.mark.parametrize("answer", ["7 days", "after 7 days.", "(7 days)", "Up to 7 DAYS, then deleted", "x, 7 days"])
def test_fact_still_matches_at_boundaries(answer):
    assert score_question(Q, res(answer=answer), k=3).fact == 1.0


def test_status_code_does_not_match_longer_number():
    q = Question("s", "?", True, ("g",), "429")
    assert score_question(q, res(answer="error 4290"), k=3).fact == 0.0
    assert score_question(q, res(answer="HTTP 429."), k=3).fact == 1.0
