"""Extração de dados públicos do perfil (nome de exibição, bio, links) a partir da resposta já obtida."""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import asdict, dataclass, field

from .checks import get_path
from .net import Response
from .platforms import Platform

_URL = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,10}(?:/[^\s<>\"')]*)?", re.I)
_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"""([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|'([^']*)')""")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_FILE_EXT = {"jpg", "jpeg", "png", "gif", "svg", "webp", "css", "js", "json", "html", "php", "pdf", "mp4"}


@dataclass
class Profile:
    display_name: str | None = None
    bio: str | None = None
    links: list[str] = field(default_factory=list)
    followers: int | None = None
    created: str | None = None
    location: str | None = None

    @property
    def bio_available(self) -> bool:
        return bool((self.bio or "").strip())

    def to_dict(self) -> dict:
        return asdict(self)

    def text_for_analysis(self) -> str:
        return "\n".join(x for x in (self.display_name, self.bio, self.location) if x)


def _html_meta(text: str) -> dict[str, str]:
    metas: dict[str, str] = {}
    # NÃO cortar em </head>: o YouTube tem essa string dentro de scripts inline antes das metatags reais
    for tag in _META_TAG.findall(text):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in _ATTR.finditer(tag)}
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            metas.setdefault(key.lower(), _html.unescape(attrs["content"]))
    return metas


def find_links(*texts: str | None) -> list[str]:
    seen: list[str] = []
    for t in texts:
        for m in _URL.findall(t or ""):
            m = m.rstrip(".,;:)")
            host = re.sub(r"^https?://", "", m, flags=re.I).split("/")[0].lower()
            if host.rsplit(".", 1)[-1] in _FILE_EXT or "@" in host:
                continue
            if m not in seen:
                seen.append(m)
    return seen[:20]


def _to_int(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def extract_profile(platform: Platform, resp: Response) -> Profile:
    spec = platform.bio or {}
    p = Profile()
    if spec.get("type") == "json":
        try:
            data = json.loads(resp.text)
        except ValueError:
            return p
        m = spec.get("map", {})

        def val(k: str) -> object:
            return get_path(data, m[k]) if k in m else None

        def clean(v: object, as_html: bool) -> str | None:
            if v is None:
                return None
            s = str(v)
            if as_html:
                s = _html.unescape(_TAG.sub(" ", s))
            return re.sub(r"\s+", " ", s).strip() or None

        html_fields = set(spec.get("html_fields", []))
        p.display_name = clean(val("display_name"), "display_name" in html_fields)
        p.bio = clean(val("bio"), "bio" in html_fields)
        p.location = clean(val("location"), False)
        p.followers = _to_int(val("followers"))
        p.created = clean(val("created"), False)
        link = clean(val("link"), False)
        p.links = find_links(p.bio, link)
        if link and link not in p.links:
            p.links.insert(0, link)
    elif spec.get("type") == "html":
        metas = _html_meta(resp.text)
        title = _TITLE.search(resp.text)
        p.display_name = (metas.get("og:title") or (title.group(1).strip() if title else None) or None)
        p.bio = metas.get("og:description") or metas.get("description")
        if p.display_name:
            p.display_name = re.sub(r"\s+", " ", _html.unescape(p.display_name)).strip()
        p.links = find_links(p.bio)
    # textos genéricos da plataforma ("You can contact @x right away.") não são bio escrita pelo usuário
    for pat in spec.get("placeholders", []):
        if p.bio and re.match(pat, p.bio.strip(), re.I):
            p.bio, p.links = None, []
            break
    return p
