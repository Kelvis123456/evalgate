from evalgate.app import Result
from evalgate.evalset import Question
from evalgate.metrics import aggregate, score_question

Q = Question("q", "?", True, ("g1", "g2"), "256 KB")
NO = Question("n", "?", False)


def res(answer="the limit is 256 KB", cited=("g1",), retrieved=("x", "g1", "y")):
    return Result(answer, tuple(cited), tuple(retrieved))


def test_perfect_answer():
    s = score_question(Q, res(retrieved=("g1", "x")), k=3)
    assert (s.hit, s.rr, s.cited, s.fact, s.abstained_ok) == (1.0, 1.0, 1.0, 1.0, None)


def test_hit_respects_k_and_mrr_uses_full_list():
    r = res(retrieved=("a", "b", "c", "g2"))
    s3 = score_question(Q, r, k=3)
    s4 = score_question(Q, r, k=4)
    assert (s3.hit, s3.rr) == (0.0, 0.25)
    assert (s4.hit, s4.rr) == (1.0, 0.25)


def test_rank_two_gives_half():
    assert score_question(Q, res(retrieved=("x", "g2")), k=3).rr == 0.5


def test_first_gold_wins_for_mrr_when_several_gold_are_retrieved():
    assert score_question(Q, res(retrieved=("g2", "g1")), k=3).rr == 1.0


def test_no_gold_retrieved():
    s = score_question(Q, res(retrieved=("a", "b")), k=3)
    assert (s.hit, s.rr) == (0.0, 0.0)


def test_empty_retrieval_scores_zero_not_crash():
    s = score_question(Q, res(retrieved=()), k=3)
    assert (s.hit, s.rr) == (0.0, 0.0)


def test_citation_must_name_a_gold_passage():
    assert score_question(Q, res(cited=("x",)), k=3).cited == 0.0
    assert score_question(Q, res(cited=("x", "g2")), k=3).cited == 1.0
    assert score_question(Q, res(cited=()), k=3).cited == 0.0


def test_abstaining_on_an_answerable_question_scores_zero_everywhere_it_can():
    s = score_question(Q, res(answer="  ", cited=("g1",)), k=3)
    assert (s.cited, s.fact) == (0.0, 0.0)
    assert s.hit == 1.0  # retrieval is still judged on its own


def test_fact_match_is_case_whitespace_and_unicode_insensitive():
    assert score_question(Q, res(answer="It is 256\n  kb."), k=3).fact == 1.0
    q = Question("u", "?", True, ("g",), "Café €5")
    assert score_question(q, res(answer="cafe €5"), k=3).fact == 0.0  # no accent folding
    assert score_question(q, res(answer="CAFÉ  €5 today"), k=3).fact == 1.0
    decomposed = "Café €5"  # e + combining acute, NFKC composes it
    assert score_question(q, Result(decomposed, (), ()), k=3).fact == 1.0


def test_fact_missing():
    assert score_question(Q, res(answer="about 256 megabytes"), k=3).fact == 0.0


def test_unanswerable_scores_only_abstention():
    refused = score_question(NO, res(answer=""), k=3)
    answered = score_question(NO, res(), k=3)
    assert (refused.abstained_ok, refused.hit, refused.fact) == (1.0, None, None)
    assert answered.abstained_ok == 0.0


def test_aggregate_exact_numbers_and_none_when_not_applicable():
    scores = [
        score_question(Q, res(retrieved=("g1",)), k=3),                              # 1, 1, 1, 1
        score_question(Q, res(retrieved=("x", "g1"), cited=("x",), answer="no"), 3),  # 1, .5, 0, 0
        score_question(Q, res(retrieved=("x",), cited=(), answer=""), 3),             # 0, 0, 0, 0
        score_question(NO, res(answer=""), 3),
        score_question(NO, res(), 3),
        score_question(NO, res(), 3),
    ]
    m = aggregate(scores)
    assert m == {
        "hit_at_k": round(2 / 3, 6),
        "mrr": 0.5,
        "citation_correct": round(1 / 3, 6),
        "answer_contains_fact": round(1 / 3, 6),
        "abstention_accuracy": round(1 / 3, 6),
    }
    only_answerable = aggregate(scores[:3])
    assert only_answerable["abstention_accuracy"] is None
    assert aggregate(scores[3:])["hit_at_k"] is None
    assert aggregate([]) == dict.fromkeys(m)
