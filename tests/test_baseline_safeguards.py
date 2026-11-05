import json
import sys
import types

import pytest

from evalgate.cli import main

SET = (
    '{"id": "a", "question": "size?", "gold_ids": ["p1"], "gold_fact": "256 KB"}\n'
    '{"id": "n", "question": "who?", "answerable": false}\n'
)


class Fixed:
    def __init__(self, answer="256 KB", cited=("p1",)):
        self.out = {"answer": answer, "cited_ids": list(cited), "retrieved_ids": ["p1"]}

    def answer(self, question):
        if question == "who?":
            return {"answer": ""}
        return dict(self.out)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    mod = types.ModuleType("fixedapp")
    mod.build = lambda **kw: Fixed(**kw)
    monkeypatch.setitem(sys.modules, "fixedapp", mod)
    ev = tmp_path / "q.jsonl"
    ev.write_text(SET, encoding="utf-8")
    return str(ev), str(tmp_path / "b.json")


def base(paths, *extra):
    ev, b = paths
    return main(["baseline", "--evalset", ev, "--baseline", b, "--app", "fixedapp:build", *extra])


def load(paths):
    return json.loads(open(paths[1], encoding="utf-8").read())


def test_existing_k_and_tolerances_survive_a_refresh(paths):
    assert base(paths, "--k", "5", "--tolerance", "0.1") == 0
    data = load(paths)
    data["tolerances"] = {"mrr": 0.3}
    open(paths[1], "w", encoding="utf-8").write(json.dumps(data))
    assert base(paths) == 0
    data = load(paths)
    assert (data["k"], data["default_tolerance"], data["tolerances"]) == (5, 0.1, {"mrr": 0.3})


def test_new_baseline_defaults(paths):
    assert base(paths) == 0
    assert (load(paths)["k"], load(paths)["default_tolerance"]) == (3, 0.02)


def test_lowering_a_score_is_refused_without_the_flag(paths, capsys):
    assert base(paths) == 0
    before = open(paths[1], encoding="utf-8").read()
    assert base(paths, "--param", "answer=nothing") == 2
    assert "lower than the existing baseline" in capsys.readouterr().err
    assert open(paths[1], encoding="utf-8").read() == before
    assert base(paths, "--param", "answer=nothing", "--allow-regression") == 0
    assert load(paths)["metrics"]["answer_contains_fact"] == 0.0


def test_judge_score_is_written_only_when_asked(paths, monkeypatch, capsys):
    monkeypatch.setenv("EVALGATE_JUDGE", "evalgate.judge:OverlapStubJudge")
    assert base(paths) == 0
    assert "judge_score" not in load(paths)["metrics"]
    assert base(paths, "--with-judge") == 0
    assert "judge_score" in load(paths)["metrics"]
    monkeypatch.delenv("EVALGATE_JUDGE")
    assert base(paths, "--with-judge") == 2
    assert "EVALGATE_JUDGE" in capsys.readouterr().err


def test_baseline_tolerance_must_be_finite(paths, capsys):
    assert base(paths, "--tolerance=inf") == 2
    assert base(paths, "--tolerance=-0.1") == 2
    capsys.readouterr()
