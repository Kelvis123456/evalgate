import json

import pytest

from evalgate.cli import main
from evalgate.errors import EvalGateError
from evalgate.gate import Baseline, compare, parse_baseline


def test_cli_rejects_non_finite_tolerance(capsys):
    for bad in ("inf", "nan", "-inf"):
        assert main(["run", f"--tolerance={bad}"]) == 2
        assert "finite" in capsys.readouterr().err


@pytest.mark.parametrize("token", ["Infinity", "NaN", "-Infinity"])
def test_baseline_rejects_non_finite_tolerance_and_metrics(token):
    with pytest.raises(EvalGateError, match="finite"):
        parse_baseline('{"metrics": {"m": 1}, "default_tolerance": %s}' % token)
    with pytest.raises(EvalGateError, match="finite"):
        parse_baseline('{"metrics": {"m": %s}}' % token)
    with pytest.raises(EvalGateError, match="finite"):
        parse_baseline('{"metrics": {"m": 1}, "tolerances": {"m": %s}}' % token)


def test_non_finite_current_metric_is_an_error():
    b = Baseline({"m": 0.5}, 0.02, {}, 3)
    for bad in (float("nan"), float("inf")):
        with pytest.raises(EvalGateError, match="finite"):
            compare(b, {"m": bad})
