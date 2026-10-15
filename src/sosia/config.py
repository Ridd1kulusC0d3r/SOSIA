"""Configuração TOML (stdlib tomllib)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .model import Brand
from .textutil import slugify

TEMPLATE = '''# sosia.toml — configuração de uma marca/pessoa protegida
[brand]
name = "Marca Zeta"
handle = "marcazeta"                 # base para as variantes
display_names = ["Marca Zeta", "MarcaZeta Brasil"]
domains = ["marcazeta.com.br"]       # domínios oficiais (link recíproco é a única prova de vínculo)
extra_affixes = ["clube", "cartao"]  # termos do seu setor para combosquatting

[official]                           # allowlist: nunca são sinalizados
"*" = ["marcazeta"]
instagram = ["marcazeta", "marcazeta_sac"]
x = ["marcazeta_br"]

[scan]
platforms = ["github", "bluesky", "telegram", "youtube", "linktree", "tiktok"]
budget = 150
rate = 1.0                           # segundos entre requisições ao mesmo host
'''


def load_config(path: str | Path) -> tuple[Brand, dict]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    b = data.get("brand", {})
    if not b.get("name"):
        raise ValueError("[brand].name é obrigatório")
    official = {k: {h.lower() for h in v} for k, v in data.get("official", {}).items()}
    brand = Brand(name=b["name"], handle=b.get("handle") or slugify(b["name"]),
                  display_names=list(b.get("display_names", [])), domains=list(b.get("domains", [])),
                  official=official, extra_affixes=list(b.get("extra_affixes", [])))
    return brand, data.get("scan", {})
