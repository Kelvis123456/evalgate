"""The contract between evalgate and the app under test."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import EvalGateError


class App(Protocol):
    """Anything with answer(question) returning a dict with these keys:

    answer        str, the final text. An empty string means the app abstained.
    cited_ids     list[str], passage ids the answer claims to rely on.
    retrieved_ids list[str], passage ids from retrieval, best first.
    """

    def answer(self, question: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Result:
    answer: str
    cited_ids: tuple[str, ...]
    retrieved_ids: tuple[str, ...]

    @property
    def abstained(self) -> bool:
        return not self.answer.strip()


def _id_list(raw: object, key: str) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)) or not all(isinstance(i, str) for i in raw):
        raise EvalGateError(f"app result: '{key}' must be a list of strings")
    return tuple(raw)


def normalize_result(raw: object) -> Result:
    if not isinstance(raw, dict):
        raise EvalGateError("app result: answer() must return a dict")
    answer = raw.get("answer")
    if not isinstance(answer, str):
        raise EvalGateError("app result: 'answer' must be a string")
    return Result(
        answer,
        _id_list(raw.get("cited_ids", []), "cited_ids"),
        _id_list(raw.get("retrieved_ids", []), "retrieved_ids"),
    )


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    if value in ("true", "false"):
        return value == "true"
    return value


def parse_params(pairs: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise EvalGateError(f"bad --param '{pair}', expected key=value")
        params[key] = _coerce(value)
    return params


def load_factory(spec: str):
    """Resolve 'package.module:attr' to a callable."""
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise EvalGateError(f"bad app spec '{spec}', expected module:factory")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise EvalGateError(f"cannot import '{module_name}': {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise EvalGateError(f"module '{module_name}' has no attribute '{attr}'") from exc


def load_app(spec: str, params: dict[str, Any] | None = None) -> App:
    """Build the app by calling the factory with the --param values as kwargs."""
    factory = load_factory(spec)
    try:
        app = factory(**(params or {}))
    except TypeError as exc:
        raise EvalGateError(f"factory '{spec}' rejected params {params}: {exc}") from exc
    if not callable(getattr(app, "answer", None)):
        raise EvalGateError(f"factory '{spec}' did not return an object with answer()")
    return app
