"""Mundo simulado em memória: plataformas fictícias com os modos de falha reais que importam.

Cada comportamento corresponde a um problema documentado nas referências (soft-404, shell de SPA,
login wall, rate limit, CAPTCHA, instabilidade, drift de layout). É um *simulador de regressão* —
não substitui validação ao vivo.
"""

from __future__ import annotations

import html
import json
import random
import threading
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from ..net import Response


class Behavior(str, Enum):
    CLEAN = "clean"              # 200/404 corretos
    API_JSON = "api_json"        # API JSON limpa
    SOFT404 = "soft404"          # 200 para tudo, corpo "não encontrado" diferente do perfil
    SOFT404_MSG = "soft404_msg"  # idem, mas o conector tem marcadores bem escolhidos
    SPA_SHELL = "spa_shell"      # 200 + mesmo shell para tudo (perfil invisível)
    LOGIN_WALL = "login_wall"    # redireciona tudo para /login
    RATELIMIT = "ratelimit"      # 429 após N requisições
    CAPTCHA = "captcha"          # página de desafio após N requisições
    FLAKY = "flaky"              # 503 aleatório
    DRIFT = "drift"              # vira soft-404 após N requisições (mudança de layout)


@dataclass
class SiteSpec:
    id: str
    behavior: Behavior
    after: int = 45              # gatilho para RATELIMIT / CAPTCHA / DRIFT
    flaky_p: float = 0.12


@dataclass
class ProfileSpec:
    display_name: str
    bio: str
    followers: int = 0


NAV = "Início Explorar Entrar Cadastrar-se Termos Privacidade Ajuda Sobre Carreiras Desenvolvedores Imprensa"
FOOT = "© Rede Simulada Todos os direitos reservados Política de cookies Idioma Português"


def _page(u: str, p: ProfileSpec) -> str:
    n, b = html.escape(p.display_name, quote=True), html.escape(p.bio, quote=True)
    return (f"<html><head><title>{n} (@{u}) | Rede</title><meta property=\"og:title\" content=\"{n}\">"
            f"<meta property=\"og:description\" content=\"{b}\"></head><body><nav>{NAV}</nav>"
            f"<div class=\"profile-card\"><h1>{n}</h1><span>@{u}</span><p class=\"bio\">{b}</p>"
            f"<span>{p.followers} seguidores</span></div><footer>{FOOT}</footer></body></html>")


class MockWorld:
    """Implementa o protocolo Fetcher."""

    def __init__(self, sites: dict[str, SiteSpec], profiles: dict[str, dict[str, ProfileSpec]], seed: int = 0) -> None:
        self.sites = sites
        self.profiles = profiles
        self._count: dict[str, int] = {s: 0 for s in sites}
        self._rng = {s: random.Random(f"{seed}:{s}") for s in sites}
        self._lock = threading.Lock()
        self.requests = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        parts = urlsplit(url)
        site = parts.netloc.split(".")[0]
        spec = self.sites[site]
        u = parts.path.rstrip("/").split("/")[-1].lstrip("@").lower()
        with self._lock:
            self.requests += 1
            self._count[site] += 1
            n = self._count[site]
            rnd = self._rng[site].random()
        prof = self.profiles.get(site, {}).get(u)
        b = spec.behavior

        if b == Behavior.DRIFT:
            b = Behavior.SOFT404 if n > spec.after else Behavior.CLEAN
        if b == Behavior.RATELIMIT and n > spec.after:
            return Response(url, 429, url, {"Retry-After": "1"}, b"Too Many Requests")
        if b == Behavior.CAPTCHA and n > spec.after:
            return Response(url, 200, url, {}, b"<html><head><title>Just a moment...</title></head><body>captcha</body></html>")
        if b == Behavior.FLAKY and rnd < spec.flaky_p:
            return Response(url, 503, url, {}, b"Service Unavailable")
        if b in (Behavior.RATELIMIT, Behavior.CAPTCHA, Behavior.FLAKY):
            b = Behavior.CLEAN

        if b == Behavior.API_JSON:
            if prof:
                body = json.dumps({"login": u, "name": prof.display_name, "bio": prof.bio, "followers": prof.followers})
                return Response(url, 200, url, {}, body.encode())
            return Response(url, 404, url, {}, b'{"message":"Not Found"}')
        if b == Behavior.CLEAN:
            if prof:
                return Response(url, 200, url, {}, _page(u, prof).encode())
            return Response(url, 404, url, {}, f"<html><body><nav>{NAV}</nav><h1>Página não encontrada</h1></body></html>".encode())
        if b in (Behavior.SOFT404, Behavior.SOFT404_MSG):
            if prof:
                return Response(url, 200, url, {}, _page(u, prof).encode())
            nonce = "%016x" % random.Random(f"{u}:{n}").getrandbits(64)
            body = (f"<html><head><title>Rede</title></head><body data-nonce=\"{nonce}\"><nav>{NAV}</nav>"
                    f"<h1>Ops! Não encontramos esta página</h1><p>Verifique o endereço e tente novamente</p>"
                    f"<footer>{FOOT}</footer></body></html>")
            return Response(url, 200, url, {}, body.encode())
        if b == Behavior.SPA_SHELL:
            return Response(url, 200, url, {}, b"<html><body><div id=\"root\"></div><script src=\"/app.js\"></script></body></html>")
        if b == Behavior.LOGIN_WALL:
            login = f"https://{site}.sim/login"
            return Response(url, 200, login, {}, b"<html><body><h1>Entre para continuar</h1><form></form></body></html>")
        return Response(url, 0, url, {}, b"", error="UnknownBehavior")
