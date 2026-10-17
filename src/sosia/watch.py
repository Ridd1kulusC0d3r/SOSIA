"""SÓSIA Watch: monitoramento contínuo com estado (perfis novos, bio/links alterados, escalonamento, remoção).

Cada execução compara o `case.json` novo com o `latest.json` do diretório de estado e emite eventos.
Também alerta quando um *conector* perde cobertura (ex.: passou de `trusted` para `blocked`) — queda
silenciosa de cobertura é o pior modo de falha de um monitor.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from pathlib import Path
from typing import Any

from .diff import PRIORITY_RANK, _fp

Key = tuple[str, str]


def _index(case: dict) -> dict[Key, dict]:
    return {(f["platform"], f["username"]): f for f in case["findings"] if f["existence"] in ("confirmed", "probable")}


def _prio(f: dict) -> str:
    return (f.get("assessment") or {}).get("priority", "INFO")


def _states(case: dict) -> dict[str, str]:
    return {c["platform"]: c["state"] for c in case["calibrations"]}


def compute_events(old: dict | None, new: dict) -> list[dict[str, Any]]:
    """Eventos entre duas execuções. `old=None` => baseline (sem eventos)."""
    if old is None:
        return []
    o, n = _index(old), _index(new)
    ev: list[dict[str, Any]] = []

    def add(kind: str, f: dict, **extra: Any) -> None:
        a = f.get("assessment") or {}
        ev.append({"event": kind, "platform": f["platform"], "username": f["username"], "url": f["url"],
                   "priority": _prio(f), "reasons": a.get("reasons", [])[:4], **extra})

    for k, f in n.items():
        if k not in o:
            add("new_profile", f)
            continue
        po, pn = _prio(o[k]), _prio(f)
        if PRIORITY_RANK.get(pn, 0) > PRIORITY_RANK.get(po, 0):
            add("escalated", f, **{"from": po})
        elif PRIORITY_RANK.get(pn, 0) < PRIORITY_RANK.get(po, 0):
            add("deescalated", f, **{"from": po})
        if _fp(o[k]) != _fp(f):
            add("profile_changed", f, before=o[k].get("profile"), after=f.get("profile"))
    for k, f in o.items():
        if k not in n:
            add("profile_gone", f)          # pode ser takedown bem-sucedido OU conector degradado: ver connector_change

    so, sn = _states(old), _states(new)
    usable = {"trusted", "trusted_no_positive", "differential"}
    for pid, st in sn.items():
        before = so.get(pid)
        if before and (before in usable) != (st in usable):
            ev.append({"event": "connector_change", "platform": pid, "from": before, "to": st,
                       "priority": "ALTO" if before in usable else "INFO",
                       "note": "cobertura perdida: ausência de achados NÃO significa ausência de perfis" if before in usable
                               else "cobertura recuperada"})
    return ev


def exit_code(events: list[dict]) -> int:
    top = 0
    for e in events:
        if e["event"] in ("new_profile", "escalated", "profile_changed", "connector_change"):
            top = max(top, PRIORITY_RANK.get(e.get("priority", "INFO"), 0))
    return 20 if top >= 4 else 10 if top >= 3 else 0


def watch_step(case: dict, state_dir: str | Path) -> tuple[list[dict], bool]:
    """Compara com o estado, grava histórico/alertas e atualiza `latest.json`. Retorna (eventos, era_baseline)."""
    sd = Path(state_dir)
    (sd / "history").mkdir(parents=True, exist_ok=True)
    latest = sd / "latest.json"
    old = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else None
    events = compute_events(old, case)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    payload = json.dumps(case, ensure_ascii=False, indent=2)
    (sd / "history" / f"{ts}-{uuid.uuid4().hex[:12]}.json").write_text(payload, encoding="utf-8")
    tmp = sd / "latest.json.tmp"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, latest)                                    # atômico: nunca deixa estado pela metade
    if events:
        with (sd / "alerts.jsonl").open("a", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps({"at": ts, **e}, ensure_ascii=False) + "\n")
    return events, old is None
