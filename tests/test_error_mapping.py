import math
import os
import sys
import types

import pytest

from evalgate.app import load_app, parse_params
from evalgate.cli import main
from evalgate.errors import EvalGateError

SET = '{"id": "a", "question": "size?", "gold_ids": ["p1"], "gold_fact": "256 KB"}\n'


@pytest.fixture
def evalset(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(SET, encoding="utf-8")
    return str(p)


def register(monkeypatch, name, build):
    mod = types.ModuleType(name)
    mod.build = build
    monkeypatch.setitem(sys.modules, name, mod)


def make_baseline(evalset, tmp_path):
    out = tmp_path / "b.json"
    assert main(["baseline", "--evalset", evalset, "--baseline", str(out)]) in (0, 2)
    return str(out)


@pytest.fixture
def baseline(tmp_path, evalset, monkeypatch):
    class Good:
        def answer(self, q):
            return {"answer": "256 KB", "cited_ids": ["p1"], "retrieved_ids": ["p1"]}

    register(monkeypatch, "goodapp", lambda: Good())
    out = tmp_path / "b.json"
    assert main(["baseline", "--evalset", evalset, "--baseline", str(out), "--app", "goodapp:build"]) == 0
    return str(out)


def run(evalset, baseline, app, *extra):
    return main(["run", "--evalset", evalset, "--baseline", baseline, "--app", app, *extra])


def test_app_exception_is_exit_2_not_a_traceback(monkeypatch, evalset, baseline, capsys):
    class Boom:
        def answer(self, q):
            raise RuntimeError("model down")

    register(monkeypatch, "boomapp", lambda: Boom())
    assert run(evalset, baseline, "boomapp:build") == 2
    err = capsys.readouterr().err
    assert "question a" in err and "RuntimeError" in err and "model down" in err
    assert "Traceback" not in err


def test_factory_exception_is_exit_2(monkeypatch, evalset, baseline, capsys):
    def build():
        raise ValueError("no api key")

    register(monkeypatch, "badfactory", build)
    assert run(evalset, baseline, "badfactory:build") == 2
    assert "no api key" in capsys.readouterr().err


def test_non_utf8_evalset_is_exit_2(tmp_path, baseline, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_bytes(b'{"id": "a", "question": "caf\xe9?"}\n')
    assert main(["run", "--evalset", str(bad), "--baseline", baseline]) == 2
    assert "UTF-8" in capsys.readouterr().err


def test_unwritable_report_file_is_exit_2(tmp_path, evalset, baseline, monkeypatch, capsys):
    register(monkeypatch, "goodapp2", lambda: types.SimpleNamespace(
        answer=lambda q: {"answer": "256 KB", "cited_ids": ["p1"], "retrieved_ids": ["p1"]}))
    target = tmp_path / "no_such_dir" / "r.md"
    assert run(evalset, baseline, "goodapp2:build", "--report-file", str(target)) == 2
    assert "report" in capsys.readouterr().err


def test_syntax_error_in_user_module_is_exit_2(tmp_path, monkeypatch, evalset, baseline, capsys):
    (tmp_path / "brokenmod.py").write_text("def build(:\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert run(evalset, baseline, "brokenmod:build") == 2
    assert "brokenmod" in capsys.readouterr().err


def test_import_time_exception_is_exit_2(tmp_path, monkeypatch, evalset, baseline, capsys):
    (tmp_path / "explodes.py").write_text("raise RuntimeError('at import')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert run(evalset, baseline, "explodes:build") == 2
    assert "at import" in capsys.readouterr().err


def test_judge_exception_is_exit_2(monkeypatch, evalset, baseline, capsys):
    class BadJudge:
        def score(self, q, a, g):
            raise RuntimeError("judge offline")

    register(monkeypatch, "badjudge", lambda: BadJudge())
    monkeypatch.setenv("EVALGATE_JUDGE", "badjudge:build")
    assert main(["run", "--evalset", evalset, "--baseline", baseline, "--app", "goodapp:build"]) == 2
    assert "judge offline" in capsys.readouterr().err


def test_debug_env_keeps_the_traceback(monkeypatch, evalset, baseline):
    class Boom:
        def answer(self, q):
            raise RuntimeError("model down")

    register(monkeypatch, "boomapp2", lambda: Boom())
    monkeypatch.setenv("EVALGATE_DEBUG", "1")
    with pytest.raises(Exception):
        run(evalset, baseline, "boomapp2:build")


def test_factory_type_error_inside_factory_is_an_app_error_not_a_param_error():
    def build(top_k=3):
        return len(None)  # genuine TypeError inside the factory

    mod = types.ModuleType("tefactory")
    mod.build = build
    sys.modules["tefactory"] = mod
    try:
        with pytest.raises(EvalGateError, match="raised TypeError") as e:
            load_app("tefactory:build", {"top_k": 1})
        assert "rejected params" not in str(e.value)
        with pytest.raises(EvalGateError, match="rejected params"):
            load_app("tefactory:build", {"nope": 1})
    finally:
        del sys.modules["tefactory"]


@pytest.mark.parametrize("v", ["nan", "inf", "-inf", "NaN", "Infinity"])
def test_param_rejects_non_finite_floats(v):
    with pytest.raises(EvalGateError, match="finite"):
        parse_params([f"x={v}"])


def test_param_booleans_are_case_insensitive():
    assert parse_params(["a=True", "b=FALSE", "c=true"]) == {"a": True, "b": False, "c": True}
    assert parse_params(["a=truely"]) == {"a": "truely"}
    assert parse_params(["a=1e3"]) == {"a": 1000.0} and math.isfinite(1000.0)


def test_cwd_is_importable_even_when_not_on_sys_path(tmp_path, monkeypatch, evalset, baseline, capsys):
    (tmp_path / "cwdapp.py").write_text(
        "class A:\n    def answer(self, q):\n        return {'answer': '256 KB', 'cited_ids': ['p1'], 'retrieved_ids': ['p1']}\n"
        "def build():\n    return A()\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cwd = os.getcwd()
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", cwd)])
    assert run(evalset, baseline, "cwdapp:build") == 0
    capsys.readouterr()
    sys.modules.pop("cwdapp", None)
