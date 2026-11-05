from evalgate.gate import Baseline, compare, passed, render_markdown

BASE = Baseline({"mrr": 0.8}, 0.02, {}, 3)


def test_metric_missing_from_baseline_is_shown_but_not_gated():
    rows = compare(BASE, {"mrr": 0.8, "citation_precision": 0.1, "judge_score": None})
    assert [r.metric for r in rows] == ["mrr", "citation_precision"]  # None metrics are not applicable
    assert passed(rows)
    out = render_markdown(rows)
    assert "| citation_precision | n/a | 0.1000 | n/a | n/a | new (not gated) |" in out
    assert out.startswith("## evalgate: PASS")


def test_new_metric_does_not_hide_a_regression():
    rows = compare(BASE, {"mrr": 0.1, "extra": 1.0})
    assert not passed(rows)
    assert "Regressed beyond tolerance: mrr." in render_markdown(rows)
