"""Command line entry point: evalgate run | baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .app import load_app, parse_params
from .errors import EvalGateError
from .evalset import load_evalset
from .gate import Baseline, compare, load_baseline, passed, render_markdown, write_baseline
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
    return p


def _run(args: argparse.Namespace) -> int:
    questions = load_evalset(args.evalset)
    app = load_app(args.app, parse_params(args.param))
    judge = judge_from_env()
    if args.command == "baseline":
        k = 3
        result = run_evalset(app, questions, k=k, judge=judge)
        write_baseline(args.baseline, result.metrics, k)
        print(f"wrote {args.baseline}")
        return 0
    baseline: Baseline = load_baseline(args.baseline)
    if args.tolerance is not None and args.tolerance < 0:
        raise EvalGateError("--tolerance must not be negative")
    result = run_evalset(app, questions, k=baseline.k, judge=judge)
    rows = compare(baseline, result.metrics, args.tolerance)
    report = render_markdown(rows)
    sys.stdout.write(report)
    if args.report_file:
        Path(args.report_file).write_text(report, encoding="utf-8")
    return 0 if passed(rows) else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except EvalGateError as exc:
        print(f"evalgate: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
