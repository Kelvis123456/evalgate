"""Optional LLM-judge metric. Off by default and never used in this repo's CI.

Set EVALGATE_JUDGE=module:factory to turn it on. The factory takes no
arguments and returns an object with score(question, answer, gold_fact) -> float
in [0, 1]. evalgate ships the interface and one offline stub; it does not ship
any vendor client. Wiring a real model in is the user's job.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

from .app import load_factory
from .errors import EvalGateError

ENV_VAR = "EVALGATE_JUDGE"


class Judge(Protocol):
    def score(self, question: str, answer: str, gold_fact: str) -> float: ...


class OverlapStubJudge:
    """Example only: fraction of gold-fact words found in the answer.

    This is not an LLM and is not a good judge. It exists to show the shape
    of the interface and to exercise the code path in tests.
    """

    def score(self, question: str, answer: str, gold_fact: str) -> float:
        gold = set(re.findall(r"\w+", gold_fact.casefold()))
        if not gold:
            return 0.0
        got = set(re.findall(r"\w+", answer.casefold()))
        return len(gold & got) / len(gold)


def judge_from_env(env: dict[str, str] | None = None) -> Judge | None:
    spec = (env if env is not None else os.environ).get(ENV_VAR, "").strip()
    if not spec:
        return None
    try:
        judge = load_factory(spec)()
    except EvalGateError:
        raise
    except Exception as exc:
        raise EvalGateError(f"{ENV_VAR}='{spec}' raised {type(exc).__name__}: {exc}") from exc
    if not callable(getattr(judge, "score", None)):
        raise EvalGateError(f"{ENV_VAR}='{spec}' did not return an object with score()")
    return judge
