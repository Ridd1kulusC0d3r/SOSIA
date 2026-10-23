"""Orquestração: calibrar -> gerar -> sondar com canário -> extrair bio -> triar."""

from __future__ import annotations

import dataclasses
import datetime as _dt
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import __version__
from .calibrate import CalState, Calibration, calibrate, differential_verdict, random_valid_username, validate_differential
from .checks import Kind, Verdict, classify
from .model import Brand, Existence, Finding, ScanResult
from .net import Fetcher, Response
from .platforms import Platform
from .profiles import extract_profile
from .scoring import assess
from .signals import analyze_bio
from .textutil import dl_distance, similarity
from .variants import Variant, VariantEngine


@dataclass
class ScanConfig:
    budget: int = 150                 # candidatos por plataforma
    concurrency: int = 8              # plataformas em paralelo (cada uma é sequencial + rate limit por host)
    negatives: int = 3                # controles negativos por calibração
    canary_every: int = 25            # sonda de controle a cada N consultas
    retries: int = 1                  # só para erro de rede
    guard_ratio: float = 0.5          # razão FOUND que força canário imediato
    guard_min_probes: int = 12
    max_consecutive_blocked: int = 3
    save_raw: bool = False
    seed: int | None = None
    positive_overrides: dict[str, str] = field(default_factory=dict)
    families: set[str] | None = None
    extra_candidates: list[str] = field(default_factory=list)   # watchlist: sempre consultados
    masses: dict[str, float] | None = None   # massas por família (ver `sosia fit-priors`)
    shuffle_seed: int | None = None   # embaralha a ordem de consulta (evita viés de ordem em medições)
    discover: bool = False            # descoberta por busca nativa (Bluesky/Mastodon) antes da varredura
    discover_max: int = 40            # teto de handles descobertos adicionados como candidatos
    record_probed: bool = False       # guarda os usernames consultados em stats (bench/auditoria)


class Scanner:
    def __init__(self, brand: Brand, platforms: dict[str, Platform], fetcher: Fetcher,
                 cfg: ScanConfig | None = None, progress: Callable[[str], None] | None = None) -> None:
        self.brand = brand
        self.platforms = platforms
        self.fetcher = fetcher
        self.cfg = cfg or ScanConfig()
        self.progress = progress or (lambda _m: None)

    # ------------------------------------------------------------------ API
    def run(self) -> ScanResult:
        t0 = time.monotonic()
        started = _dt.datetime.now(_dt.timezone.utc)
        discovery_meta = self._run_discovery() if self.cfg.discover else None
        engine = VariantEngine(self.brand.handle, extra_affixes=self.brand.extra_affixes, masses=self.cfg.masses)
        all_official = set().union(*self.brand.official.values()) if self.brand.official else set()
        variants = engine.generate(exclude=all_official, families=self.cfg.families)

        results: list[tuple[Calibration, list[Finding], dict]] = []
        if self.platforms:
            with ThreadPoolExecutor(max_workers=max(1, min(self.cfg.concurrency, len(self.platforms)))) as ex:
                futs = [ex.submit(self._scan_platform, p, variants) for p in self.platforms.values()]
                results = [f.result() for f in futs]

        cals = [c for c, _, _ in results]
        findings = [f for _, fs, _ in results for f in fs]
        stats = {"platforms": {c.platform: s for c, _, s in results}}
        stats["totals"] = {
            "requests": sum(s["requests"] for _, _, s in results),
            "candidates_generated": len(variants),
            "found": sum(s["found"] for _, _, s in results),
            "not_found": sum(s["not_found"] for _, _, s in results),
            "inconclusive": sum(s["inconclusive"] for _, _, s in results),
            "skipped": sum(s["skipped"] for _, _, s in results),
            "platforms_usable": sum(1 for c in cals if c.usable),
            "platforms_discarded": [f"{c.platform}:{c.state.value}" for c in cals if not c.usable],
        }
        meta = {
            "discovery": discovery_meta,
            "tool": "sosia", "version": __version__, "started_at": started.isoformat(timespec="seconds"),
            "duration_s": round(time.monotonic() - t0, 2), "seed": self.cfg.seed,
            "config": {k: (sorted(v) if isinstance(v, set) else v) for k, v in self.cfg.__dict__.items()},
            "unverified_connectors": sorted(p.id for p in self.platforms.values() if not p.verified_on),
            "caveat": "Verificação passiva de presença pública. Existência não implica impersonação; "
                      "prioridades são triagem explicável, não veredito jurídico.",
        }
        brand = {"name": self.brand.name, "handle": self.brand.handle, "display_names": self.brand.display_names,
                 "domains": self.brand.domains, "official": {k: sorted(v) for k, v in self.brand.official.items()}}
        return ScanResult(meta, brand, cals, findings, stats)

    def candidates_for(self, p: Platform, variants: list[Variant]) -> list[Variant]:
        """Watchlist (extra_candidates) + melhores variantes válidas na plataforma, até o orçamento."""
        official = self.brand.official_handles(p.id)
        extra = []
        for u in dict.fromkeys(x.lower() for x in self.cfg.extra_candidates):
            if u not in official and p.valid_username(u):
                extra.append(Variant(u, {"watchlist"}, dl_distance(self.brand.slug, u), similarity(self.brand.handle, u), 1.0))
        names = {v.value for v in extra}
        rest = [v for v in variants if v.value not in official and v.value not in names and p.valid_username(v.value)]
        out = extra + rest[: max(0, self.cfg.budget - len(extra))]
        if self.cfg.shuffle_seed is not None:
            random.Random(f"{self.cfg.shuffle_seed}:{p.id}").shuffle(out)
        return out

    # ------------------------------------------------------------------ descoberta por busca
    def _run_discovery(self) -> dict:
        """Busca nativa pelo nome da marca. Achado do bench real: a busca lista ~100% dos handles que contêm a marca; a
        enumeração, 2–3%. Os handles viram candidatos (watchlist) e a saturação da busca liga `ambiguous` automaticamente."""
        from .discovery import discover, estimate_ambiguity, handle_class, local_part
        errs: list[str] = []
        try:
            accounts = discover(self.brand.slug, self.fetcher, (), errs)
        except Exception as e:  # noqa: BLE001 — descoberta é opcional; falha não derruba a varredura
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}
        if errs and not accounts:
            return {"ok": False, "error": "busca indisponível (" + ", ".join(sorted(set(errs))) + ")"}
        amb = estimate_ambiguity(self.brand.slug, accounts)
        official = set().union(*self.brand.official.values()) if self.brand.official else set()
        rank = {"contains": 0, "similar": 1}
        found: list[tuple[int, int, str]] = []
        for acc in accounts:
            lp = local_part(acc)
            if not lp or lp in official or lp == self.brand.slug:
                continue
            cls = handle_class(self.brand.slug, lp)
            if cls in rank:
                found.append((rank[cls], len(lp), lp))
        added = list(dict.fromkeys(lp for _, _, lp in sorted(found)))[: self.cfg.discover_max]
        self.cfg.extra_candidates = list(dict.fromkeys([*self.cfg.extra_candidates, *added]))
        auto = amb["saturated"] and not self.brand.ambiguous
        if auto:
            self.brand = dataclasses.replace(self.brand, ambiguous=True)
        return {"ok": True, "accounts_returned": amb["accounts_returned"], "handles_containing_brand": amb["handles_containing_brand"],
                "saturated": amb["saturated"], "ambiguous_auto": auto, "candidates_added": len(added), "advice": amb["advice"],
                "partial_errors": sorted(set(errs))}

    # ------------------------------------------------------------------ internos
    def _probe(self, p: Platform, cal: Calibration, u: str, stat: dict) -> tuple[Verdict, Response]:
        url = p.probe(u)
        for attempt in range(self.cfg.retries + 1):
            resp = self.fetcher.get(url, p.headers or None)
            stat["requests"] += 1
            v = classify(p, resp, u)
            transient = v.kind == Kind.ERROR or resp.status in (502, 503, 504)
            if not transient or attempt == self.cfg.retries:
                break
        if cal.state == CalState.DIFFERENTIAL:
            v = differential_verdict(cal, resp, u, v)
        return v, resp

    def _make_finding(self, p: Platform, cal: Calibration, var: Variant, v: Verdict, resp: Response,
                      validated: bool = True) -> Finding:
        evidence = {
            "request_url": p.probe(var.value), "http_status": resp.status, "final_url": resp.final_url,
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "body_sha256": resp.sha256, "body_bytes": len(resp.body), "elapsed_ms": int(resp.elapsed * 1000),
            "calibration_state": cal.state.value, "check_reason": v.reason, "canary_validated": validated,
        }
        f = Finding(p.id, var.value, p.profile_url(var.value), Existence.INCONCLUSIVE, v.reason,
                    variant=var.to_dict(), evidence=evidence)
        if self.cfg.save_raw:
            f.raw_body = resp.body
        if v.kind == Kind.FOUND:
            f.existence = Existence.CONFIRMED if cal.state in (CalState.TRUSTED, CalState.TRUSTED_NO_POSITIVE) \
                else Existence.PROBABLE
            profile = extract_profile(p, resp)
            rep = analyze_bio(profile, self.brand)
            f.profile = profile.to_dict()
            f.signals = rep.to_dict()
            f.assessment = assess(self.brand, p.id, var.value, var.similarity, cal.confidence, profile, rep)
        elif v.kind == Kind.MISSING:
            f.existence = Existence.NOT_FOUND
        return f

    def _canary(self, p: Platform, cal: Calibration, rng: random.Random, stat: dict, positive: bool) -> bool:
        stat["canaries"] += 1
        u = random_valid_username(p, rng)
        if u is None:
            return True
        v, _ = self._probe(p, cal, u, stat)
        if v.kind != Kind.MISSING:
            return False
        pos = self.cfg.positive_overrides.get(p.id) or p.positive_control
        if positive and pos:
            vp, _ = self._probe(p, cal, pos, stat)
            if vp.kind != Kind.FOUND:
                return False
        return True

    def _scan_platform(self, p: Platform, variants: list[Variant]) -> tuple[Calibration, list[Finding], dict]:
        cfg = self.cfg
        rng = random.Random(f"{cfg.seed}:{p.id}") if cfg.seed is not None else random.Random()
        official = self.brand.official_handles(p.id)
        cands = self.candidates_for(p, variants)
        stat = {"state": "", "reason": "", "requests": 0, "probed": 0, "found": 0, "not_found": 0, "inconclusive": 0,
                "skipped": 0, "canaries": 0, "canary_failures": 0, "recalibrations": 0, "candidates": len(cands),
                "midrun": None}
        if cfg.record_probed:
            stat["probed_users"] = []

        cal = calibrate(p, self.fetcher, negatives=cfg.negatives, rng=rng, positive=cfg.positive_overrides.get(p.id))
        cal, val = validate_differential(p, cal, self.fetcher, rng=rng)
        if val:
            stat["validation"] = val.to_dict()
        stat["requests"] += cal.requests
        stat["state"], stat["reason"] = cal.state.value, cal.reason
        self.progress(f"[{p.id}] calibração: {cal.state.value} ({cal.reason})")
        if not cal.usable:
            stat["skipped"] = len(cands)
            return cal, [], stat

        findings: list[Finding] = []
        pending: list[tuple[Variant, Finding | None]] = []   # desde o último canário válido
        blocked_streak = 0
        since_canary = 0
        canary_count = 0
        i = 0

        def flush() -> None:
            findings.extend(f for _, f in pending if f is not None and f.existence != Existence.NOT_FOUND)
            pending.clear()

        def tally(f: Finding) -> None:
            if f.existence in (Existence.CONFIRMED, Existence.PROBABLE):
                stat["found"] += 1
            elif f.existence == Existence.NOT_FOUND:
                stat["not_found"] += 1
            else:
                stat["inconclusive"] += 1

        def handle_canary_failure() -> bool:
            """True se o conector segue utilizável após recalibrar (e reprocessa o pendente)."""
            nonlocal cal
            stat["canary_failures"] += 1
            stat["recalibrations"] += 1
            self.progress(f"[{p.id}] canário falhou — recalibrando")
            new = calibrate(p, self.fetcher, negatives=cfg.negatives, rng=rng, positive=cfg.positive_overrides.get(p.id))
            new, _ = validate_differential(p, new, self.fetcher, rng=rng)
            stat["requests"] += new.requests
            if new.usable:
                cal = new
                stat["state"], stat["reason"] = new.state.value, "recalibrated:" + new.reason
                redo: list[tuple[Variant, Finding | None]] = []
                for var, f in pending:
                    # reprocessa tudo do período suspeito sob a nova calibração
                    v, resp = self._probe(p, cal, var.value, stat)
                    nf = self._make_finding(p, cal, var, v, resp, validated=False)
                    if f is not None:
                        _untally(f)
                    tally(nf)
                    redo.append((var, nf))
                pending[:] = redo
                return True
            stat["midrun"] = "degraded:" + new.state.value
            stat["state"], stat["reason"] = "degraded", new.state.value + ":" + new.reason
            for var, f in pending:
                if f is not None:
                    _untally(f)
                    bad = Finding(p.id, var.value, p.profile_url(var.value), Existence.INCONCLUSIVE,
                                  "canary_failed_connector_degraded", variant=var.to_dict(),
                                  evidence={"calibration_state": "degraded"})
                    tally(bad)
                    findings.append(bad)
            pending.clear()
            return False

        def _untally(f: Finding) -> None:
            if f.existence in (Existence.CONFIRMED, Existence.PROBABLE):
                stat["found"] -= 1
            elif f.existence == Existence.NOT_FOUND:
                stat["not_found"] -= 1
            else:
                stat["inconclusive"] -= 1

        while i < len(cands):
            var = cands[i]
            i += 1
            v, resp = self._probe(p, cal, var.value, stat)
            stat["probed"] += 1
            if cfg.record_probed:
                stat["probed_users"].append(var.value)
            since_canary += 1
            f = self._make_finding(p, cal, var, v, resp, validated=False)
            tally(f)
            pending.append((var, f))

            blocked_streak = blocked_streak + 1 if v.kind == Kind.BLOCKED else 0
            if blocked_streak >= cfg.max_consecutive_blocked:
                stat["midrun"] = "blocked:" + v.reason
                stat["state"], stat["reason"] = "degraded", "blocked_midrun:" + v.reason
                self.progress(f"[{p.id}] bloqueado ({v.reason}) — interrompendo")
                for _, pf in pending:
                    if pf is not None and pf.existence != Existence.NOT_FOUND:
                        pf.evidence["canary_validated"] = False
                flush()
                stat["skipped"] += len(cands) - i
                return cal, findings, stat

            ratio = stat["found"] / max(stat["probed"], 1)
            guard = stat["probed"] >= cfg.guard_min_probes and ratio > cfg.guard_ratio and since_canary >= 5
            if since_canary >= cfg.canary_every or guard:
                canary_count += 1
                ok = self._canary(p, cal, rng, stat, positive=(canary_count % 2 == 0))
                since_canary = 0
                if ok:
                    for _, pf in pending:
                        if pf is not None:
                            pf.evidence["canary_validated"] = True
                    flush()
                elif not handle_canary_failure():
                    stat["skipped"] += len(cands) - i
                    return cal, findings, stat
                else:
                    flush()

        if pending:  # canário final cobre a cauda
            ok = self._canary(p, cal, rng, stat, positive=True)
            if ok:
                for _, pf in pending:
                    if pf is not None:
                        pf.evidence["canary_validated"] = True
                flush()
            elif handle_canary_failure():
                flush()
        return cal, findings, stat
