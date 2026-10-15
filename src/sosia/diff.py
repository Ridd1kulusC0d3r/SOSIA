"""Comparação entre duas execuções (semente do SÓSIA Watch): novos perfis, mudanças de bio/links/prioridade."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PRIORITY_RANK = {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAIXO": 1, "INFO": 0}


def _load(path: str | Path) -> dict[tuple[str, str], dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(f["platform"], f["username"]): f for f in data["findings"]
            if f["existence"] in ("confirmed", "probable")}


def _fp(f: dict) -> str:
    p = f.get("profile") or {}
    blob = json.dumps([p.get("display_name"), p.get("bio"), sorted(p.get("links") or [])], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def diff_cases(old_path: str | Path, new_path: str | Path) -> dict:
    old, new = _load(old_path), _load(new_path)
    out: dict[str, list] = {"new": [], "gone": [], "bio_changed": [], "priority_changed": []}
    for k, f in new.items():
        if k not in old:
            out["new"].append({"platform": k[0], "username": k[1], "priority": (f["assessment"] or {}).get("priority")})
            continue
        o = old[k]
        if _fp(o) != _fp(f):
            out["bio_changed"].append({"platform": k[0], "username": k[1], "before": o.get("profile"), "after": f.get("profile")})
        po, pn = (o["assessment"] or {}).get("priority"), (f["assessment"] or {}).get("priority")
        if po != pn:
            out["priority_changed"].append({"platform": k[0], "username": k[1], "from": po, "to": pn,
                                            "escalated": PRIORITY_RANK.get(pn, 0) > PRIORITY_RANK.get(po, 0)})
    for k in old:
        if k not in new:
            out["gone"].append({"platform": k[0], "username": k[1]})
    return out
