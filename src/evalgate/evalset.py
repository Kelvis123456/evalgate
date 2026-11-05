"""Eval set loading: one JSON object per line.

    {"id": "q01", "question": "...", "answerable": true,
     "gold_ids": ["p02"], "gold_fact": "256 KB"}

An unanswerable question has no gold: "answerable": false, empty gold_ids and
no gold_fact. The app is expected to abstain on those.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import EvalGateError


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    answerable: bool
    gold_ids: tuple[str, ...] = ()
    gold_fact: str | None = None


def _parse(obj: object, where: str) -> Question:
    if not isinstance(obj, dict):
        raise EvalGateError(f"{where}: expected a JSON object")
    for key in ("id", "question"):
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            raise EvalGateError(f"{where}: '{key}' must be a non-empty string")
    answerable = obj.get("answerable", True)
    if not isinstance(answerable, bool):
        raise EvalGateError(f"{where}: 'answerable' must be true or false")
    gold_ids = obj.get("gold_ids", [])
    if not isinstance(gold_ids, list) or not all(isinstance(g, str) and g for g in gold_ids):
        raise EvalGateError(f"{where}: 'gold_ids' must be a list of non-empty strings")
    gold_fact = obj.get("gold_fact")
    if gold_fact is not None and (not isinstance(gold_fact, str) or not gold_fact.strip()):
        raise EvalGateError(f"{where}: 'gold_fact' must be a non-empty string or absent")
    if answerable and (not gold_ids or gold_fact is None):
        raise EvalGateError(f"{where}: an answerable question needs gold_ids and gold_fact")
    if not answerable and (gold_ids or gold_fact is not None):
        raise EvalGateError(f"{where}: an unanswerable question must not have gold_ids or gold_fact")
    return Question(obj["id"], obj["question"], answerable, tuple(gold_ids), gold_fact)


def parse_evalset(text: str, source: str = "<string>") -> list[Question]:
    questions: list[Question] = []
    seen: dict[str, int] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{source}:{lineno}"
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalGateError(f"{where}: invalid JSON ({exc.msg})") from exc
        q = _parse(obj, where)
        if q.id in seen:
            raise EvalGateError(f"{where}: duplicate question id '{q.id}' (first seen on line {seen[q.id]})")
        seen[q.id] = lineno
        questions.append(q)
    if not questions:
        raise EvalGateError(f"{source}: eval set is empty")
    return questions


def fingerprint(text: str) -> str:
    """sha256 of the eval set with line endings, outer spaces and blank lines normalized."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def load_evalset_with_fingerprint(path: str | Path) -> tuple[list[Question], str]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalGateError(f"cannot read eval set {p}: {exc.strerror or exc}") from exc
    return parse_evalset(text, str(p)), fingerprint(text)


def load_evalset(path: str | Path) -> list[Question]:
    return load_evalset_with_fingerprint(path)[0]
