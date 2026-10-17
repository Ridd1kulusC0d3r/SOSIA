"""Leitura da bio/nome: sinais explicáveis, com negação e mitigadores.

Bio é *evidência contextual*, não veredito: "suporte", "oficial", "Pix" e "WhatsApp" também
aparecem em operações legítimas. Por isso:

* cada sinal tem grupo; "forte" exige ≥2 grupos independentes (ou grupo duro + alegação de identidade);
* menções negadas ("nunca pedimos senha ou Pix") não somam — viram aviso de segurança;
* disclaimers (fã/paródia/crítica) são registrados e limitam a prioridade;
* link para domínio oficial é apenas *alegação não verificada* (falta link recíproco).
"""

from __future__ import annotations

import re

from . import lexicon as L
from .model import Brand, Signal, SignalReport
from .profiles import Profile, find_links
from .textutil import dl_distance, norm_text, skeleton

_COMPOUND_TLD = {"com", "org", "net", "gov", "edu", "co"}


def registrable(host: str) -> str:
    host = host.lower().strip(".")
    host = re.sub(r"^www\.", "", host)
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _COMPOUND_TLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _host(link: str) -> str:
    return re.sub(r"^https?://", "", link, flags=re.I).split("/")[0].split(":")[0].lower()


def _label(domain: str) -> str:
    return domain.split(".")[0]


def classify_link(link: str, brand: Brand) -> dict:
    host = _host(link)
    reg = registrable(host)
    auth = {registrable(d) for d in brand.domains}
    info = {"link": link, "domain": reg, "class": "external"}
    if reg in auth:
        info["class"] = "authorized_domain"
    elif reg in L.SHORTENERS:
        info["class"] = "shortener"
    elif reg in L.MESSAGING_DOMAINS or host in L.MESSAGING_DOMAINS:
        info["class"] = "messaging"
    elif reg in L.AGGREGATORS:
        info["class"] = "aggregator"
    else:
        lab = skeleton(_label(reg))
        slug = brand.skeleton_slug
        if slug and lab == slug:
            # mesmo rótulo em outro TLD (transfermarkt.de vs .com): em geral é domínio irmão do oficial, não lookalike
            info["class"] = "sibling_tld"
            return info
        sim_auth = max((1 - dl_distance(lab, skeleton(_label(registrable(d)))) / max(len(lab), len(skeleton(_label(registrable(d)))), 1)
                        for d in brand.domains), default=0.0)
        if slug and len(slug) >= 4 and slug in lab or sim_auth >= 0.78:
            info["class"] = "lookalike_domain"
            info["similarity"] = round(max(sim_auth, 0.8 if slug in lab else 0.0), 2)
    return info


def deobfuscate(norm: str) -> str:
    """Troca dígitos/símbolos por letras só dentro de palavras mistas ("p1x" -> "pix")."""
    def fix(m: re.Match[str]) -> str:
        w = m.group(0)
        if re.search(r"[a-z]", w) and re.search(r"[0-9@$]", w):
            return "".join(L.LEET.get(c, c) for c in w)
        return w
    return re.sub(r"[a-z0-9@$]{3,}", fix, norm)


def _negated(norm: str, start: int) -> bool:
    return bool(L.NEGATORS.search(norm[max(0, start - L.NEGATION_WINDOW):start]))


def analyze_bio(profile: Profile | None, brand: Brand, extra_text: str = "") -> SignalReport:
    rep = SignalReport()
    if profile is None:
        return rep
    rep.bio_available = profile.bio_available
    raw_text = profile.text_for_analysis() + "\n" + extra_text
    norm = norm_text(raw_text)
    skel = skeleton(raw_text)

    rep.brand_mention = bool(brand.skeleton_slug) and len(brand.skeleton_slug) >= 3 and brand.skeleton_slug in skel

    seen_ids: set[str] = set()
    deob = deobfuscate(norm)
    passes = [(norm, False)] + ([(deob, True)] if deob != norm else [])
    for text, obfuscated in passes:
        for sd in L.SIGNALS:
            for m in sd.pattern.finditer(text):
                if sd.id == "pix_payment" and L.PAYMENT_ACCEPT.search(text[max(0, m.start() - 40):m.end() + 40]):
                    rep.mitigators.append(Signal("payment_method_mention", "mitigator", 0.0, [], text[max(0, m.start() - 20):m.end() + 20], False))
                    continue
                neg = sd.negatable and _negated(text, m.start())
                snippet = text[max(0, m.start() - 20):m.end() + 20].strip() + (" (ofuscado)" if obfuscated else "")
                sig = Signal(sd.id, sd.group, sd.weight, list(sd.levers), snippet, neg)
                if neg:
                    if sd.group in ("financial_ask", "credential_ask") or sd.id.startswith("claims_"):
                        rep.mitigators.append(Signal("negated_" + sd.id, "mitigator", 0.0, [], snippet, True))
                    continue
                if sd.id not in seen_ids:
                    seen_ids.add(sd.id)
                    rep.signals.append(sig)

    if L.SECURITY_NOTICE.search(norm):
        rep.mitigators.append(Signal("security_notice", "mitigator", 0.0, [], "aviso de segurança", False))
    if L.DISCLAIMER.search(norm):
        rep.disclaimed = True
        m = L.DISCLAIMER.search(norm)
        rep.mitigators.append(Signal("disclaimer", "mitigator", 0.0, [], m.group(0) if m else "", False))

    # links e domínios
    links = list(profile.links) + [x for x in find_links(profile.bio) if x not in profile.links]
    for ln in links:
        info = classify_link(ln, brand)
        rep.domains.append(info)
        cls = info["class"]
        if cls == "authorized_domain":
            rep.links_authorized_domain = True
        elif cls == "lookalike_domain":
            rep.signals.append(Signal("lookalike_domain", "lookalike_link", 0.40, [], ln))
        elif cls == "shortener":
            rep.signals.append(Signal("shortener_link", "link_risk", 0.10, [], ln))
        elif cls == "messaging":
            if "channel_shift" not in seen_ids:
                seen_ids.add("channel_shift")
                rep.signals.append(Signal("channel_shift_link", "channel_shift", 0.20, ["isolation"], ln))

    rep.claims_authority = any(s.group == "identity_claim" for s in rep.signals)
    rep.groups = sorted({s.group for s in rep.signals})
    rep.levers = sorted({lv for s in rep.signals for lv in s.levers})
    rep.abuse_score = min(1.0, sum(s.weight for s in rep.signals))

    risk_groups = set(rep.groups) - {"identity_claim"}
    hard = risk_groups & L.HARD_GROUPS
    soft = risk_groups & L.SOFT_GROUPS
    if (len(risk_groups) >= 2 and hard) or (hard and rep.claims_authority and rep.abuse_score >= 0.5):
        rep.abuse_level = "strong"
    elif hard or len(soft) >= 2:
        rep.abuse_level = "moderate"
    elif soft:
        rep.abuse_level = "weak"
    else:
        rep.abuse_level = "none"
    return rep
