"""Classificação de uma resposta HTTP em FOUND / MISSING / BLOCKED / ERROR / UNKNOWN.

Princípio herdado do Maigret: "o servidor não consegue responder agora" (rate limit,
CAPTCHA, desafio) NUNCA vira ausência — vira BLOCKED/UNKNOWN e, adiante, *inconclusivo*.
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

from .net import Response
from .platforms import Platform


class Kind(str, Enum):
    FOUND = "found"
    MISSING = "missing"
    BLOCKED = "blocked"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Verdict:
    kind: Kind
    reason: str


_BLOCK_TITLE = re.compile(
    r"<title>[^<]*(just a moment|attention required|access denied|captcha|are you a robot|verify you are human|"
    r"unusual traffic|checking your browser)", re.I)
_BLOCK_BODY = ("captcha", "cf-challenge", "checking your browser", "unusual traffic", "are you a robot",
               "verify you are human", "too many requests", "rate limit")
_BLOCK_STATUS = {401, 403, 407, 429, 451, 503, 999}


def get_path(obj: Any, path: str) -> Any:
    """Caminho pontilhado com índices numéricos: 'data.subreddit.title', '0.bio'."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _marker(s: str, username: str) -> str:
    return s.replace("{u}", username).lower()


def block_reason(platform: Platform, resp: Response) -> str | None:
    text_l = resp.text[:20000].lower()
    for e in platform.errors:
        if e in text_l:
            return f"marker:{e}"
    if resp.status in _BLOCK_STATUS:
        return f"http_{resp.status}"
    if resp.status == 200 and (_BLOCK_TITLE.search(resp.text[:4000]) or
                               (len(resp.body) < 20000 and any(m in text_l for m in _BLOCK_BODY))):
        return "challenge_page"
    return None


def classify(platform: Platform, resp: Response, username: str) -> Verdict:
    if resp.error or resp.status == 0:
        return Verdict(Kind.ERROR, "network:" + (resp.error or "no_response").split(":")[0])
    chk = platform.check
    typ = chk.get("type", "status_code")
    found_st = set(chk.get("found_status", [200]))
    miss_st = set(chk.get("missing_status", [404, 410]))
    text_l = resp.text.lower()

    # 1) evidência positiva decisiva vence bloqueio genérico
    if typ == "message":
        present = [_marker(s, username) for s in chk.get("present_strs", [])]
        absent = [_marker(s, username) for s in chk.get("absent_strs", [])]
        if resp.status in found_st and present and any(p in text_l for p in present) \
                and not any(a in text_l for a in absent):
            return Verdict(Kind.FOUND, "present_marker")
    elif typ == "json" and resp.status in found_st:
        try:
            data = json.loads(resp.text)
        except ValueError:
            data = None
        if data is not None:
            if chk.get("json_nonempty"):
                return Verdict(Kind.FOUND, "json_nonempty") if data else Verdict(Kind.MISSING, "json_empty")
            if chk.get("json_has") and get_path(data, chk["json_has"]) is not None:
                return Verdict(Kind.FOUND, "json_has")
            if not chk.get("json_has"):
                return Verdict(Kind.FOUND, "json_ok")
            return Verdict(Kind.MISSING, "json_field_absent")

    # 2) bloqueio
    br = block_reason(platform, resp)
    if br:
        return Verdict(Kind.BLOCKED, br)

    # 3) restante por tipo
    if resp.status in miss_st:
        return Verdict(Kind.MISSING, f"http_{resp.status}")
    if typ == "status_code":
        if resp.status in found_st:
            return Verdict(Kind.FOUND, f"http_{resp.status}")
        return Verdict(Kind.UNKNOWN, f"unexpected_status_{resp.status}")
    if typ == "message":
        absent = [_marker(s, username) for s in chk.get("absent_strs", [])]
        if any(a in text_l for a in absent):
            return Verdict(Kind.MISSING, "absent_marker")
        return Verdict(Kind.UNKNOWN, "no_marker")
    if typ == "response_url":
        path = urlsplit(resp.final_url).path.lower().rstrip("/")
        if path.endswith(f"/{username.lower()}"):
            return Verdict(Kind.FOUND, "final_url_matches")
        return Verdict(Kind.MISSING, "redirected_away")
    if typ == "json":
        return Verdict(Kind.UNKNOWN, f"unexpected_status_{resp.status}")
    return Verdict(Kind.UNKNOWN, "unsupported_check")


# --------------------------------------------------------------------------- fingerprint diferencial
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_META = re.compile(r"""<meta[^>]+(?:property|name)=["'](?:og:[a-z:]+|description)["'][^>]*content=["']([^"']*)["']""", re.I)
_TAG = re.compile(r"<[^>]+>")
_NOISE = re.compile(r"\b(?:[0-9a-f]{12,}|[A-Za-z0-9+/_-]{20,}={0,2})\b|\d+")


def norm_tokens(resp: Response, username: str) -> list[str]:
    """Texto visível + metas, com o username e ruído (nonce/ids/números) removidos."""
    raw = resp.text
    metas = " ".join(_META.findall(raw))
    body = _TAG.sub(" ", _TAGS.sub(" ", raw))
    s = _html.unescape(f"{metas} {body}").lower()
    s = s.replace(username.lower(), " ")
    s = _NOISE.sub(" ", s)
    return re.findall(r"[a-zà-ÿ$%]{2,}", s)


def shingles(tokens: list[str], n: int = 3) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
