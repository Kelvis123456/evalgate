"""Command line entry point: evalgate run | baseline."""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from . import __version__
from .app import load_app, parse_params
from .errors import EvalGateError
from .evalset import load_evalset_with_fingerprint
from .gate import (
    DEFAULT_TOLERANCE, Baseline, check_evalset, compare, load_baseline, lower_metrics, passed,
    render_markdown, write_baseline,
)
from .judge import judge_from_env
from .runner import run_evalset

DEFAULT_APP = "evalgate.refapp:build"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="evalgate", description="CI ship gate for RAG and LLM apps.")
    p.add_argument("--version", action="version", version=f"evalgate {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_ in (("run", "run the eval set and gate against the baseline"),
                        ("baseline", "run the eval set and write a new baseline")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--evalset", default="evals/questions.jsonl")
        s.add_argument("--baseline", default="baseline.json")
        s.add_argument("--app", default=DEFAULT_APP, help="module:factory (default: reference app)")
        s.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                       help="keyword argument for the app factory, repeatable")
        if name == "run":
            s.add_argument("--tolerance", type=float, default=None,
                           help="override every tolerance in the baseline")
            s.add_argument("--report-file", help="also write the Markdown report here")
        else:
            s.add_argument("--k", type=int, default=None,
                           help="k for hit_at_k (default: keep the existing baseline's k, else 3)")
            s.add_argument("--tolerance", type=float, default=None,
                           help="default tolerance (default: keep the existing one, else 0.02)")
            s.add_argument("--allow-regression", action="store_true",
                           help="write the baseline even if a metric is lower than the existing one")
            s.add_argument("--with-judge", action="store_true",
                           help="run the EVALGATE_JUDGE judge and store judge_score")
    return p


def _write_baseline(args: argparse.Namespace, app, questions, digest: str) -> int:
    existing = load_baseline(args.baseline) if Path(args.baseline).is_file() else None
    k = args.k if args.k is not None else (existing.k if existing else 3)
    if k < 1:
        raise EvalGateError("--k must be at least 1")
    tolerance = args.tolerance if args.tolerance is not None else (
        existing.default_tolerance if existing else DEFAULT_TOLERANCE)
    judge = None
    if args.with_judge:
        judge = judge_from_env()
        if judge is None:
            raise EvalGateError("--with-judge needs EVALGATE_JUDGE=module:factory")
    result = run_evalset(app, questions, k=k, judge=judge)
    if existing and not args.allow_regression:
        lower = lower_metrics(existing, result.metrics)
        if lower:
            raise EvalGateError(
                "refusing to write a baseline that is lower than the existing baseline: "
                + "; ".join(lower) + ". Pass --allow-regression if that is intended."
            )
    write_baseline(args.baseline, result.metrics, k, tolerance,
                   evalset=(digest, len(questions)),
                   tolerances=existing.tolerances if existing else None)
    print(f"wrote {args.baseline}")
    return 0


def _run(args: argparse.Namespace) -> int:
    questions, digest = load_evalset_with_fingerprint(args.evalset)
    if args.tolerance is not None and (not math.isfinite(args.tolerance) or args.tolerance < 0):
        raise EvalGateError("--tolerance must be a finite number, not negative")
    app = load_app(args.app, parse_params(args.param))
    if args.command == "baseline":
        return _write_baseline(args, app, questions, digest)
    judge = judge_from_env()
    baseline: Baseline = load_baseline(args.baseline)
    check_evalset(baseline, digest, len(questions))
    result = run_evalset(app, questions, k=baseline.k, judge=judge)
    rows = compare(baseline, result.metrics, args.tolerance)
    report = render_markdown(rows)
    sys.stdout.write(report)
    if args.report_file:
        try:
            Path(args.report_file).write_text(report, encoding="utf-8")
        except OSError as exc:
            raise EvalGateError(f"cannot write report {args.report_file}: {exc.strerror or exc}") from exc
    return 0 if passed(rows) else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # The `evalgate` script does not put the cwd on sys.path (python -m does), so do it
    # explicitly: --app mymodule:build then resolves the same way for both.
    cwd = os.getcwd()
    if cwd not in sys.path and "" not in sys.path:
        sys.path.insert(0, cwd)
    try:
        return _run(args)
    except EvalGateError as exc:
        if os.environ.get("EVALGATE_DEBUG"):
            raise
        print(f"evalgate: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # exit 1 is reserved for "quality regressed", so nothing else may end up there
        if os.environ.get("EVALGATE_DEBUG"):
            raise
        print(f"evalgate: error: unexpected {type(exc).__name__}: {exc} "
              "(set EVALGATE_DEBUG=1 for the traceback)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
