"""Camada HTTP: passiva, educada e substituível (Fetcher) — o bench usa um mundo simulado."""

from __future__ import annotations

import gzip
import hashlib
import threading
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from . import __version__

MAX_BODY = 3 * 1024 * 1024   # YouTube serve >512KB antes das metatags og:*; só páginas encontradas são grandes
DEFAULT_UA = f"SOSIA/{__version__} (+https://github.com/Ridd1kulusC0d3r/SOSIA; passive brand-protection check)"


@dataclass
class Response:
    url: str
    status: int  # 0 = erro de rede
    final_url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    elapsed: float = 0.0
    error: str | None = None
    _text: str | None = field(default=None, repr=False, compare=False)

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.body.decode("utf-8", errors="replace")
        return self._text

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


class Fetcher(Protocol):
    def get(self, url: str, headers: dict[str, str] | None = None) -> Response: ...


class UrlLibFetcher:
    """GET com rate limit por host, retry em 429/503 respeitando Retry-After e corpo limitado.

    Sem login, sem resolução de CAPTCHA, sem rotação de IP/UA: o objetivo é checar a presença
    pública de um perfil, não contornar proteções (se a plataforma bloqueia, o conector é
    marcado como `blocked` e o resultado fica *inconclusivo*, preservando o motivo).
    """

    def __init__(self, *, user_agent: str = DEFAULT_UA, timeout: float = 12.0, min_interval: float = 1.0,
                 retries: int = 1, max_retry_wait: float = 20.0, host_intervals: dict[str, float] | None = None) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval = min_interval
        self.host_intervals = host_intervals or {}   # intervalo por host (ex.: mastodon.social limita a ~300 req/5 min)
        self.retries = retries
        self.max_retry_wait = max_retry_wait
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()
        self.requests = 0

    def _wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            t = max(now, self._next.get(host, 0.0))
            self._next[host] = t + self.host_intervals.get(host, self.min_interval)
        if t > now:
            time.sleep(t - now)

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        host = urlsplit(url).netloc
        hdrs = {"User-Agent": self.user_agent, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5", **(headers or {})}
        attempt = 0
        while True:
            self._wait(host)
            with self._lock:
                self.requests += 1
            resp = self._once(url, hdrs)
            if resp.status in (429, 503) and attempt < self.retries:
                wait = min(self.max_retry_wait, _retry_after(resp.headers) or 2.0 * (attempt + 1))
                time.sleep(wait)
                attempt += 1
                continue
            return resp

    def _once(self, url: str, hdrs: dict[str, str]) -> Response:
        t0 = time.monotonic()
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (https only por conector)
                return Response(url, r.status, r.geturl(), dict(r.headers), _read(r), time.monotonic() - t0)
        except urllib.error.HTTPError as e:
            try:
                body = _read(e)
            except Exception:  # noqa: BLE001
                body = b""
            return Response(url, e.code, e.geturl() or url, dict(e.headers or {}), body, time.monotonic() - t0)
        except Exception as e:  # noqa: BLE001 — rede/timeout/TLS viram erro classificado
            return Response(url, 0, url, {}, b"", time.monotonic() - t0, error=f"{type(e).__name__}: {e}"[:200])


def _read(r) -> bytes:  # type: ignore[no-untyped-def]
    raw = r.read(MAX_BODY + 1)[:MAX_BODY]
    enc = (r.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            return gzip.decompress(raw)
        if enc == "deflate":
            return zlib.decompress(raw)
    except Exception:  # noqa: BLE001
        pass
    return raw


def _retry_after(headers: dict[str, str]) -> float | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except ValueError:
                return None
    return None
