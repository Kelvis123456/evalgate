import json
import pathlib
import sys
import types

import pytest

from evalgate.app import load_app, normalize_result, parse_params
from evalgate.cli import main
from evalgate.errors import EvalGateError
from evalgate.evalset import Question, fingerprint
from evalgate.judge import OverlapStubJudge, judge_from_env
from evalgate.runner import run_evalset


class Fixed:
    """An app that always returns the same thing."""

    def __init__(self, answer="", cited=(), retrieved=()):
        self.out = {"answer": answer, "cited_ids": list(cited), "retrieved_ids": list(retrieved)}

    def answer(self, question):
        return dict(self.out)


@pytest.fixture
def plug(monkeypatch):
    """Registers module 'plugapp' whose factory(**kw) builds Fixed(**kw)."""
    mod = types.ModuleType("plugapp")
    mod.build = lambda **kw: Fixed(**kw)
    mod.not_an_app = lambda **kw: object()
    mod.value = 3
    monkeypatch.setitem(sys.modules, "plugapp", mod)


def write_set(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(
        '{"id": "a", "question": "size?", "gold_ids": ["p1"], "gold_fact": "256 KB"}\n'
        '{"id": "n", "question": "who?", "answerable": false}\n',
        encoding="utf-8",
    )
    return str(p)


def write_base(tmp_path, metrics, evalset="evals/questions.jsonl", **extra):
    text = pathlib.Path(evalset).read_text(encoding="utf-8")
    ev = {"sha256": fingerprint(text), "questions": len([x for x in text.splitlines() if x.strip()])}
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"metrics": metrics, "evalset": ev, **extra}), encoding="utf-8")
    return str(p)


def test_shipped_baseline_passes_for_the_reference_app(capsys):
    assert main(["run"]) == 0
    assert capsys.readouterr().out.startswith("## evalgate: PASS")


def test_breaking_the_tokenizer_fails_the_gate(capsys):
    assert main(["run", "--param", "tokenizer=whitespace"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("## evalgate: FAIL")
    assert "| citation_correct | 0.9412 | 0.5000 | -0.4412 | 0.0200 | FAIL |" in out
    assert "| abstention_accuracy | 0.7143 | 1.0000 | +0.2857 | 0.0200 | PASS |" in out


def test_report_file_is_written(tmp_path):
    report = tmp_path / "r.md"
    main(["run", "--report-file", str(report)])
    assert report.read_text(encoding="utf-8").startswith("## evalgate: PASS")


def test_always_answering_app_fails_on_abstention(plug, tmp_path, capsys):
    mod = sys.modules["plugapp"]
    mod.build = lambda: Fixed("It is 256 KB", ["p1"], ["p1"])
    base = write_base(tmp_path, {"hit_at_k": 1.0, "abstention_accuracy": 1.0}, write_set(tmp_path))
    assert main(["run", "--evalset", write_set(tmp_path), "--baseline", base, "--app", "plugapp:build"]) == 1
    out = capsys.readouterr().out
    assert "| hit_at_k | 1.0000 | 1.0000 | +0.0000 | 0.0200 | PASS |" in out
    assert "| abstention_accuracy | 1.0000 | 0.0000 | -1.0000 | 0.0200 | FAIL |" in out


def test_list_valued_results_pass(plug, tmp_path, capsys):
    mod = sys.modules["plugapp"]

    class Good:
        def answer(self, question):
            if question == "size?":
                return {"answer": "It is 256 KB", "cited_ids": ["p1"], "retrieved_ids": ["p1"]}
            return {"answer": ""}

    mod.build = lambda: Good()
    base = write_base(tmp_path, {"hit_at_k": 1.0, "mrr": 1.0, "citation_correct": 1.0,
                                 "answer_contains_fact": 1.0, "abstention_accuracy": 1.0},
                      write_set(tmp_path))
    assert main(["run", "--evalset", write_set(tmp_path), "--baseline", base, "--app", "plugapp:build"]) == 0
    assert "| mrr | 1.0000 | 1.0000 | +0.0000 | 0.0200 | PASS |" in capsys.readouterr().out


def test_tolerance_flag_flips_the_verdict(tmp_path, capsys):
    # reference app scores abstention 0.714286; baseline asks 0.73, a 0.015714 drop
    base = write_base(tmp_path, {"abstention_accuracy": 0.73})
    assert main(["run", "--baseline", base]) == 0
    assert main(["run", "--baseline", base, "--tolerance", "0.01"]) == 1
    capsys.readouterr()


def test_errors_exit_2_with_message(tmp_path, capsys):
    assert main(["run", "--baseline", str(tmp_path / "missing.json")]) == 2
    assert "baseline not found" in capsys.readouterr().err
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a", "question": "q", "gold_ids": ["p"], "gold_fact": "f"}\n{oops\n', encoding="utf-8")
    assert main(["run", "--evalset", str(bad)]) == 2
    assert f"{bad}:2: invalid JSON" in capsys.readouterr().err
    assert main(["run", "--app", "no_such_module_xyz:build"]) == 2
    assert main(["run", "--param", "novalue"]) == 2
    assert main(["run", "--tolerance", "-1"]) == 2
    assert main(["run", "--param", "bogus=1"]) == 2  # factory rejects unknown kwarg
    capsys.readouterr()


def test_baseline_command_writes_file(tmp_path, capsys):
    out = tmp_path / "new.json"
    assert main(["baseline", "--baseline", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["metrics"]["hit_at_k"] == 1.0 and data["k"] == 3
    assert main(["run", "--baseline", str(out)]) == 0
    capsys.readouterr()


def test_parse_params_coerces_types():
    assert parse_params(["a=3", "b=0.5", "c=true", "d=x=y", "e=false"]) == {
        "a": 3, "b": 0.5, "c": True, "d": "x=y", "e": False}
    with pytest.raises(EvalGateError):
        parse_params(["=1"])


def test_load_app_errors(plug):
    with pytest.raises(EvalGateError, match="expected module:factory"):
        load_app("nocolon")
    with pytest.raises(EvalGateError, match="has no attribute 'zzz'"):
        load_app("plugapp:zzz")
    with pytest.raises(EvalGateError, match="did not return an object with answer"):
        load_app("plugapp:not_an_app")


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("text", "must return a dict"),
        ({"answer": None}, "'answer' must be a string"),
        ({"answer": "x", "cited_ids": "p1"}, "'cited_ids' must be a list of strings"),
        ({"answer": "x", "retrieved_ids": [1]}, "'retrieved_ids' must be a list of strings"),
    ],
)
def test_normalize_result_rejects_bad_shapes(raw, fragment):
    with pytest.raises(EvalGateError, match=fragment):
        normalize_result(raw)


def test_runner_names_the_question_when_app_misbehaves():
    class Bad:
        def answer(self, q):
            return "oops"

    qs = [Question("q7", "?", False)]
    with pytest.raises(EvalGateError, match="question q7: app result"):
        run_evalset(Bad(), qs)
    with pytest.raises(EvalGateError, match="k must be at least 1"):
        run_evalset(Fixed(), qs, k=0)


def test_judge_is_off_by_default_and_metric_absent():
    assert judge_from_env({}) is None
    qs = [Question("a", "?", True, ("p",), "256 KB")]
    m = run_evalset(Fixed("it is 256 KB", ["p"], ["p"]), qs).metrics
    assert "judge_score" not in m


def test_judge_stub_adds_metric_when_enabled():
    judge = judge_from_env({"EVALGATE_JUDGE": "evalgate.judge:OverlapStubJudge"})
    assert isinstance(judge, OverlapStubJudge)
    qs = [Question("a", "?", True, ("p",), "256 KB"), Question("b", "?", True, ("p",), "one two three four")]
    m = run_evalset(Fixed("about 256 kb and one two", ["p"], ["p"]), qs, judge=judge).metrics
    assert m["judge_score"] == 0.75  # (1.0 + 0.5) / 2
    assert OverlapStubJudge().score("q", "", "x") == 0.0
    assert OverlapStubJudge().score("q", "anything", "!!!") == 0.0


def test_judge_env_rejects_non_judge():
    with pytest.raises(EvalGateError, match="did not return an object with score"):
        judge_from_env({"EVALGATE_JUDGE": "evalgate.refapp:load_corpus"})
