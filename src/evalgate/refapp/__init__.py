"""Reference RAG app: BM25 retrieval plus an extractive answerer, no network."""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import Any

from ..errors import EvalGateError
from .bm25 import BM25, TOKENIZERS, Passage


def load_corpus() -> list[Passage]:
    text = resources.files(__package__).joinpath("corpus.jsonl").read_text(encoding="utf-8")
    return [Passage(**json.loads(line)) for line in text.splitlines() if line.strip()]


# "how long / how many" style questions want a number, so sentences with a digit get a bonus.
_QUANTITY = re.compile(r"\b(how (long|many|far|quickly|often|fast|much)|after how)\b", re.I)
_DIGIT_BONUS = 0.3


class RefApp:
    """Retrieve top_k passages, return the sentence that covers the most query
    terms (idf weighted). Abstain when that coverage is under min_coverage."""

    def __init__(self, passages: list[Passage], top_k: int = 3, min_coverage: float = 0.4,
                 k1: float = 1.5, b: float = 0.75, tokenizer: str = "default"):
        if tokenizer not in TOKENIZERS:
            raise EvalGateError(f"unknown tokenizer '{tokenizer}', pick one of {sorted(TOKENIZERS)}")
        self.tokenize = TOKENIZERS[tokenizer]
        self.index = BM25(passages, k1=k1, b=b, tokenizer=self.tokenize)
        self.top_k = top_k
        self.min_coverage = min_coverage

    def answer(self, question: str) -> dict[str, Any]:
        hits = self.index.search(question, self.top_k)
        retrieved = [p.id for p, _ in hits]
        q_tokens = set(self.tokenize(question))
        total = sum(self.index.idf(t) for t in q_tokens)
        wants_number = bool(_QUANTITY.search(question))
        best: tuple[float, str, str] | None = None
        for passage, _ in hits:
            for sentence in re.split(r"(?<=[.!?])\s+", passage.text):
                got = set(self.tokenize(sentence)) & q_tokens
                cov = sum(self.index.idf(t) for t in got) / total if total else 0.0
                if wants_number and re.search(r"\d", sentence):
                    cov += _DIGIT_BONUS
                if best is None or cov > best[0]:
                    best = (cov, sentence, passage.id)
        if best is None or best[0] < self.min_coverage:
            return {"answer": "", "cited_ids": [], "retrieved_ids": retrieved}
        return {"answer": best[1], "cited_ids": [best[2]], "retrieved_ids": retrieved}


def build(top_k: int = 3, min_coverage: float = 0.4, k1: float = 1.5, b: float = 0.75,
          tokenizer: str = "default") -> RefApp:
    return RefApp(load_corpus(), top_k=top_k, min_coverage=min_coverage, k1=k1, b=b,
                  tokenizer=tokenizer)
