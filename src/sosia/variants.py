"""Motor de variantes de username/handle.

Famílias inspiradas em dnstwist / AIL typo-squatting (omissão, repetição, transposição,
substituição por teclas vizinhas, inserção, troca de vogal, homóglifos) + famílias que só
fazem sentido em handles sociais (afixos de autoridade/atendimento/promoção/golpe em pt-BR,
separadores, preenchimento, dígitos). Regras de domínio NÃO são transplantadas às cegas:
cada plataforma impõe sua própria restrição de caracteres/tamanho (ver `Constraint`).

Não gera clones que usam um handle completamente diferente: para isso existem
`display_variants` e `pivots` (descoberta fora da enumeração de handles).
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from . import lexicon as L
from .confusables import ASCII_LOOKALIKES, ASCII_TO_UNICODE
from .textutil import dl_distance, similarity, slugify

KEYBOARD = {  # QWERTY; ABNT2 compartilha o layout de letras
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok",
    "o": "ipl", "p": "ol", "a": "qsz", "s": "awdx", "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn",
    "j": "hukm", "k": "jil", "l": "kop", "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhjm", "m": "njk",
}
VOWELS = "aeiou"
SEPS = "._-"


# --------------------------------------------------------------------------- restrição por plataforma
@dataclass(frozen=True)
class Constraint:
    regex: re.Pattern[str]
    min_len: int = 1
    max_len: int = 64
    forbid: tuple[re.Pattern[str], ...] = ()
    separators: str = SEPS
    case_insensitive: bool = True

    def valid(self, s: str) -> bool:
        if not (self.min_len <= len(s) <= self.max_len):
            return False
        t = s.lower() if self.case_insensitive else s
        if not self.regex.match(t):
            return False
        return not any(f.search(t) for f in self.forbid)


# --------------------------------------------------------------------------- operadores (b = base minúscula)
def _omission(b: str) -> Iterator[str]:
    for i in range(len(b)):
        yield b[:i] + b[i + 1:]


def _repetition(b: str) -> Iterator[str]:
    for i, c in enumerate(b):
        if c.isalnum():
            yield b[:i] + c + b[i:]


def _transposition(b: str) -> Iterator[str]:
    for i in range(len(b) - 1):
        if b[i] != b[i + 1]:
            yield b[:i] + b[i + 1] + b[i] + b[i + 2:]


def _replacement(b: str) -> Iterator[str]:
    for i, c in enumerate(b):
        for k in KEYBOARD.get(c, ""):
            yield b[:i] + k + b[i + 1:]


def _insertion(b: str) -> Iterator[str]:
    for i, c in enumerate(b):
        for k in KEYBOARD.get(c, ""):
            yield b[:i] + k + b[i:]
            yield b[:i + 1] + k + b[i + 1:]


def _vowel_swap(b: str) -> Iterator[str]:
    for i, c in enumerate(b):
        if i > 0 and c in VOWELS:
            for v in VOWELS:
                if v != c:
                    yield b[:i] + v + b[i + 1:]


def _homoglyph(b: str) -> Iterator[str]:
    for i, c in enumerate(b):
        for rep in ASCII_LOOKALIKES.get(c, ()):
            yield b[:i] + rep + b[i + 1:]
    # todas as ocorrências da mesma letra de uma vez (ex.: "cafeteria" -> "c4fet3ri4" parcial)
    for c, reps in ASCII_LOOKALIKES.items():
        if b.count(c) > 1:
            for rep in reps:
                yield b.replace(c, rep)
    # direção inversa: "rn"->"m", "vv"->"w", "cl"->"d"
    for seq, rep in (("rn", "m"), ("vv", "w"), ("cl", "d")):
        start = b.find(seq)
        while start != -1:
            yield b[:start] + rep + b[start + len(seq):]
            start = b.find(seq, start + 1)


def _separator(b: str) -> Iterator[str]:
    bare = re.sub(r"[._\-]", "", b)
    if bare != b:
        yield bare
    for i in range(1, len(bare)):
        for s in SEPS:
            yield bare[:i] + s + bare[i:]
    for s in SEPS:  # troca de separador existente
        if s in b:
            for t in SEPS:
                if t != s:
                    yield b.replace(s, t)


def _pad(b: str) -> Iterator[str]:
    for s in ("_", ".", "-", "__"):
        yield b + s
    yield "_" + b
    yield "." + b


def _digits(b: str, year: int) -> Iterator[str]:
    for d in L.DIGIT_SUFFIXES + [str(year), str(year)[2:], str(year - 1)[2:]]:
        yield b + d


@dataclass
class Variant:
    value: str
    families: set[str] = field(default_factory=set)
    distance: int = 0
    similarity: float = 0.0
    rank: float = 0.0

    def to_dict(self) -> dict:
        return {"value": self.value, "families": sorted(self.families), "distance": self.distance,
                "similarity": self.similarity, "rank": round(self.rank, 4)}


class VariantEngine:
    def __init__(self, base: str, *, extra_affixes: Iterable[str] = (), year: int | None = None,
                 masses: dict[str, float] | None = None) -> None:
        self.raw_base = base
        self.base = re.sub(r"[^a-z0-9._\-]", "", slugify_keep(base))
        if not self.base:
            raise ValueError("handle base vazio após normalização")
        self.year = year or _dt.date.today().year
        self.extra_affixes = [slugify(a) for a in extra_affixes if slugify(a)]
        self.masses = {**L.FAMILY_MASS, **(masses or {})}

    # -- geração -------------------------------------------------------------------------
    def _raw(self) -> Iterator[tuple[str, str]]:
        b = self.base
        simple: list[tuple[str, Callable[[str], Iterator[str]]]] = [
            ("omission", _omission), ("repetition", _repetition), ("transposition", _transposition),
            ("replacement", _replacement), ("insertion", _insertion), ("vowel_swap", _vowel_swap),
            ("homoglyph", _homoglyph), ("separator", _separator), ("pad", _pad),
        ]
        for fam, fn in simple:
            for v in fn(b):
                yield v, fam
        for v in _digits(b, self.year):
            yield v, "digits"

        joiners = ("", "_", ".", "-")
        for cat, words in L.AFFIXES.items():
            words = words + (self.extra_affixes if cat == "commerce" else [])
            for w in words:
                for j in joiners:
                    yield b + j + w, f"affix_{cat}"
                    yield w + j + b, f"affix_{cat}"

        # afixo + cauda numérica ("marca_suporte01", "marcaoficial2")
        for w in L.AFFIXES["authority"][:3] + L.AFFIXES["support"][:5]:
            for j in ("", "_"):
                for d in ("1", "2", "01", "24"):
                    yield f"{b}{j}{w}{d}", "affix_digits"

        # afixos de autoridade + atendimento ("marca_suporte_oficial")
        for a in L.AFFIXES["authority"][:5]:
            for s in L.AFFIXES["support"][:6]:
                for j in ("", "_"):
                    yield f"{b}{j}{s}{j}{a}", "affix_double"
                    yield f"{b}{j}{a}{j}{s}", "affix_double"

        # afixo com erro de digitação ("marca_ofical", "marca_0ficial")
        for w in ("oficial", "official", "suporte", "support", "atendimento"):
            typos = set(_omission(w)) | set(_transposition(w)) | set(_homoglyph(w))
            for t in typos:
                yield b + t, "affix_typo"
                yield f"{b}_{t}", "affix_typo"

    def _compose(self, seeds: list[str]) -> Iterator[tuple[str, str]]:
        """Profundidade 2: um truque no corpo + afixo de autoridade/atendimento."""
        words = L.AFFIXES["authority"][:3] + L.AFFIXES["support"][:5]
        for s in seeds:
            for w in words:
                for j in ("", "_"):
                    yield s + j + w, "compose"

    def generate(self, *, exclude: Iterable[str] = (), constraint: Constraint | None = None,
                 families: set[str] | None = None, compose_seeds: int = 60) -> list[Variant]:
        excl = {self.base, *(e.lower() for e in exclude)}
        found: dict[str, Variant] = {}

        def add(value: str, fam: str) -> None:
            value = value.strip().lower()
            if not value or value in excl:
                return
            if families and fam not in families and fam != "compose":
                return
            if constraint and not constraint.valid(value):
                return
            v = found.get(value)
            if v is None:
                v = found[value] = Variant(value)
            v.families.add(fam)

        for value, fam in self._raw():
            add(value, fam)

        # sementes de composição: melhores variantes de 1 truque por similaridade
        seeds = sorted(
            (v for v in found.values() if v.families & {"homoglyph", "transposition", "omission", "repetition"}),
            key=lambda v: -similarity(self.base, v.value),
        )[:compose_seeds]
        for value, fam in self._compose([s.value for s in seeds]):
            add(value, fam)

        out = list(found.values())
        for v in out:
            v.distance = dl_distance(self.base, v.value)
            v.similarity = similarity(self.base, v.value)
        weight = {id(v): 0.5 + 0.5 * v.similarity for v in out}
        fam_total: dict[str, float] = {}
        for v in out:
            for f in v.families:
                fam_total[f] = fam_total.get(f, 0.0) + weight[id(v)]
        for v in out:
            v.rank = 100.0 * max(self.masses.get(f, 0.02) * weight[id(v)] / fam_total[f] for f in v.families)
        out.sort(key=lambda v: (-v.rank, v.value))
        return out


def slugify_keep(s: str) -> str:
    """Como slugify, mas preserva . _ - (separadores legítimos no handle base)."""
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn")
    return s.casefold().replace(" ", "")


# --------------------------------------------------------------------------- nome de exibição + pivôs
def display_variants(name: str, limit: int = 40) -> list[dict]:
    """Variantes do nome de exibição (não enumeráveis por URL): para busca manual/por plataforma."""
    out: list[dict] = []
    seen: set[str] = {name}

    def add(v: str, fam: str) -> None:
        if v not in seen:
            seen.add(v)
            out.append({"value": v, "family": fam})

    for suffix in ("Oficial", "Official", "Suporte", "Atendimento", "SAC", "Brasil", "Promoções", "Sorteios"):
        add(f"{name} {suffix}", "display_affix")
    low = name.lower()
    for i, c in enumerate(low):
        for u in ASCII_TO_UNICODE.get(c, [])[:2]:
            add(name[:i] + u + name[i + 1:], "display_unicode_confusable")
    add(name[:1] + "​" + name[1:], "display_invisible_char")
    add(name.replace(" ", "  "), "display_spacing")
    return out[:limit]


def pivots(brand_names: list[str], domains: list[str], handle_hint: str | None = None) -> list[dict]:
    """Consultas de descoberta para clones sem handle parecido (execução manual/assistida)."""
    out: list[dict] = []
    lures = '("oficial" OR "suporte" OR "atendimento" OR "sorteio" OR "pix" OR "whatsapp")'
    sites = ["instagram.com", "tiktok.com", "facebook.com", "x.com", "t.me", "linktr.ee", "youtube.com", "threads.net"]
    for name in brand_names:
        for s in sites:
            out.append({"kind": "dork", "query": f'site:{s} "{name}" {lures}'})
        for d in domains:
            out.append({"kind": "dork", "query": f'"{name}" ("chave pix" OR "taxa" OR "liberação") -site:{d}'})
    for d in domains:
        out.append({"kind": "dork", "query": f'"{d}" (site:linktr.ee OR site:instagram.com OR site:t.me)'})
        out.append({"kind": "manual", "query": d, "note": "busque o domínio oficial em páginas de link-na-bio e nas buscas nativas (link ≠ vínculo: exige link recíproco)"})
    if handle_hint:
        out.append({"kind": "manual", "query": f'{handle_hint}', "note": "busca nativa de cada plataforma por nome/palavras-chave"})
    return out
