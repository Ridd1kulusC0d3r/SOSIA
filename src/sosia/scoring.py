"""Triagem multidimensional. CRITICO = prioridade de resposta sustentada por evidência,
nunca "uma palavra encontrada na bio".

Dimensões independentes (ver `model.Assessment`): existência · semelhança · vínculo ·
evidência de abuso · severidade potencial · confiança.
"""

from __future__ import annotations

from .model import Assessment, Brand, Priority, SignalReport
from .profiles import Profile
from .textutil import similarity, skeleton, slugify

CRITICAL_MIN_EXISTENCE_CONF = 0.80   # não promove a CRITICO com existência só "probable" (modo diferencial)
CRITICAL_MIN_SIMILARITY = 0.60


def _severity(rep: SignalReport, sim: float) -> str:
    g = set(rep.groups)
    if "credential_ask" in g or "lookalike_link" in g:
        return "credencial/phishing"
    if g & {"financial_ask", "invest_lure", "reward_lure"}:
        return "financeiro"
    if rep.claims_authority and sim >= 0.8:
        return "reputacao"
    return "baixo"


def _bio_summary(rep: SignalReport) -> str:
    names = {"claims_official": "alegação de oficial", "claims_support": "alegação de suporte", "pix_payment": "pedido de pagamento/Pix",
             "credential_request": "pedido de senha/código/dados", "channel_shift": "desvio para WhatsApp/Telegram",
             "channel_shift_link": "desvio para mensageiro (link)", "prize_lure": "isca de prêmio/sorteio",
             "invest_lure": "isca de investimento", "urgency": "urgência", "fear_pressure": "pressão por medo",
             "social_proof": "prova social", "lookalike_domain": "link para domínio parecido", "shortener_link": "link encurtado"}
    return ", ".join(names.get(s.id, s.id) for s in rep.signals)


def assess(brand: Brand, platform_id: str, username: str, variant_sim: float, existence_conf: float,
           profile: Profile | None, rep: SignalReport) -> Assessment:
    reasons: list[str] = []
    name_sim = max((similarity(profile.display_name, n) for n in brand.names), default=0.0) \
        if profile and profile.display_name else 0.0
    sim = max(variant_sim, name_sim)

    if brand.is_official(platform_id, username):
        return Assessment(Priority.INFO, existence_conf, 1.0, "authorized", "none", "baixo", existence_conf, False,
                          ["handle consta na lista de canais oficiais (allowlist)"])

    affiliation = "disclaimed" if rep.disclaimed else ("claims_link" if rep.links_authorized_domain else "unknown")
    lvl = rep.abuse_level
    bio_ok = rep.bio_available
    severity = _severity(rep, sim)

    reasons.append(f"semelhança visual {sim:.2f} (handle {variant_sim:.2f}" + (f", nome {name_sim:.2f})" if name_sim else ")"))
    if rep.signals:
        reasons.append("bio: " + _bio_summary(rep) + f" → abuso {lvl}")
    elif bio_ok:
        reasons.append("bio lida: sem sinais de abuso")
    else:
        reasons.append("bio indisponível: avaliação baseada só em nome/handle")
    if rep.mitigators:
        reasons.append("mitigadores: " + ", ".join(sorted({m.id for m in rep.mitigators})))
    if rep.links_authorized_domain:
        reasons.append("aponta para domínio oficial (alegação NÃO verificada: exige link recíproco)")
    if rep.levers:
        reasons.append("alavancas psicológicas: " + ", ".join(rep.levers))

    brand_ref = sim >= CRITICAL_MIN_SIMILARITY or rep.brand_mention
    if lvl != "none" and not brand_ref:
        # Achado do bench real (R3): 486/504 "ALTO" eram bios de golpe/sorteio/Pix SEM relação com a marca
        # (hosts de sorteio, criadores com doação via Pix...). Linguagem de golpe sozinha não é impersonação DESTA marca.
        reasons.append("bio com linguagem de golpe/isca, mas sem referência à marca (nome, menção ou handle parecido): "
                       "não é impersonação desta marca")
        return Assessment(Priority.LOW, existence_conf, sim, affiliation, lvl, severity, round(existence_conf * 0.7, 3), False, reasons)
    # CRÍTICO exige IDENTIDADE parecida (handle/nome >= 0.6); mera menção da marca na bio é contexto (bench real, hold-out #1)
    if lvl == "strong" and bio_ok and not rep.disclaimed and sim >= CRITICAL_MIN_SIMILARITY and existence_conf >= CRITICAL_MIN_EXISTENCE_CONF:
        pr = Priority.CRITICAL
        reasons.append("CRÍTICO: ≥2 grupos de evidência independentes + referência à marca + existência confirmada + sem disclaimer")
    elif lvl == "strong":
        pr = Priority.HIGH
        why = []
        if not bio_ok:
            why.append("bio indisponível")
        if rep.disclaimed:
            why.append("há disclaimer de fã/paródia")
        if existence_conf < CRITICAL_MIN_EXISTENCE_CONF:
            why.append("existência apenas provável")
        if sim < CRITICAL_MIN_SIMILARITY:
            why.append("identidade (handle/nome) pouco parecida com a marca")
        reasons.append("ALTO (não CRÍTICO): " + ("; ".join(why) or "evidência forte sem todos os requisitos"))
    elif lvl == "moderate":
        # só pedido de dinheiro/credencial/isca vira ALTO; domínio parecido isolado é MÉDIO (bench real: 0/14 eram impersonação)
        hard_ask = set(rep.groups) & {"financial_ask", "credential_ask", "reward_lure", "invest_lure"}
        # menção à marca na bio é contexto (ex.: "Pix (Nubank)" = banco do usuário), não identidade: exige semelhança de handle/nome
        pr = Priority.HIGH if (hard_ask and sim >= 0.7) else Priority.MEDIUM
    elif lvl == "weak":
        # MÉDIO = algo específico a revisar (desvio de canal/urgência/medo); domínio parecido isolado é só lista
        actionable_soft = set(rep.groups) & {"channel_shift", "urgency", "fear"}
        pr = Priority.MEDIUM if (sim >= 0.8 and actionable_soft) else Priority.LOW
    else:
        # Bench real (hold-out #2): 49% das contas caíam em MÉDIO só por "handle parecido". Semelhança sozinha = LISTA (BAIXO),
        # não fila. Entram na fila: alegação de oficial/atendimento, ou confundível visual (m4rca, marca_zeta) da marca.
        visual_lookalike = skeleton(username) == brand.skeleton_slug and slugify(username) != brand.slug
        if sim >= 0.85 and rep.claims_authority and not rep.disclaimed:
            # 25/26 desses "ALTO" eram entidades legítimas de nome comum ("Official account of ..."); sem abuso => MÉDIO
            pr = Priority.MEDIUM
            reasons.append("handle parecido + alegação de oficial, sem evidência de abuso: comum em contas legítimas; "
                           "confira contra a allowlist de canais oficiais")
        elif visual_lookalike and not rep.disclaimed:
            pr = Priority.MEDIUM
            reasons.append("handle é confundível visual da marca (homóglifo/separador): revisar")
        elif sim >= 0.85 and bio_ok and not rep.brand_mention:
            pr = Priority.LOW
            reasons.append("handle parecido, mas a bio não tem relação com a marca (possível homônimo)")
        elif sim >= 0.6:
            pr = Priority.LOW
        else:
            pr = Priority.INFO

    if rep.disclaimed and lvl != "strong" and pr.rank > Priority.MEDIUM.rank:
        pr = Priority.MEDIUM
    if not bio_ok and pr.rank > Priority.HIGH.rank:
        pr = Priority.HIGH
    if getattr(brand, "ambiguous", False) and pr.rank > Priority.HIGH.rank:
        pr = Priority.HIGH
        reasons.append("marca marcada como ambígua (palavra comum): CRÍTICO exige confirmação humana")

    bio_factor = 1.0 if bio_ok else 0.3
    confidence = existence_conf * (0.7 + 0.3 * bio_factor)
    if lvl == "strong" and len(set(rep.groups) - {"identity_claim"}) >= 3:
        confidence = min(1.0, confidence + 0.03)
    needs_review = pr.rank >= Priority.HIGH.rank and (existence_conf < 0.8 or not bio_ok or rep.disclaimed)
    return Assessment(pr, existence_conf, sim, affiliation, lvl, severity, round(confidence, 3), needs_review, reasons)
