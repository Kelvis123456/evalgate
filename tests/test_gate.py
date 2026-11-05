import json

import pytest

from evalgate.errors import EvalGateError
from evalgate.gate import (
    Baseline, compare, load_baseline, parse_baseline, passed, render_markdown, write_baseline,
)

BASE = Baseline({"hit_at_k": 0.9, "mrr": 0.8}, 0.05, {"mrr": 0.01}, 3)


def by_name(rows):
    return {r.metric: r for r in rows}


def test_equal_to_baseline_passes():
    rows = compare(BASE, {"hit_at_k": 0.9, "mrr": 0.8})
    assert passed(rows) and all(r.delta == 0.0 for r in rows)


def test_drop_exactly_at_tolerance_passes():
    rows = by_name(compare(BASE, {"hit_at_k": 0.85, "mrr": 0.79}))
    assert rows["hit_at_k"].passed and rows["hit_at_k"].delta == -0.05
    assert rows["mrr"].passed and rows["mrr"].delta == -0.01


def test_drop_just_past_tolerance_fails():
    rows = by_name(compare(BASE, {"hit_at_k": 0.849999, "mrr": 0.789999}))
    assert not rows["hit_at_k"].passed and not rows["mrr"].passed


def test_float_noise_does_not_flip_boundary():
    # 0.7 - 0.6 is 0.09999999999999998 in floats; the gate must treat it as exactly 0.1
    b = Baseline({"m": 0.7}, 0.1, {}, 3)
    assert passed(compare(b, {"m": 0.6}))
    assert not passed(compare(b, {"m": 0.599999}))


def test_improvement_always_passes():
    rows = compare(BASE, {"hit_at_k": 1.0, "mrr": 0.95})
    assert passed(rows) and by_name(rows)["mrr"].delta == 0.15


def test_per_metric_tolerance_beats_default():
    r = by_name(compare(BASE, {"hit_at_k": 0.9, "mrr": 0.8}))
    assert (r["hit_at_k"].tolerance, r["mrr"].tolerance) == (0.05, 0.01)


def test_cli_override_beats_everything():
    r = compare(BASE, {"hit_at_k": 0.9, "mrr": 0.8}, tolerance_override=0.0)
    assert [x.tolerance for x in r] == [0.0, 0.0]
    assert not passed(compare(BASE, {"hit_at_k": 0.89, "mrr": 0.8}, tolerance_override=0.0))


def test_zero_tolerance_means_any_drop_fails_but_equal_passes():
    b = Baseline({"m": 0.5}, 0.0, {}, 3)
    assert passed(compare(b, {"m": 0.5}))
    assert not passed(compare(b, {"m": 0.499999}))


def test_missing_or_none_current_metric_fails():
    for current in ({"hit_at_k": 0.9}, {"hit_at_k": 0.9, "mrr": None}):
        rows = by_name(compare(BASE, current))
        assert not rows["mrr"].passed and rows["mrr"].current is None and rows["mrr"].delta is None


def test_extra_current_metrics_are_ignored():
    rows = compare(BASE, {"hit_at_k": 0.9, "mrr": 0.8, "judge_score": 0.1})
    assert len(rows) == 2 and passed(rows)


def test_markdown_pass_and_fail():
    ok = render_markdown(compare(BASE, {"hit_at_k": 0.9, "mrr": 0.8}))
    assert ok.splitlines()[0] == "## evalgate: PASS"
    assert "| hit_at_k | 0.9000 | 0.9000 | +0.0000 | 0.0500 | PASS |" in ok
    bad = render_markdown(compare(BASE, {"hit_at_k": 0.5, "mrr": None}))
    assert bad.splitlines()[0] == "## evalgate: FAIL"
    assert "| hit_at_k | 0.9000 | 0.5000 | -0.4000 | 0.0500 | FAIL |" in bad
    assert "| mrr | 0.8000 | missing | n/a | 0.0100 | FAIL |" in bad
    assert bad.rstrip().endswith("Regressed beyond tolerance: hit_at_k, mrr.")


def test_baseline_roundtrip_drops_none(tmp_path):
    p = tmp_path / "b.json"
    write_baseline(p, {"mrr": 0.5, "abstention_accuracy": None}, k=5)
    b = load_baseline(p)
    assert b == Baseline({"mrr": 0.5}, 0.02, {}, 5)


def test_missing_baseline_says_how_to_fix(tmp_path):
    with pytest.raises(EvalGateError, match=r"baseline not found: .*evalgate baseline"):
        load_baseline(tmp_path / "nope.json")


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("{oops", "invalid JSON"),
        ("[]", "non-empty 'metrics'"),
        ('{"metrics": {}}', "non-empty 'metrics'"),
        ('{"metrics": {"m": "high"}}', "metric 'm' must be a number"),
        ('{"metrics": {"m": true}}', "metric 'm' must be a number"),
        ('{"metrics": {"m": 1}, "version": 2}', "unsupported baseline version 2"),
        ('{"metrics": {"m": 1}, "k": 0}', "'k' must be a positive integer"),
        ('{"metrics": {"m": 1}, "default_tolerance": -0.1}', "must not be negative"),
        ('{"metrics": {"m": 1}, "tolerances": {"m": -1}}', "must not be negative"),
    ],
)
def test_bad_baselines(text, fragment):
    with pytest.raises(EvalGateError, match=fragment):
        parse_baseline(text)


def test_defaults_when_optional_fields_absent():
    b = parse_baseline(json.dumps({"metrics": {"m": 1}}))
    assert b == Baseline({"m": 1.0}, 0.02, {}, 3)
