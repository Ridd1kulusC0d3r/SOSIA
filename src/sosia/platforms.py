"""Conectores de plataforma (dados em JSON, extensíveis pelo usuário)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from .variants import Constraint


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    url: str                      # URL pública do perfil ({u})
    probe_url: str                # URL realmente consultada (pode ser uma API JSON)
    constraint: Constraint
    check: dict[str, Any]
    bio: dict[str, Any] = field(default_factory=dict)
    positive_control: str | None = None
    known_profiles: tuple[str, ...] = ()   # perfis reais conhecidos (validação do conector)
    errors: tuple[str, ...] = ()
    tier: str = "html"            # api | html | walled  (expectativa; a calibração decide)
    protection: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    verified_on: str | None = None  # data da última validação ao vivo (None = ainda não validado)
    notes: str = ""

    def valid_username(self, u: str) -> bool:
        return self.constraint.valid(u)

    def profile_url(self, u: str) -> str:
        return self.url.replace("{u}", u)

    def probe(self, u: str) -> str:
        return self.probe_url.replace("{u}", u)


def _from_dict(d: dict[str, Any]) -> Platform:
    un = d["username"]
    c = Constraint(
        regex=re.compile(un["regex"]),
        min_len=int(un.get("min", 1)),
        max_len=int(un.get("max", 64)),
        forbid=tuple(re.compile(f) for f in un.get("forbid", [])),
        separators=un.get("separators", "._-"),
        case_insensitive=bool(un.get("ci", True)),
    )
    return Platform(
        id=d["id"], name=d["name"], url=d["url"], probe_url=d.get("probe_url", d["url"]), constraint=c,
        check=d["check"], bio=d.get("bio", {}), positive_control=d.get("positive_control"),
        known_profiles=tuple(d.get("known_profiles", [])),
        errors=tuple(e.lower() for e in d.get("errors", [])), tier=d.get("tier", "html"),
        protection=tuple(d.get("protection", [])), headers=d.get("headers", {}),
        verified_on=d.get("verified_on"), notes=d.get("notes", ""),
    )


def load_platforms(extra: str | Path | None = None, only: list[str] | None = None) -> dict[str, Platform]:
    raw = json.loads(resources.files("sosia").joinpath("data/platforms.json").read_text(encoding="utf-8"))
    entries = list(raw["platforms"])
    if extra:
        p = Path(extra)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p]
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            entries.extend(data["platforms"] if "platforms" in data else [data])
    out = {e["id"]: _from_dict(e) for e in entries}  # extra sobrescreve builtin pelo id
    if only:
        missing = [i for i in only if i not in out]
        if missing:
            raise KeyError(f"plataformas desconhecidas: {', '.join(missing)}")
        out = {i: out[i] for i in only}
    return out
