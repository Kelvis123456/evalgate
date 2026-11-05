import pytest

from evalgate.errors import EvalGateError
from evalgate.evalset import load_evalset
from evalgate.refapp import RefApp, build, load_corpus
from evalgate.refapp.bm25 import BM25, Passage, tokenize
from evalgate.runner import run_evalset


def test_tokenize_basics():
    assert tokenize("What IS the Payload limits?") == ["payload", "limit"]
    assert tokenize("class access") == ["class", "access"]  # 'ss' keeps its s
    assert tokenize("") == [] and tokenize("   ?!  ") == []


def test_tokenize_unicode():
    assert tokenize("Café ÑANDÚ 日本語 ﬁsh") == ["café", "ñandú", "日本語", "fish"]


def test_empty_corpus_returns_nothing_and_does_not_divide_by_zero():
    idx = BM25([])
    assert idx.search("anything") == []
    assert idx.idf("x") > 0
    assert RefApp([]).answer("anything") == {"answer": "", "cited_ids": [], "retrieved_ids": []}


def test_ties_break_by_corpus_order():
    ps = [Passage("b", "", "apple pie"), Passage("a", "", "apple pie"), Passage("c", "", "apple pie")]
    hits = BM25(ps).search("apple", top_k=3)
    assert [p.id for p, _ in hits] == ["b", "a", "c"]
    assert hits[0][1] == hits[1][1] == hits[2][1]


def test_zero_scores_are_excluded_and_top_k_caps():
    ps = [Passage("a", "", "apple"), Passage("b", "", "banana"), Passage("c", "", "apple banana")]
    idx = BM25(ps)
    assert [p.id for p, _ in idx.search("apple", 5)] == ["a", "c"]
    assert [p.id for p, _ in idx.search("apple banana", 1)] == ["c"]
    assert idx.search("cherry") == []
    assert idx.search("apple", top_k=0) == []


def test_rarer_term_ranks_higher():
    ps = [Passage("a", "", "common rare"), Passage("b", "", "common common"), Passage("c", "", "common")]
    assert BM25(ps).search("common rare", 1)[0][0].id == "a"


def test_corpus_shape():
    c = load_corpus()
    assert len(c) == 25
    assert len({p.id for p in c}) == 25


def test_known_answers():
    app = build()
    out = app.answer("What is the maximum size of a job payload?")
    assert out["retrieved_ids"][0] == "p02"
    out = app.answer("How long are dead letter jobs kept before deletion?")
    assert out == {
        "answer": "Dead letter jobs are kept for 14 days before deletion.",
        "cited_ids": ["p05"],
        "retrieved_ids": out["retrieved_ids"],
    }
    assert out["retrieved_ids"][0] == "p05"


def test_abstains_on_unknown_topic():
    out = build().answer("Who founded Tessera?")
    assert out["answer"] == "" and out["cited_ids"] == []


def test_unicode_and_empty_questions_do_not_crash():
    app = build()
    assert app.answer("¿Cuánto cuesta ☕ 日本語?")["answer"] == ""
    assert app.answer("")["retrieved_ids"] == []


def test_params_validate():
    with pytest.raises(EvalGateError, match="unknown tokenizer 'nope'"):
        build(tokenizer="nope")


def test_top_k_one_returns_a_single_retrieved_id():
    assert len(build(top_k=1).answer("job payload size")["retrieved_ids"]) == 1


def test_reference_scores_are_pinned():
    m = run_evalset(build(), load_evalset("evals/questions.jsonl")).metrics
    assert m == {
        "hit_at_k": 1.0,
        "mrr": 0.985294,
        "citation_correct": 0.941176,
        "answer_contains_fact": 0.882353,
        "abstention_accuracy": 0.714286,
    }


def test_whitespace_tokenizer_really_is_worse():
    m = run_evalset(build(tokenizer="whitespace"), load_evalset("evals/questions.jsonl")).metrics
    assert m["hit_at_k"] == 0.941176
    assert m["mrr"] == 0.872549
    assert m["citation_correct"] == 0.5
    assert m["answer_contains_fact"] == 0.5
