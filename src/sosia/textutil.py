"""Utilitários de texto: normalização, skeleton (UTS #39-like) e similaridade."""

from __future__ import annotations

import re
import unicodedata

from .confusables import FOLD_MULTI, FOLD_SINGLE, UNICODE_TO_ASCII

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍‎‏⁠﻿­"), None)
_SEPARATORS = re.compile(r"[\s._\-]+")
_WS = re.compile(r"\s+")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn")


def norm_text(s: str) -> str:
    """Normaliza texto livre para casamento de léxico: sem acentos, minúsculo, sem zero-width."""
    s = unicodedata.normalize("NFKC", s or "").translate(_ZERO_WIDTH)
    s = strip_accents(s).casefold()
    return _WS.sub(" ", s).strip()


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_accents(unicodedata.normalize("NFKC", s)).casefold())


def skeleton(s: str) -> str:
    """Forma canônica de comparação visual. Não use como identificador."""
    s = unicodedata.normalize("NFKC", s or "").translate(_ZERO_WIDTH)
    s = "".join(UNICODE_TO_ASCII.get(c, c) for c in s)
    s = strip_accents(s).casefold()
    s = _SEPARATORS.sub("", s)
    for seq, rep in FOLD_MULTI:
        s = s.replace(seq, rep)
    return "".join(FOLD_SINGLE.get(c, c) for c in s)


def dl_distance(a: str, b: str) -> int:
    """Damerau-Levenshtein (variante OSA)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not la or not lb:
        return max(la, lb)
    prev2: list[int] | None = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


def similarity(a: str, b: str) -> float:
    """Similaridade visual 0..1 entre dois nomes/handles (via skeleton)."""
    sa, sb = skeleton(a), skeleton(b)
    if not sa or not sb:
        return 0.0
    d = dl_distance(sa, sb)
    score = 1.0 - d / max(len(sa), len(sb))
    short, long_ = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if len(short) >= 4 and short in long_:
        score = max(score, 0.75 + 0.25 * len(short) / len(long_))
    return round(max(0.0, score), 4)
