"""Compare a run against the committed baseline and render the verdict."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .errors import EvalGateError

DEFAULT_TOLERANCE = 0.02
BASELINE_VERSION = 1


@dataclass(frozen=True)
class Baseline:
    metrics: dict[str, float]
    default_tolerance: float
    tolerances: dict[str, float]
    k: int
    evalset_sha256: str | None = None
    questions: int | None = None


@dataclass(frozen=True)
class Row:
    metric: str
    baseline: float | None
    current: float | None
    delta: float | None
    tolerance: float | None
    passed: bool
    new: bool = False  # produced by the run but absent from the baseline, so not gated


def _num(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvalGateError(f"baseline: {what} must be a number")
    if not math.isfinite(value):
        raise EvalGateError(f"baseline: {what} must be finite, got {value}")
    return float(value)


def _reject_constant(name: str):
    raise EvalGateError(f"baseline: {name} is not allowed, numbers must be finite")


def parse_baseline(text: str, source: str = "<string>") -> Baseline:
    try:
        raw = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise EvalGateError(f"{source}: invalid JSON ({exc.msg} at line {exc.lineno})") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("metrics"), dict) or not raw["metrics"]:
        raise EvalGateError(f"{source}: expected an object with a non-empty 'metrics' object")
    if raw.get("version", BASELINE_VERSION) != BASELINE_VERSION:
        raise EvalGateError(f"{source}: unsupported baseline version {raw['version']}")
    metrics = {name: _num(v, f"metric '{name}'") for name, v in raw["metrics"].items()}
    default = _num(raw.get("default_tolerance", DEFAULT_TOLERANCE), "default_tolerance")
    tolerances = {n: _num(v, f"tolerance '{n}'") for n, v in (raw.get("tolerances") or {}).items()}
    k = raw.get("k", 3)
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise EvalGateError(f"{source}: 'k' must be a positive integer")
    if default < 0 or any(t < 0 for t in tolerances.values()):
        raise EvalGateError(f"{source}: tolerances must not be negative")
    ev = raw.get("evalset")
    sha, count = None, None
    if ev is not None:
        if (not isinstance(ev, dict) or not isinstance(ev.get("sha256"), str)
                or isinstance(ev.get("questions"), bool) or not isinstance(ev.get("questions"), int)):
            raise EvalGateError(f"{source}: 'evalset' must be {{\"sha256\": str, \"questions\": int}}")
        sha, count = ev["sha256"], ev["questions"]
    return Baseline(metrics, default, tolerances, k, sha, count)


def load_baseline(path: str | Path) -> Baseline:
    p = Path(path)
    if not p.is_file():
        raise EvalGateError(
            f"baseline not found: {p}. Create one with 'evalgate baseline' and commit it."
        )
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvalGateError(f"cannot read baseline {p}: {exc}") from exc
    return parse_baseline(text, str(p))


def write_baseline(path: str | Path, metrics: dict[str, float | None], k: int,
                   default_tolerance: float = DEFAULT_TOLERANCE,
                   evalset: tuple[str, int] | None = None,
                   tolerances: dict[str, float] | None = None) -> None:
    clean = {n: v for n, v in metrics.items() if v is not None}
    payload: dict = {"version": BASELINE_VERSION, "k": k, "default_tolerance": default_tolerance,
                     "tolerances": tolerances or {}}
    if evalset is not None:
        payload["evalset"] = {"sha256": evalset[0], "questions": evalset[1]}
    payload["metrics"] = clean
    try:
        Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise EvalGateError(f"cannot write baseline {path}: {exc.strerror or exc}") from exc


def lower_metrics(old: Baseline, new: dict[str, float | None]) -> list[str]:
    """Describe every metric in `old` that `new` lowers or no longer produces."""
    out = []
    for name, was in old.metrics.items():
        now = new.get(name)
        if now is None:
            out.append(f"{name} {was:.4f} -> missing")
        elif now < was:
            out.append(f"{name} {was:.4f} -> {now:.4f}")
    return out


def check_evalset(baseline: Baseline, sha256: str, questions: int) -> None:
    """The baseline only means something for the eval set it was measured on."""
    if baseline.evalset_sha256 is None:
        raise EvalGateError("baseline does not record its eval set; re-run 'evalgate baseline' and commit it")
    if baseline.evalset_sha256 != sha256:
        raise EvalGateError(
            f"eval set changed since the baseline was written (baseline: {baseline.evalset_sha256[:12]}, "
            f"{baseline.questions} questions; now: {sha256[:12]}, {questions} questions). "
            "Review the change, then run 'evalgate baseline' and commit the result."
        )


def compare(baseline: Baseline, current: dict[str, float | None],
            tolerance_override: float | None = None) -> list[Row]:
    """A metric fails when it drops by strictly more than its tolerance.

    Improvements always pass. A baseline metric that the current run did not
    produce fails, because silently dropping a check must not pass the gate.
    """
    rows = []
    for name, base in baseline.metrics.items():
        if tolerance_override is not None:
            tol = tolerance_override
        else:
            tol = baseline.tolerances.get(name, baseline.default_tolerance)
        cur = current.get(name)
        if cur is None:
            rows.append(Row(name, base, None, None, tol, False))
            continue
        if not math.isfinite(cur):
            raise EvalGateError(f"metric '{name}' is {cur}, metrics must be finite")
        delta = round(cur - base, 6)
        rows.append(Row(name, base, cur, delta, tol, round(-delta, 6) <= tol))
    for name, cur in current.items():
        if name not in baseline.metrics and cur is not None:
            if not math.isfinite(cur):
                raise EvalGateError(f"metric '{name}' is {cur}, metrics must be finite")
            rows.append(Row(name, None, cur, None, None, True, new=True))
    return rows


def passed(rows: list[Row]) -> bool:
    return all(r.passed for r in rows)


def render_markdown(rows: list[Row]) -> str:
    ok = passed(rows)
    failed = [r.metric for r in rows if not r.passed]
    lines = [
        "## evalgate: " + ("PASS" if ok else "FAIL"),
        "",
        "| Metric | Baseline | Current | Delta | Tolerance | Status |",
        "| --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        cur = "missing" if r.current is None else f"{r.current:.4f}"
        delta = "n/a" if r.delta is None else f"{r.delta:+.4f}"
        base = "n/a" if r.baseline is None else f"{r.baseline:.4f}"
        tol = "n/a" if r.tolerance is None else f"{r.tolerance:.4f}"
        status = "new (not gated)" if r.new else ("PASS" if r.passed else "FAIL")
        lines.append(f"| {r.metric} | {base} | {cur} | {delta} | {tol} | {status} |")
    lines.append("")
    if ok:
        lines.append("No metric dropped more than its tolerance below the baseline.")
    else:
        lines.append("Regressed beyond tolerance: " + ", ".join(failed) + ".")
    return "\n".join(lines) + "\n"
