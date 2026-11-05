"""A small BM25 retriever in stdlib. Deterministic: ties break by corpus order."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i in is it of on or the to what when "
    "which who with my me you your there that this".split()
)


def tokenize(text: str) -> list[str]:
    """Casefold, split on non-word characters, drop stopwords, strip a plural s."""
    text = unicodedata.normalize("NFKC", text).casefold()
    out = []
    for tok in re.findall(r"\w+", text):
        if tok in STOPWORDS:
            continue
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        out.append(tok)
    return out


def whitespace_tokenize(text: str) -> list[str]:
    """Deliberately weak: no casefold, no punctuation stripping. 'payload?' never
    matches 'payload'. Exists so the regression demo has a tokenizer to break."""
    return text.split()


TOKENIZERS = {"default": tokenize, "whitespace": whitespace_tokenize}


@dataclass(frozen=True)
class Passage:
    id: str
    title: str
    text: str


class BM25:
    def __init__(self, passages: list[Passage], k1: float = 1.5, b: float = 0.75,
                 tokenizer=tokenize):
        self.passages = passages
        self.tokenize = tokenizer
        self.k1, self.b = k1, b
        self._tf = [Counter(tokenizer(f"{p.title} {p.text}")) for p in passages]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(passages)) if passages else 0.0
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        self._n = len(passages)
        self._df = df

    def idf(self, token: str) -> float:
        """Unseen tokens get the highest idf, so an unknown word in a question
        lowers the answerer's coverage instead of being ignored."""
        c = self._df.get(token, 0)
        return math.log(1 + (self._n - c + 0.5) / (c + 0.5))

    def search(self, query: str, top_k: int = 3) -> list[tuple[Passage, float]]:
        """Passages with a positive score, best first, at most top_k."""
        if top_k < 1 or not self.passages:
            return []
        q_tokens = self.tokenize(query)
        scored = []
        for i, tf in enumerate(self._tf):
            score = 0.0
            for t in q_tokens:
                f = tf.get(t, 0)
                if not f:
                    continue
                norm = 1 - self.b + self.b * (self._len[i] / self._avg if self._avg else 0)
                score += self.idf(t) * f * (self.k1 + 1) / (f + self.k1 * norm)
            if score > 0:
                scored.append((-score, i))
        scored.sort()
        return [(self.passages[i], -neg) for neg, i in scored[:top_k]]
