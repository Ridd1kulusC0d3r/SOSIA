"""Descoberta por BUSCA nativa da plataforma (Bluesky, Mastodon) — o complemento da enumeração de variantes.

Achado do bench real (139 marcas, 5.327 contas devolvidas pela busca): a busca encontra por construção as contas com a marca no
handle; a enumeração de variantes cobre ~3% delas. Mas "contém a marca" ≠ impersonação: o resultado é uma LISTA de candidatas
para triagem, não alertas. Marcas cuja busca devolve dezenas de contas (palavras comuns, marcas gigantes) são ruidosas.
"""

from __future__ import annotations

import html as _html
import json
import re
from typing import Any
from urllib.parse import quote

from .net import Fetcher
from .textutil import similarity, skeleton

_TAG = re.compile(r"<[^>]+>")


def discover(label: str, fetcher: Fetcher, extra_queries: tuple[str, ...] = (), errors: list[str] | None = None) -> list[dict[str, Any]]:
    """Busca pelo nome. Falhas (HTTP != 200, JSON inválido) NÃO são silenciosas: vão para `errors` quando fornecida."""
    out: dict[tuple[str, str], dict] = {}
    err = errors if errors is not None else []
    queries = [(label, "plain")] + [(f"{label} {x}", "lure") for x in extra_queries]
    for q, qkind in queries:
        qq = quote(q)
        cursor = None
        for _ in range(2 if qkind == "plain" else 1):
            url = f"https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?q={qq}&limit=100" + (f"&cursor={quote(cursor)}" if cursor else "")
            r = fetcher.get(url)
            if r.status != 200:
                err.append(f"bluesky:{r.status or r.error}")
                break
            try:
                d = json.loads(r.text)
                for a in d.get("actors", []):
                    out.setdefault(("bluesky", a["handle"]), {
                        "platform": "bluesky", "handle": a["handle"], "display_name": a.get("displayName"),
                        "bio": a.get("description"), "created": a.get("createdAt"), "query_kind": qkind,
                        "verified": bool((a.get("verification") or {}).get("verifiedStatus") == "valid")})
            except (ValueError, KeyError, TypeError):
                err.append("bluesky:invalid_json")
                break
            cursor = d.get("cursor")
            if not cursor:
                break
        r = fetcher.get(f"https://mastodon.social/api/v2/search?q={qq}&type=accounts&limit=40")
        if r.status != 200:
            err.append(f"mastodon:{r.status or r.error}")
            continue
        try:
            for a in json.loads(r.text).get("accounts", []):
                out.setdefault(("mastodon", a["acct"]), {
                    "platform": "mastodon", "handle": a["acct"], "display_name": a.get("display_name"),
                    "bio": _html.unescape(_TAG.sub(" ", a.get("note") or "")).strip(), "created": a.get("created_at"),
                    "query_kind": qkind, "verified": False})
        except (ValueError, KeyError, TypeError):
            err.append("mastodon:invalid_json")
    return list(out.values())


def local_part(acct: dict) -> str | None:
    h = acct["handle"].lower()
    if acct["platform"] == "bluesky":
        return h[:-len(".bsky.social")] if h.endswith(".bsky.social") else None     # domínio próprio => não enumerável
    return h.split("@")[0]


def handle_class(base: str, local: str) -> str:
    sb, sl = skeleton(base), skeleton(local)
    if sl == sb:
        return "exact"
    if len(sb) >= 4 and sb in sl:
        return "contains"
    if similarity(base, local) >= 0.7:
        return "similar"
    return "unrelated"


SATURATION_THRESHOLD = 40   # handles contendo a marca
SEARCH_CAP_THRESHOLD = 150  # resultados do Bluesky (a busca pagina até ~195): perto do teto = nome comum/popular
# Limiares escolhidos olhando as 140 marcas do bench real (18 sinalizadas, 13%): NÃO são independentes dos dados.


def estimate_ambiguity(label: str, accounts: list[dict[str, Any]]) -> dict[str, Any]:
    """Saturação da busca como proxy de ambiguidade (palavra comum/marca gigante). Heurística, não verdade."""
    contains = [a for a in accounts if (lp := local_part(a)) and handle_class(label, lp) in ("contains", "similar")]
    exact = [a for a in accounts if (lp := local_part(a)) and handle_class(label, lp) == "exact"]
    n, n_bsky = len(contains), sum(1 for a in accounts if a["platform"] == "bluesky")
    saturated = n >= SATURATION_THRESHOLD or n_bsky >= SEARCH_CAP_THRESHOLD
    return {"label": label, "accounts_returned": len(accounts), "bluesky_results": n_bsky, "handles_containing_brand": n,
            "exact_name_accounts": len(exact), "saturated": saturated,
            "advice": ("busca saturada: a marca é palavra comum ou muito popular. Defina `ambiguous = true` no sosia.toml e "
                       "exija domínio/telefone/visual além de nome. Espere muito ruído." if saturated else
                       "busca não saturada: lista de candidatas de tamanho tratável.")}
