"""Léxicos (pt-BR primeiro, en/es mínimos) para variantes e para leitura de bio.

Os pesos são *priors heurísticos*, não probabilidades calibradas. O `sosia bench`
existe justamente para medir o efeito deles; ajuste com marcas de desenvolvimento
e valide em marcas separadas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- variantes
AFFIXES: dict[str, list[str]] = {
    "authority": ["oficial", "official", "original", "verificado", "verified", "real", "true", "ofc"],
    "support": ["suporte", "support", "sac", "atendimento", "ajuda", "help", "care", "contato", "central", "falecom"],
    "commerce": ["promo", "promocoes", "ofertas", "outlet", "vendas", "loja", "store", "shop", "cupom",
                 "sorteio", "premios", "descontos", "parceiro"],
    "finance": ["pix", "reembolso", "cashback", "investimentos", "invest", "trade", "cripto", "bonus",
                "financeiro", "pagamentos", "cobranca"],
    "region": ["br", "brasil", "brazil", "sp", "rj", "latam", "pt"],
}

# Massa de probabilidade por família: "qual fração dos handles de impersonação reais cai nesta família?".
# É uma HIPÓTESE do autor (não medida). Cada candidato recebe massa_da_família × peso / soma_dos_pesos_da_família,
# então famílias pequenas (9 omissões) não são soterradas por famílias grandes (80 afixos).
# Re-estime com seus dados reais: `sosia fit-priors`.
FAMILY_MASS: dict[str, float] = {
    "omission": 0.06, "repetition": 0.05, "transposition": 0.06, "replacement": 0.05, "insertion": 0.04,
    "vowel_swap": 0.02, "homoglyph": 0.08, "separator": 0.08, "pad": 0.04, "digits": 0.03,
    "affix_authority": 0.12, "affix_support": 0.12, "affix_finance": 0.06, "affix_commerce": 0.06,
    "affix_region": 0.04, "affix_double": 0.04, "affix_typo": 0.03, "affix_digits": 0.04, "compose": 0.08,
}
COMPOSE_PENALTY = 1.0  # a massa de "compose" já é pequena e dividida entre centenas de candidatos

DIGIT_SUFFIXES = ["1", "2", "01", "07", "10", "24", "123", "x"]

# --------------------------------------------------------------------------- bio
SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "t.ly", "rb.gy", "shorturl.at", "ow.ly", "goo.gl",
    "tiny.cc", "rebrand.ly", "s.id", "encurtador.com.br", "l.instagram.com",
}
AGGREGATORS = {"linktr.ee", "beacons.ai", "bio.link", "allmylinks.com", "campsite.bio", "linkin.bio"}
MESSAGING_DOMAINS = {"wa.me", "api.whatsapp.com", "chat.whatsapp.com", "t.me", "telegram.me", "telegram.dog"}

NEGATORS = re.compile(r"\b(nunca|jamais|nao|never|not|sem|dont|don t|do not|nada de)\b")
NEGATION_WINDOW = 40

# grupos "duros": sozinhos já indicam tentativa de obter dinheiro/credencial/transferir ao golpista
# lookalike_link saiu de HARD: no bench real (hold-out) 0/14 domínios "parecidos" eram impersonação (domínios irmãos,
# podcasts, sites de fãs, produtos homônimos). Continua sinal, mas não sustenta CRÍTICO sozinho.
HARD_GROUPS = {"financial_ask", "credential_ask", "reward_lure", "invest_lure"}
SOFT_GROUPS = {"channel_shift", "urgency", "fear", "link_risk", "social_proof", "lookalike_link"}

LEVERS = ("authority", "urgency", "scarcity", "reward", "fear", "social_proof", "isolation", "commitment")


@dataclass(frozen=True)
class SignalDef:
    id: str
    group: str
    weight: float
    levers: tuple[str, ...]
    pattern: re.Pattern[str]
    negatable: bool = True


def _s(id_: str, group: str, weight: float, levers: tuple[str, ...], pat: str, negatable: bool = True) -> SignalDef:
    return SignalDef(id_, group, weight, levers, re.compile(pat), negatable)


# Aplicados sobre texto normalizado (sem acento, minúsculo).
SIGNALS: list[SignalDef] = [
    _s("claims_official", "identity_claim", 0.20, ("authority",),
       r"\b(oficial|official|verificad[oa]|verified|canal oficial|perfil oficial|conta oficial)\b"),
    _s("claims_support", "identity_claim", 0.20, ("authority",),
       r"\b(suporte|support|sac|atendimento|central de (ajuda|atendimento)|help ?desk|customer care|fale conosco|assistencia)\b"),
    _s("pix_payment", "financial_ask", 0.35, ("commitment",),
       r"\b(pix|boleto|deposito|transferencia|chave pix|pagamento antecipado|reembolso|estorno|saque|"
       r"taxa de (liberacao|cadastro|ativacao|entrega|seguro|desbloqueio))\b"),
    _s("credential_request", "credential_ask", 0.35, ("authority", "fear"),
       r"\b(senha|password|codigo (de )?(verificacao|seguranca|sms)|token|cvv|cpf|dados (bancarios|pessoais|do cartao)|"
       r"confirm(ar|e) (seus )?dados|atualiz(ar|e) (seu )?cadastro|validar (conta|cadastro))\b"),
    _s("channel_shift", "channel_shift", 0.20, ("isolation",),
       r"\b(whats ?app|zap|wpp|wa\.me|api\.whatsapp\.com|telegram|t\.me|chame (no|na|pelo)|chama (no|na|pelo)|"
       r"me chama|fale (no|pelo)|dm|direct|inbox)\b", negatable=False),
    _s("prize_lure", "reward_lure", 0.30, ("reward", "scarcity"),
       r"\b(sorteio|sorteado|ganhador|ganhou|contemplad[oa]|premiad[oa]|voce foi (selecionad|escolhid)\w*|resgate|"
       r"giveaway|brinde gratis|100% gratis)\b"),
    _s("invest_lure", "invest_lure", 0.30, ("reward", "social_proof"),
       r"\b(lucro garantido|renda extra|retorno (garantido|diario)|dobre seu|multiplique|day ?trade|forex|sinais vip|"
       r"alavancagem|rentabilidade|ganhe (ate )?r\$ ?\d+)\b"),
    _s("urgency", "urgency", 0.10, ("urgency", "scarcity"),
       r"\b(urgente|ultimas? (horas|vagas|unidades)|so hoje|somente hoje|acaba hoje|corra|imediato|agora mesmo|ate meia noite)\b",
       negatable=False),
    _s("fear_pressure", "fear", 0.20, ("fear",),
       r"\b(conta (bloqueada|suspensa|hackeada|invadida)|cobranca indevida|multa|negativad[oa]|irregularidade|acesso suspenso)\b"),
    _s("social_proof", "social_proof", 0.05, ("social_proof",),
       r"\b(milhares de (clientes|pessoas)|depoimentos|clientes satisfeitos|aprovad[oa] por)\b", negatable=False),
]

# mitigadores: não somam abuso
DISCLAIMER = re.compile(
    r"\b(fa club|fan ?(page|account|club)|pagina de fas|perfil de fas|parodia|parody|satira|humor|"
    r"nao (e )?(oficial|afiliad\w*)|nao tem (vinculo|afiliacao)|sem vinculo|unofficial|not (affiliated|official)|"
    r"nao representa|critica|opiniao pessoal)\b"
)
SECURITY_NOTICE = re.compile(r"\b(nunca|jamais|nao) (pedimos|solicitamos|enviamos|cobramos|ligamos)\b")

# "aceitamos Pix e cartão" descreve forma de pagamento, não um pedido de transferência.
PAYMENT_ACCEPT = re.compile(r"\b(aceitamos|aceita|aceito|formas? de pagamento|pagamento (via|em|no|por)|parcelamos|parcelamento|cartao e pix|pix e cartao)\b")
LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "@": "a", "$": "s"}
