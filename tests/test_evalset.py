import pytest

from evalgate.errors import EvalGateError
from evalgate.evalset import Question, load_evalset, parse_evalset

GOOD = '{"id": "a", "question": "q?", "gold_ids": ["p1"], "gold_fact": "x"}'
NOGOLD = '{"id": "b", "question": "nothing?", "answerable": false}'


def test_parses_answerable_and_unanswerable():
    qs = parse_evalset(GOOD + "\n" + NOGOLD + "\n")
    assert qs == [Question("a", "q?", True, ("p1",), "x"), Question("b", "nothing?", False, (), None)]


def test_blank_lines_are_skipped_but_line_numbers_stay_real():
    with pytest.raises(EvalGateError, match=r"<string>:4: invalid JSON"):
        parse_evalset(GOOD + "\n\n\n{not json\n")


def test_malformed_line_reports_its_line_number():
    with pytest.raises(EvalGateError) as exc:
        parse_evalset(GOOD + "\n" + NOGOLD + "\n" + '{"id": "c", "question": ', source="set.jsonl")
    assert str(exc.value).startswith("set.jsonl:3: invalid JSON")


def test_duplicate_ids_name_both_lines():
    with pytest.raises(EvalGateError, match=r"<string>:2: duplicate question id 'a' \(first seen on line 1\)"):
        parse_evalset(GOOD + "\n" + GOOD)


@pytest.mark.parametrize(
    "line, fragment",
    [
        ('[1, 2]', "expected a JSON object"),
        ('{"question": "q"}', "'id' must be a non-empty string"),
        ('{"id": "  ", "question": "q"}', "'id' must be a non-empty string"),
        ('{"id": "a", "question": 5}', "'question' must be a non-empty string"),
        ('{"id": "a", "question": "q", "answerable": "yes"}', "'answerable' must be true or false"),
        ('{"id": "a", "question": "q", "gold_ids": "p1", "gold_fact": "x"}', "'gold_ids' must be a list"),
        ('{"id": "a", "question": "q", "gold_ids": [""], "gold_fact": "x"}', "'gold_ids' must be a list"),
        ('{"id": "a", "question": "q", "gold_ids": ["p"], "gold_fact": ""}', "'gold_fact' must be a non-empty"),
        ('{"id": "a", "question": "q", "gold_ids": ["p"]}', "needs gold_ids and gold_fact"),
        ('{"id": "a", "question": "q", "gold_fact": "x"}', "needs gold_ids and gold_fact"),
        ('{"id": "a", "question": "q", "answerable": false, "gold_ids": ["p"]}', "must not have gold"),
        ('{"id": "a", "question": "q", "answerable": false, "gold_fact": "x"}', "must not have gold"),
    ],
)
def test_validation_errors(line, fragment):
    with pytest.raises(EvalGateError, match=r"^<string>:1: .*" + fragment.replace("'", "'")):
        parse_evalset(line)


def test_empty_set_is_an_error():
    with pytest.raises(EvalGateError, match="eval set is empty"):
        parse_evalset("\n  \n")


def test_unicode_is_preserved(tmp_path):
    f = tmp_path / "q.jsonl"
    f.write_text('{"id": "ñ1", "question": "¿Cuánto cuesta el café ☕?", "gold_ids": ["p1"], "gold_fact": "€5"}\n',
                 encoding="utf-8")
    (q,) = load_evalset(f)
    assert q.id == "ñ1" and q.question == "¿Cuánto cuesta el café ☕?" and q.gold_fact == "€5"


def test_missing_file_is_a_clean_error(tmp_path):
    with pytest.raises(EvalGateError, match="cannot read eval set"):
        load_evalset(tmp_path / "nope.jsonl")


def test_shipped_evalset_is_valid_and_consistent_with_corpus():
    import json
    from importlib import resources

    qs = load_evalset("evals/questions.jsonl")
    corpus = {}
    text = resources.files("evalgate.refapp").joinpath("corpus.jsonl").read_text(encoding="utf-8")
    for line in text.splitlines():
        row = json.loads(line)
        corpus[row["id"]] = row["text"].casefold()
    assert len(qs) == 41
    assert sum(q.answerable for q in qs) == 34
    for q in qs:
        for gid in q.gold_ids:
            assert q.gold_fact.casefold() in corpus[gid], q.id
