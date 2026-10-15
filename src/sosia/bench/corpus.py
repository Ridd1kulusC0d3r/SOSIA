"""Corpus sintético com verdade-terreno, gerado por um *simulador de atacante independente* do motor.

Para evitar resultado artificialmente bom:
* o atacante simulado usa mutações aleatórias próprias (inclusive não-visuais) e afixos *fora* do léxico do motor;
* uma classe de aliases usa handle sem relação com a marca (teto de recall da enumeração);
* marcas são separadas em desenvolvimento (dev) e teste (test) — e os TEMPLATES de bio também;
  nenhuma calibração de pesos foi feita com marcas/templates de teste;
* armadilhas: revenda legítima ("aceitamos Pix"), perfil oficial com aviso de segurança, fã/paródia,
  homônimos, bio vazia, texto ofuscado ("p1x").
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..model import Brand
from ..platforms import Platform
from ..variants import Constraint
from .world import Behavior, MockWorld, ProfileSpec, SiteSpec

import re

BRANDS_DEV = [("Zeta Marca", "zetamarca", "zetamarca.com.br"), ("Norte Val", "norteval", "norteval.com.br"),
              ("Banco Lume", "bancolume", "bancolume.com.br"), ("Vitrala", "vitrala", "vitrala.com")]
BRANDS_TEST = [("Café Guará", "cafeguara", "cafeguara.com.br"), ("Tikaro", "tikaro", "tikaro.app"),
               ("Nexoral", "nexoral", "nexoral.com.br"), ("Fibralis", "fibralis", "fibralis.com.br"),
               ("Lume Pay", "lumepay", "lumepay.com.br"), ("Aurelta", "aurelta", "aurelta.com")]

# afixos que o atacante simulado usa
IN_LEXICON = ["oficial", "official", "suporte", "support", "sac", "atendimento", "ajuda", "promo", "pix", "br",
              "brasil", "loja", "vendas", "real", "original", "ofertas"]
HELD_OUT = ["atendimento24h", "centralbr", "contatooficial", "vendasbr", "oficial2", "sacbr", "suportebr", "liquida",
            "faturas", "segundavia", "ajudaonline", "canalvip", "clientes", "premium", "cobrancas", "falaconosco"]
UNRELATED_WORDS = ["central", "cliente", "premio", "ganhadores", "resgate", "beneficio", "app", "portal", "grupo", "club"]
HAND_HOMOGLYPH = {"o": "0", "l": "1", "i": "1", "a": "4", "e": "3", "s": "5", "m": "rn", "w": "vv"}
ALPHA = "abcdefghijklmnopqrstuvwxyz"

# --------------------------------------------------------------------------- bios
TPL = {
    "scam": {
        "dev": [
            "Suporte oficial {B} ✅ Atendimento 24h. Chame no WhatsApp (11) 9{n}. Reembolso via Pix hoje!",
            "🎁 SORTEIO {B}! Você foi selecionado, resgate seu prêmio agora: bit.ly/{r}",
            "{B} Investimentos | lucro garantido | sinais VIP | chame no Telegram t.me/{r}",
            "Atendimento {B}. Confirme seus dados e envie o código de verificação para liberar sua conta bloqueada.",
            "Canal oficial {B}. Promoções relâmpago só hoje! {b}-promo.com",
            "Atendimento ao cliente {B}. Fale com a gente no direct.",
        ],
        "test": [
            "{B} • central de ajuda 🇧🇷 | taxa de liberação via PIX | me chama no zap {n}",
            "PARABÉNS! voce ganhou o premio da {B}. clique no link da bio e informe seu CPF e senha",
            "{B} trader oficial 📈 renda extra todo dia, retorno garantido, grupo VIP no t.me/{r}",
            "Suporte {B} | sua conta foi suspensa, regularize agora e evite multa: {b}-regulariza.com",
            "Atendimento {B} 24h – p1x ou boleto, falamos pelo whats",
            "Ajuda {B}. Nos chame na DM.",
            # difíceis: fora do léxico do motor (medem o teto honesto de recall)
            "Seu saldo {B} está liberado! Deposite R$ 50 e receba R$ 500 em minutos",
            "{B} oficial. mande um oi no número {n} e finalize sua compra com 90% off",
            "Sac {B}: p i x e whats",
            "Official {B} support — DM us to claim your reward",
        ],
    },
    "nonscam": {
        "dev": ["Perfil oficial {B} ✅ Novidades e lançamentos.", "Bem-vindo ao canal oficial da {B}."],
        "test": ["{B} Brasil 🇧🇷 | marca original", "Tudo sobre a {B} — conteúdo oficial"],
    },
    "fan": {
        "dev": ["Perfil de fãs da {B}. Não oficial. Humor e memes.", "Parody account. Not affiliated with {B}.",
                "Review e opinião pessoal sobre {B}. Sem vínculo."],
        "test": ["Fã número 1 da {B} ❤️ (conta não afiliada)", "Memes e sátira sobre a {B}",
                 "Fã da {B}, chama no whats pra parcerias"],
    },
    "benign": {
        "dev": ["Pet shop da Marcia. Banho e tosa. Chame no WhatsApp.", "Dev backend, café e código.", "Música e viagens."],
        "test": ["Studio de tatuagem • orçamento no direct", "Professora de inglês | aulas online",
                 "Fotografia de casamentos, contato por whatsapp"],
    },
    "reseller": {
        "dev": ["Revenda autorizada {B}. Atendimento via WhatsApp. Aceitamos Pix e cartão."],
        "test": ["Loja parceira {B} – vendas e suporte local. Formas de pagamento: cartão e pix. Zap {n}"],
    },
}
OFFICIAL_BIO = "Atendimento oficial {B}. Nunca pedimos senha ou Pix por aqui. {d}"
ROLE_WEIGHTS = [("scam", 0.40), ("nonscam", 0.12), ("fan", 0.18), ("benign", 0.18), ("reseller", 0.12)]
CLS_WEIGHTS = [("typo", 0.25), ("affix_in", 0.25), ("affix_out", 0.25), ("combo", 0.10), ("unrelated", 0.15)]


@dataclass
class Alias:
    handle: str
    cls: str
    role: str
    display_name: str
    bio: str
    sites: set[str] = field(default_factory=set)


@dataclass
class BrandCase:
    display: str
    handle: str
    domain: str
    split: str
    aliases: list[Alias]
    officials: list[str]

    def brand(self) -> Brand:
        return Brand(name=self.display, handle=self.handle, domains=[self.domain], official={"*": set(self.officials)})


def _mutate(base: str, rng: random.Random) -> str:
    s = base
    for _ in range(rng.choice([1, 1, 2])):
        op = rng.choice(["del", "swap", "dup", "sub", "homo", "sep"])
        i = rng.randrange(len(s))
        if op == "del" and len(s) > 4:
            s = s[:i] + s[i + 1:]
        elif op == "swap" and i < len(s) - 1:
            s = s[:i] + s[i + 1] + s[i] + s[i + 2:]
        elif op == "dup":
            s = s[:i] + s[i] + s[i:]
        elif op == "sub":
            s = s[:i] + rng.choice(ALPHA) + s[i + 1:]
        elif op == "homo":
            cands = [j for j, c in enumerate(s) if c in HAND_HOMOGLYPH]
            if cands:
                j = rng.choice(cands)
                s = s[:j] + HAND_HOMOGLYPH[s[j]] + s[j + 1:]
        elif op == "sep" and 1 <= i < len(s):
            s = s[:i] + rng.choice("._-") + s[i:]
    return s


def _affixed(core: str, word: str, rng: random.Random) -> str:
    j = rng.choice(["", "_", ".", "-"])
    out = core + j + word if rng.random() < 0.6 else word + j + core
    if rng.random() < 0.25:
        out += rng.choice(["1", "2", "01", "24", "123"])
    return out


def _make_handle(base: str, cls: str, rng: random.Random) -> str:
    if cls == "typo":
        return _mutate(base, rng)
    if cls == "affix_in":
        return _affixed(base, rng.choice(IN_LEXICON), rng)
    if cls == "affix_out":
        return _affixed(base, rng.choice(HELD_OUT), rng)
    if cls == "combo":
        return _affixed(_mutate(base, rng), rng.choice(IN_LEXICON), rng)
    return f"{rng.choice(UNRELATED_WORDS)}{rng.choice(['_', '.', ''])}{rng.choice(UNRELATED_WORDS)}{rng.randrange(10, 9999)}"


def _pick(weights: list[tuple[str, float]], rng: random.Random) -> str:
    r, acc = rng.random(), 0.0
    for k, w in weights:
        acc += w
        if r <= acc:
            return k
    return weights[-1][0]


def build_corpus(seed: int = 7, n_aliases: int = 60, n_sites: int = 12) -> list[BrandCase]:
    cases: list[BrandCase] = []
    for split, brands in (("dev", BRANDS_DEV), ("test", BRANDS_TEST)):
        for display, handle, domain in brands:
            rng = random.Random(f"{seed}:{handle}")
            seen = {handle}
            aliases: list[Alias] = []
            tries = 0
            while len(aliases) < n_aliases and tries < n_aliases * 50:
                tries += 1
                cls = _pick(CLS_WEIGHTS, rng)
                h = _make_handle(handle, cls, rng)
                if h in seen or not re.match(r"^[a-z0-9._-]{4,30}$", h) or h[0] in "._-" or h[-1] in "._-" or ".." in h:
                    continue
                seen.add(h)
                role = _pick(ROLE_WEIGHTS, rng)
                tpl = rng.choice(TPL[role][split])
                bio = tpl.format(B=display, b=handle, d=domain, n=rng.randrange(10000000, 99999999), r="".join(rng.choice(ALPHA) for _ in range(6)))
                if rng.random() < 0.12:
                    bio = ""
                dn = {"scam": f"{display} Oficial", "nonscam": display, "fan": f"{display} Fãs",
                      "reseller": f"{display} Revenda", "benign": rng.choice(["Studio Aurora", "Marcia Pet", "Dev Café", "Foto & Arte"])}[role]
                aliases.append(Alias(h, cls, role, dn, bio))
            cases.append(BrandCase(display, handle, domain, split, aliases, [handle, f"{handle}_sac"]))
    return cases


# --------------------------------------------------------------------------- mundo + plataformas
SITES: list[SiteSpec] = [
    SiteSpec("cleana", Behavior.CLEAN), SiteSpec("cleanb", Behavior.CLEAN), SiteSpec("apijson", Behavior.API_JSON),
    SiteSpec("softpos", Behavior.SOFT404), SiteSpec("softnopos", Behavior.SOFT404),
    SiteSpec("softmsg", Behavior.SOFT404_MSG), SiteSpec("spashell", Behavior.SPA_SHELL),
    SiteSpec("loginwall", Behavior.LOGIN_WALL), SiteSpec("ratelimit", Behavior.RATELIMIT, after=45),
    SiteSpec("captcha", Behavior.CAPTCHA, after=40), SiteSpec("flaky", Behavior.FLAKY, flaky_p=0.12),
    SiteSpec("drift", Behavior.DRIFT, after=70),
]
POSITIVE = "refperfil1"
POSITIVE2 = "refperfil2"
_CONSTRAINT = Constraint(re.compile(r"^[a-z0-9._-]{1,30}$"), 1, 30, (re.compile(r"\.\."),), "._-", True)


def sim_platforms() -> dict[str, Platform]:
    out: dict[str, Platform] = {}
    for s in SITES:
        has_pos = s.id != "softnopos"
        if s.behavior == Behavior.API_JSON:
            url, probe = f"https://{s.id}.sim/{{u}}", f"https://{s.id}.sim/api/users/{{u}}"
            check = {"type": "json", "found_status": [200], "missing_status": [404], "json_has": "login"}
            bio = {"type": "json", "map": {"display_name": "name", "bio": "bio", "followers": "followers"}}
        else:
            url = probe = f"https://{s.id}.sim/{{u}}"
            bio = {"type": "html"}
            if s.behavior == Behavior.SOFT404_MSG:
                check = {"type": "message", "present_strs": ["profile-card"], "absent_strs": ["não encontramos"], "found_status": [200]}
            else:  # configuração ingênua típica: status 200 = existe
                check = {"type": "status_code", "found_status": [200], "missing_status": [404]}
        out[s.id] = Platform(id=s.id, name=s.id, url=url, probe_url=probe, constraint=_CONSTRAINT, check=check, bio=bio,
                             positive_control=POSITIVE if has_pos else None,
                             known_profiles=(POSITIVE, POSITIVE2) if has_pos else (), tier="html")
    return out


def build_world(case: BrandCase, seed: int = 0, presence: float = 0.45) -> MockWorld:
    rng = random.Random(f"world:{seed}:{case.handle}")
    profiles: dict[str, dict[str, ProfileSpec]] = {s.id: {} for s in SITES}
    for a in case.aliases:
        sites = {s.id for s in SITES if rng.random() < presence} or {rng.choice(SITES).id}
        a.sites = sites
        for sid in sites:
            profiles[sid][a.handle] = ProfileSpec(a.display_name, a.bio, rng.randrange(0, 5000))
    for sid in profiles:
        for off in case.officials:
            profiles[sid][off] = ProfileSpec(case.display, OFFICIAL_BIO.format(B=case.display, d=case.domain), 90000)
        profiles[sid][POSITIVE] = ProfileSpec("Perfil de Referência", "Perfil de teste para calibração de conectores.", 10)
        profiles[sid][POSITIVE2] = ProfileSpec("Segundo Perfil de Referência", "Outro perfil de teste: conteúdo e tamanho diferentes para validar conectores.", 20)
    return MockWorld({s.id: SiteSpec(s.id, s.behavior, s.after, s.flaky_p) for s in SITES}, profiles, seed=seed)
