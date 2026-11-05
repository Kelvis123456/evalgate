import pytest

from evalgate import metrics
from evalgate.app import Result
from evalgate.evalset import Question
from evalgate.metrics import aggregate, score_question

Q = Question("q", "?", True, ("g1", "g2"), "7 days")
NO = Question("n", "?", False)


def res(answer="it is 7 days", cited=("g1",), retrieved=("g1",)):
    return Result(answer, tuple(cited), tuple(retrieved))


def test_citation_precision_is_share_of_cited_ids_that_are_gold():
    assert score_question(Q, res(cited=("g1",)), 3).precision == 1.0
    assert score_question(Q, res(cited=("g1", "x")), 3).precision == 0.5
    assert score_question(Q, res(cited=("g1", "g1", "x")), 3).precision == 0.5  # duplicates count once
    assert score_question(Q, res(cited=("x",)), 3).precision == 0.0


def test_citation_precision_edge_cases():
    assert score_question(Q, res(cited=()), 3).precision == 0.0           # answered, cited nothing
    assert score_question(Q, res(answer="", cited=("g1",)), 3).precision == 0.0  # abstained on answerable
    assert score_question(NO, res(answer="", cited=()), 3).precision == 1.0     # nothing expected, nothing cited
    assert score_question(NO, res(answer="", cited=("g1",)), 3).precision == 0.0  # no gold exists to cite


def test_long_answer_does_not_count_as_containing_the_fact():
    dump = "filler words " * 100 + "7 days"
    assert len(dump) > metrics.MAX_ANSWER_CHARS
    assert score_question(Q, res(answer=dump), 3).fact == 0.0
    ok = "x " * 50 + "7 days"
    assert len(ok) <= metrics.MAX_ANSWER_CHARS
    assert score_question(Q, res(answer=ok), 3).fact == 1.0


def test_aggregate_has_citation_precision():
    m = aggregate([score_question(Q, res(cited=("g1", "x")), 3), score_question(NO, res(answer="", cited=()), 3)])
    assert m["citation_precision"] == 0.75
