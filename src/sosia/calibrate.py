"""Calibração de conector — o "nome impossível", feito direito.

Antes de confiar em uma plataforma, SÓSIA mede o comportamento dela:

* N nomes aleatórios *sintaticamente válidos* (um nome inválido pode cair em outra rota do servidor);
* 1 controle positivo conhecido (perfil que sabemos que existe);
* comparação de veredito do conector + impressão digital do corpo (shingles) entre negativos e positivo.

Resultado possível (estado do conector), sempre com motivo:

  trusted                 negativos ausentes, positivo encontrado
  trusted_no_positive     negativos ausentes, sem controle positivo utilizável (confiança menor)
  differential            o conector "acha" tudo (soft-404/shell), mas o corpo do positivo difere do
                          dos negativos de forma estável -> usa comparação de impressão digital
  soft404                 responde "existe" para tudo e não há como distinguir -> descartado
  blind                   não enxerga nem o perfil real (SPA/login wall) -> inconclusivo
  blocked / error         rate limit, CAPTCHA, desafio, rede
  unstable                negativos discordam entre si -> inconclusivo
  unvalidated             diferencial reprovado/sem perfis conhecidos para validar -> inconclusivo

Isso não é inédito (Maigret exige verificação com username fictício); o ganho aqui é transformar a
checagem em estado persistido + reuso em tempo de varredura (canário, recalibração, fingerprint).
"""

from __future__ import annotations

import datetime as _dt
import random
import string
from dataclasses import dataclass, field
from enum import Enum

from .checks import Kind, Verdict, classify, jaccard, norm_tokens, shingles
from .net import Fetcher, Response
from .platforms import Platform

DIFF_CONSISTENT = 0.85   # negativos entre si
DIFF_DISTINCT = 0.75     # positivo vs negativos: abaixo disso consideramos "diferente"
DIFF_FOUND_MAX = 0.60    # candidato vs molde negativo: abaixo disso => provável presença


class CalState(str, Enum):
    TRUSTED = "trusted"
    TRUSTED_NO_POSITIVE = "trusted_no_positive"
    DIFFERENTIAL = "differential"
    SOFT404 = "soft404"
    BLIND = "blind"
    BLOCKED = "blocked"
    ERROR = "error"
    UNSTABLE = "unstable"
    UNVALIDATED = "unvalidated"   # modo diferencial que não passou (ou não pôde passar) na validação


USABLE = {CalState.TRUSTED, CalState.TRUSTED_NO_POSITIVE, CalState.DIFFERENTIAL}
CONFIDENCE = {CalState.TRUSTED: 0.95, CalState.TRUSTED_NO_POSITIVE: 0.85, CalState.DIFFERENTIAL: 0.65}


@dataclass
class ProbeRecord:
    username: str
    kind: str
    reason: str
    status: int
    final_url: str
    sha256: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Calibration:
    platform: str
    state: CalState
    reason: str
    negatives: list[ProbeRecord] = field(default_factory=list)
    positive: ProbeRecord | None = None
    requests: int = 0
    at: str = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    neg_shingles: list[set] = field(default_factory=list, repr=False)
    pos_shingles: set | None = field(default=None, repr=False)

    @property
    def usable(self) -> bool:
        return self.state in USABLE

    @property
    def confidence(self) -> float:
        return CONFIDENCE.get(self.state, 0.0)

    def to_dict(self) -> dict:
        return {"platform": self.platform, "state": self.state.value, "usable": self.usable,
                "confidence": self.confidence, "reason": self.reason, "requests": self.requests, "at": self.at,
                "negatives": [n.to_dict() for n in self.negatives],
                "positive": self.positive.to_dict() if self.positive else None}


def random_valid_username(platform: Platform, rng: random.Random, tries: int = 200) -> str | None:
    c = platform.constraint
    length = max(c.min_len, min(12, c.max_len))
    pool = string.ascii_lowercase + string.digits
    for _ in range(tries):
        s = rng.choice(string.ascii_lowercase) + "".join(rng.choice(pool) for _ in range(length - 1))
        if c.valid(s):
            return s
    return None


def _record(u: str, v: Verdict, r: Response) -> ProbeRecord:
    return ProbeRecord(u, v.kind.value, v.reason, r.status, r.final_url, r.sha256[:16])


def _probe(platform: Platform, fetcher: Fetcher, u: str, retries: int = 1) -> tuple[Verdict, Response]:
    for attempt in range(retries + 1):
        r = fetcher.get(platform.probe(u), platform.headers or None)
        v = classify(platform, r, u)
        transient = v.kind == Kind.ERROR or r.status in (502, 503, 504)
        if not transient or attempt == retries:
            return v, r
    raise AssertionError("unreachable")


def differential_verdict(cal: Calibration, resp: Response, username: str, base: Verdict) -> Verdict:
    """Reclassifica por impressão digital quando o conector, sozinho, não discrimina.

    Páginas idênticas ao molde "não encontrado" (negativos) => ausente. Páginas bem distintas desse molde
    (e que não são desafio/bloqueio) => *provável* presença. A faixa intermediária é ambígua (inconclusivo).
    """
    if base.kind in (Kind.BLOCKED, Kind.ERROR) or not cal.neg_shingles:
        return base
    sh = shingles(norm_tokens(resp, username))
    sn = max(jaccard(sh, n) for n in cal.neg_shingles)
    if sn >= DIFF_CONSISTENT:
        return Verdict(Kind.MISSING, "matches_negative_fingerprint")
    if sn < DIFF_FOUND_MAX:
        return Verdict(Kind.FOUND, "differs_from_negative_fingerprint")
    return Verdict(Kind.UNKNOWN, "fingerprint_ambiguous")


def calibrate(platform: Platform, fetcher: Fetcher, *, negatives: int = 3, rng: random.Random | None = None,
              positive: str | None = None) -> Calibration:
    """Calibra; se os negativos discordarem (ruído transitório), repete uma vez antes de desistir."""
    rng = rng or random.Random()
    cal = _calibrate_once(platform, fetcher, negatives, rng, positive)
    if cal.state == CalState.UNSTABLE:
        again = _calibrate_once(platform, fetcher, negatives, rng, positive)
        again.requests += cal.requests
        again.reason = "retry_after_unstable:" + again.reason
        return again
    return cal


def _calibrate_once(platform: Platform, fetcher: Fetcher, negatives: int, rng: random.Random,
                    positive: str | None) -> Calibration:
    cal = Calibration(platform.id, CalState.ERROR, "")
    names: list[str] = []
    while len(names) < negatives:
        n = random_valid_username(platform, rng)
        if n is None:
            cal.reason = "cannot_generate_valid_control"
            return cal
        if n not in names:
            names.append(n)

    neg_resps: list[tuple[str, Verdict, Response]] = []
    for u in names:
        v, r = _probe(platform, fetcher, u)
        neg_resps.append((u, v, r))
        cal.negatives.append(_record(u, v, r))
        cal.requests += 1
        if v.kind == Kind.BLOCKED:  # sem sentido insistir
            break
    kinds = [v.kind for _, v, _ in neg_resps]

    pos_name = positive or platform.positive_control
    pos: tuple[Verdict, Response] | None = None
    if pos_name and Kind.BLOCKED not in kinds:
        pos = _probe(platform, fetcher, pos_name)
        cal.positive = _record(pos_name, pos[0], pos[1])
        cal.requests += 1

    if Kind.BLOCKED in kinds:
        cal.state, cal.reason = CalState.BLOCKED, next(v.reason for _, v, _ in neg_resps if v.kind == Kind.BLOCKED)
        return cal
    if all(k == Kind.ERROR for k in kinds):
        cal.state, cal.reason = CalState.ERROR, neg_resps[0][1].reason
        return cal

    n_found = kinds.count(Kind.FOUND)
    n_missing = kinds.count(Kind.MISSING)

    def try_differential(why: str) -> bool:
        """Estável nos negativos e distinto do positivo -> modo diferencial."""
        if pos is None or pos[0].kind in (Kind.BLOCKED, Kind.ERROR, Kind.MISSING):
            return False
        sets = [shingles(norm_tokens(r, u)) for u, _, r in neg_resps]
        if any(jaccard(a, b) < DIFF_CONSISTENT for i, a in enumerate(sets) for b in sets[i + 1:]):
            return False
        psh = shingles(norm_tokens(pos[1], pos_name or ""))
        if max(jaccard(psh, s) for s in sets) >= DIFF_DISTINCT:
            return False
        cal.neg_shingles, cal.pos_shingles = sets, psh
        cal.state, cal.reason = CalState.DIFFERENTIAL, why
        return True

    if n_found == len(kinds):
        if not try_differential("check_says_exists_for_all_but_bodies_differ"):
            cal.state, cal.reason = CalState.SOFT404, "all_random_names_reported_as_existing"
    elif n_found > 0:
        cal.state, cal.reason = CalState.UNSTABLE, f"{n_found}/{len(kinds)}_random_names_reported_as_existing"
    elif n_missing == len(kinds):
        if pos is None:
            cal.state, cal.reason = CalState.TRUSTED_NO_POSITIVE, "no_positive_control_configured"
        elif pos[0].kind == Kind.FOUND:
            cal.state, cal.reason = CalState.TRUSTED, "negatives_missing_positive_found"
        elif pos[0].kind in (Kind.BLOCKED, Kind.ERROR):
            cal.state, cal.reason = CalState.TRUSTED_NO_POSITIVE, f"positive_control_unreachable:{pos[0].reason}"
        elif not try_differential("positive_not_seen_by_check_but_body_differs"):
            cal.state, cal.reason = CalState.BLIND, "positive_control_reported_missing"
    elif n_missing > 0:
        cal.state, cal.reason = CalState.UNSTABLE, "mixed_negative_verdicts"
    else:  # tudo UNKNOWN/ERROR sem MISSING
        if not try_differential("check_undecided_but_bodies_differ"):
            cal.state, cal.reason = CalState.BLIND, "check_cannot_decide_" + neg_resps[0][1].reason
    return cal


# --------------------------------------------------------------------------- validação empírica
@dataclass
class Validation:
    platform: str
    known_hit: int = 0
    known_total: int = 0
    random_hit: int = 0          # negativos corretamente ausentes
    random_total: int = 0
    inconclusive: int = 0
    wrong: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.known_total > 0 and self.known_hit == self.known_total and self.random_hit == self.random_total

    def to_dict(self) -> dict:
        return {"platform": self.platform, "passed": self.passed, "known": f"{self.known_hit}/{self.known_total}",
                "random_missing": f"{self.random_hit}/{self.random_total}", "inconclusive": self.inconclusive, "wrong": self.wrong}


def decide(platform: Platform, cal: Calibration, fetcher: Fetcher, u: str) -> Verdict:
    v, r = _probe(platform, fetcher, u)
    return differential_verdict(cal, r, u, v) if cal.state == CalState.DIFFERENTIAL else v


def validate(platform: Platform, cal: Calibration, fetcher: Fetcher, *, negatives: int = 6,
             rng: random.Random | None = None) -> Validation:
    """Mede o acerto REAL do conector com perfis conhecidos + nomes aleatórios *novos* (não os da calibração).

    Só um conector que passa aqui deveria receber `verified_on` no platforms.json.
    """
    rng = rng or random.Random()
    out = Validation(platform.id)
    for u in platform.known_profiles:
        v = decide(platform, cal, fetcher, u)
        out.known_total += 1
        if v.kind == Kind.FOUND:
            out.known_hit += 1
        else:
            out.inconclusive += v.kind in (Kind.BLOCKED, Kind.ERROR, Kind.UNKNOWN)
            out.wrong.append(f"conhecido '{u}' → {v.kind.value}:{v.reason}")
    for _ in range(negatives):
        u = random_valid_username(platform, rng)
        if u is None:
            break
        v = decide(platform, cal, fetcher, u)
        out.random_total += 1
        if v.kind == Kind.MISSING:
            out.random_hit += 1
        else:
            out.inconclusive += v.kind in (Kind.BLOCKED, Kind.ERROR, Kind.UNKNOWN)
            out.wrong.append(f"aleatório '{u}' → {v.kind.value}:{v.reason}")
    return out


def validate_differential(platform: Platform, cal: Calibration, fetcher: Fetcher, *, negatives: int = 6,
                          rng: random.Random | None = None) -> tuple[Calibration, Validation | None]:
    """O modo diferencial só vale se passar na validação; senão o conector vira `unvalidated`."""
    if cal.state != CalState.DIFFERENTIAL:
        return cal, None
    if len(platform.known_profiles) < 2:
        cal.state, cal.reason = CalState.UNVALIDATED, "differential_needs_>=2_known_profiles_to_validate"
        return cal, None
    val = validate(platform, cal, fetcher, negatives=negatives, rng=rng)
    cal.requests += val.known_total + val.random_total
    if not val.passed:
        cal.state = CalState.UNVALIDATED
        cal.reason = f"differential_validation_failed:known={val.known_hit}/{val.known_total},random={val.random_hit}/{val.random_total}"
    return cal, val
