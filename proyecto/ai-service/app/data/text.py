"""Tokenización en español + BM25 ligero (sin dependencias externas)."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuando de del desde donde dos el ella
ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue ha hay la las le les lo los mas me
mi mis muy ni no nos o os otra otro para pero poco por porque que quien se sea ser si sin sobre su sus tambien te
tiene tu tus un una uno unos unas y ya yo quiero busco necesito dame tienes hola favor puedes
""".split())


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def stem(tok: str) -> str:
    """Stemmer mínimo de plurales: tomates->tomate, limones->limon, patatas->patata."""
    if len(tok) > 4 and tok.endswith("es") and tok[-3] in "lnrdzj":
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    toks = [stem(t) for t in re.findall(r"[a-z0-9ñ]+", normalize(text)) if t not in STOPWORDS and len(t) > 1]
    # prefijos para palabras largas: desayunar ~ desayuno, congelado ~ congelados
    return toks + [t[:6] + "~" for t in toks if len(t) >= 7]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for tf, d in zip(self.tf, self.docs):
            s, dl = 0.0, len(d)
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out

    def top(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        sc = self.scores(query)
        idx = sorted(range(len(sc)), key=lambda i: sc[i], reverse=True)
        return [(i, sc[i]) for i in idx[:k] if sc[i] > 0]
