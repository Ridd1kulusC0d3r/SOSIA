"""SÓSIA Bench REAL — dados e oráculos reais, sem corpus simulado.

R1  Teto da enumeração: contas que a BUSCA da plataforma associa à marca (descoberta independente do
    gerador) -> quantas têm handle parecido? o gerador as cobre?
R2  Existência vs ORÁCULO INDEPENDENTE na distribuição real (variantes de marcas reais):
      bluesky : conector getProfile  vs  oráculo resolveHandle   vs  ingênuo = página bsky.app (SPA)
      mastodon: conector accounts/lookup  vs  oráculo webfinger  vs  ingênuo = página /@user
      devto   : conector API  vs  oráculo = página  (ingênuo ≡ oráculo, não avaliável)
      gitlab  : conector API de usuários  vs  oráculo = página (inclui GRUPOS: divergência esperada)
R3  Triagem em bios reais: distribuição + amostra para REVISÃO MANUAL (nunca commitada: texto de terceiros).

Limites declarados no relatório: oráculos podem errar (contas suspensas), busca tem viés de popularidade,
"relacionado à marca" != impersonação, e o revisor da amostra de R3 não é independente do autor das regras.
"""

from __future__ import annotations

import base64
import hashlib
import html as _html
import json
import math
import random
import re
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..model import Brand, Existence
from ..net import Fetcher, Response, UrlLibFetcher
from ..platforms import load_platforms
from ..profiles import Profile, find_links
from ..scanner import ScanConfig, Scanner
from ..scoring import assess
from ..signals import analyze_bio
from ..textutil import similarity, skeleton
from ..variants import VariantEngine
from .runner import BUDGETS, DNSTWIST_FAMILIES


# =============================================================================== infra
class CachingFetcher:
    """Grava respostas em disco: reprodutível, e não repete requisições às APIs públicas."""

    def __init__(self, inner: Fetcher, cache_dir: str | Path, max_body: int = 200_000) -> None:
        self.inner, self.dir, self.max_body = inner, Path(cache_dir), max_body
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = self.misses = 0
        self._lock = threading.Lock()

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        f = self.dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if f.exists():
            d = json.loads(f.read_text())
            with self._lock:
                self.hits += 1
            return Response(url, d["status"], d["final_url"], d["headers"], base64.b64decode(d["body"]), d["elapsed"], d["error"])
        r = self.inner.get(url, headers)
        with self._lock:
            self.misses += 1
        if r.status != 0 and r.status not in (429, 503):                 # não cacheia falha transitória
            f.write_text(json.dumps({"url": url, "status": r.status, "final_url": r.final_url, "headers": {},
                                     "body": base64.b64encode(r.body[: self.max_body]).decode(), "elapsed": r.elapsed,
                                     "error": r.error}))
        return r


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% [{100 * lo:.1f}–{100 * hi:.1f}] (n={n})" if n else "n/a"


_TAG = re.compile(r"<[^>]+>")


from ..discovery import discover, handle_class, local_part  # noqa: E402


# =============================================================================== R1
def run_r1(brands: list[dict], accounts: dict[str, list[dict]]) -> dict[str, Any]:
    strategies = ("sherlock_like", "dnstwist_like", "sosia")
    hit: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    classes: Counter = Counter()
    per_brand: dict[str, dict] = {}
    missed: list[dict] = []
    for b in brands:
        base = b["label"]
        eng = VariantEngine(base)
        full = eng.generate()
        dns = [v for v in eng.generate(families=DNSTWIST_FAMILIES) if v.families <= DNSTWIST_FAMILIES]
        lists = {"sosia": [v.value for v in full], "dnstwist_like": [v.value for v in dns],
                 "sherlock_like": [v.value for v in dns if v.families == {"separator"}]}
        pos = {k: {u: i for i, u in enumerate(v)} for k, v in lists.items()}
        accs = accounts.get(base, [])
        bc: Counter = Counter()
        for a in accs:
            lp = local_part(a)
            if lp is None:
                bc["custom_domain"] += 1
                classes["custom_domain"] += 1
                continue
            c = handle_class(base, lp)
            bc[c] += 1
            classes[c] += 1
            if c in ("contains", "similar"):
                for s in strategies:
                    i = pos[s].get(lp)
                    for B in BUDGETS + [0]:
                        h = hit[(s, B)]
                        h[1] += 1
                        if (B == 0 and i is not None) or (B and i is not None and i < B):
                            h[0] += 1
                if lp not in pos["sosia"]:
                    missed.append({"brand": base, "handle_class": c})
        per_brand[base] = dict(bc)
    return {"n_accounts": sum(classes.values()), "classes": dict(classes),
            "recall": {s: {str(B or "all"): {"hit": hit[(s, B)][0], "n": hit[(s, B)][1], "ci": ci(hit[(s, B)][0], hit[(s, B)][1])}
                           for B in BUDGETS + [0]} for s in strategies},
            "per_brand": per_brand, "n_missed_by_sosia": len(missed)}


# =============================================================================== R2
ORACLES: dict[str, dict[str, Any]] = {
    "bluesky": {"naive": "https://bsky.app/profile/{u}.bsky.social",
                "oracle": "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle={u}.bsky.social"},
    "mastodon": {"naive": "https://mastodon.social/@{u}",
                 "oracle": "https://mastodon.social/.well-known/webfinger?resource=acct:{u}@mastodon.social"},
    "devto": {"naive": None, "oracle": "https://dev.to/{u}"},
    "gitlab": {"naive": None, "oracle": "https://gitlab.com/{u}"},
}
R2_BUDGET = {"bluesky": 40, "mastodon": 8, "devto": 30, "gitlab": 30}
HOST_INTERVAL = {"public.api.bsky.app": 0.3, "bsky.app": 0.4, "mastodon.social": 1.15, "dev.to": 0.5, "gitlab.com": 0.5}


def run_r2_platform(pid: str, brands: list[dict], accounts: dict[str, list[dict]], fetcher: Fetcher, seed: int = 1) -> dict[str, Any]:
    plat = load_platforms(only=[pid])
    spec = ORACLES[pid]
    agg: Counter = Counter()
    states: Counter = Counter()
    disagreements: list[dict] = []
    truth_map: dict[str, bool] = {}
    for b in brands:
        base = b["label"]
        brand = Brand(name=base, handle=base, domains=[b["domain"]], official={"*": {base}})
        watch = []
        for a in accounts.get(base, []):
            lp = local_part(a)
            if lp and handle_class(base, lp) in ("contains", "similar") and lp != base:
                watch.append(lp)
        watch = list(dict.fromkeys(watch))[:10]
        cfg = ScanConfig(budget=R2_BUDGET[pid], seed=seed, extra_candidates=watch, record_probed=True, concurrency=1, shuffle_seed=seed)
        sc = Scanner(brand, plat, fetcher, cfg)
        res = sc.run()
        st = res.stats["platforms"][pid]
        states[st["state"]] += 1
        probed = st.get("probed_users", [])
        found = {f.username for f in res.findings if f.existence in (Existence.CONFIRMED, Existence.PROBABLE)}
        inc = {f.username for f in res.findings if f.existence == Existence.INCONCLUSIVE}
        unprobed = {v.value for v in sc.candidates_for(plat[pid], VariantEngine(base).generate())} - set(probed)
        for u in probed:
            r = fetcher.get(spec["oracle"].replace("{u}", u))
            if r.status not in (200, 400, 404):
                agg["oracle_error"] += 1
                continue
            truth = r.status == 200
            truth_map[u] = truth
            naive = None
            if spec["naive"]:
                rn = fetcher.get(spec["naive"].replace("{u}", u))
                naive = rn.status == 200
            s_found, s_inc = u in found, u in inc
            agg["n"] += 1
            agg["truth"] += truth
            agg["sosia_tp"] += truth and s_found
            agg["sosia_fp"] += (not truth) and s_found
            agg["sosia_fn"] += truth and not s_found and not s_inc
            agg["sosia_inc_truth"] += truth and s_inc
            agg["sosia_inc"] += s_inc
            agg["neg"] += not truth
            if naive is not None:
                agg["naive_n"] += 1
                agg["naive_tp"] += truth and naive
                agg["naive_fp"] += (not truth) and naive
                agg["naive_fn"] += truth and not naive
            if truth != s_found and not s_inc:
                disagreements.append({"brand": base, "kind": "sosia_FN" if truth else "sosia_FP"})
        agg["unprobed"] += len(unprobed)
        agg["requests_sosia"] += st["requests"]
    out = dict(agg)
    out["states"] = dict(states)
    out["disagreements_n"] = len(disagreements)
    out["truth_map"] = truth_map
    return out


def summarize_r2(r: dict[str, Any]) -> dict[str, Any]:
    n, t, neg = r.get("n", 0), r.get("truth", 0), r.get("neg", 0)
    d = {"candidates": n, "oracle_exists": t, "oracle_missing": neg, "states": r.get("states"),
         "sosia": {"tp": r.get("sosia_tp", 0), "fp": r.get("sosia_fp", 0), "fn_silent": r.get("sosia_fn", 0),
                   "inconclusive": r.get("sosia_inc", 0), "inconclusive_of_existing": r.get("sosia_inc_truth", 0),
                   "recall": ci(r.get("sosia_tp", 0), t), "false_positive_rate": ci(r.get("sosia_fp", 0), neg),
                   "precision": ci(r.get("sosia_tp", 0), r.get("sosia_tp", 0) + r.get("sosia_fp", 0))},
         "unprobed_candidates": r.get("unprobed", 0), "oracle_errors": r.get("oracle_error", 0)}
    if r.get("naive_n"):
        d["naive_page_status"] = {"tp": r["naive_tp"], "fp": r["naive_fp"], "fn": r["naive_fn"],
                                  "recall": ci(r["naive_tp"], t), "false_positive_rate": ci(r["naive_fp"], neg),
                                  "precision": ci(r["naive_tp"], r["naive_tp"] + r["naive_fp"])}
    return d


# =============================================================================== R3
def run_r3(brands: list[dict], accounts: dict[str, list[dict]], sample_path: str | Path, seed: int = 3) -> dict[str, Any]:
    rows: list[dict] = []
    dist: Counter = Counter()
    by_kind: dict[str, Counter] = defaultdict(Counter)
    for b in brands:
        base = b["label"]
        brand = Brand(name=base.title(), handle=base, domains=[b["domain"]], official={"*": {base, b["domain"].lower()}})
        for a in accounts.get(base, []):
            lp = local_part(a) or a["handle"].lower()
            bio = a.get("bio") or ""
            prof = Profile(display_name=a.get("display_name"), bio=bio or None, links=find_links(bio))
            rep = analyze_bio(prof, brand)
            asm = assess(brand, a["platform"], lp, similarity(base, lp), 0.95, prof, rep)
            dist[asm.priority.value] += 1
            by_kind[a["query_kind"]][asm.priority.value] += 1
            rows.append({"brand": base, "group": b["group"], "platform": a["platform"], "handle": a["handle"],
                         "display_name": a.get("display_name"), "bio": bio[:300], "query_kind": a["query_kind"],
                         "priority": asm.priority.value, "abuse": asm.abuse_level, "brand_mention": rep.brand_mention,
                         "sim": round(asm.similarity, 2), "signals": [x.id for x in rep.signals],
                         "mitigators": [x.id for x in rep.mitigators], "reasons": asm.reasons[:3]})
    rng = random.Random(seed)
    flagged = [r for r in rows if r["priority"] in ("CRITICO", "ALTO")]
    relevant = [r for r in rows if r["priority"] not in ("CRITICO", "ALTO") and (r["brand_mention"] or r["sim"] >= 0.6) and r["bio"]]
    other = [r for r in rows if r["priority"] not in ("CRITICO", "ALTO") and not (r["brand_mention"] or r["sim"] >= 0.6) and r["bio"]]
    rng.shuffle(relevant)
    rng.shuffle(other)
    sample = [dict(r, stratum="flagged") for r in flagged] + [dict(r, stratum="relevant_unflagged") for r in relevant[:80]] + \
             [dict(r, stratum="irrelevant_unflagged") for r in other[:40]]
    Path(sample_path).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in sample) + "\n", encoding="utf-8")
    return {"n_accounts": len(rows), "with_bio": sum(1 for r in rows if r["bio"]), "priority_distribution": dict(dist),
            "by_query_kind": {k: dict(v) for k, v in by_kind.items()},
            "brand_mention": sum(1 for r in rows if r["brand_mention"]),
            "flagged_n": len(flagged), "sample_sizes": {"flagged": len(flagged), "relevant_unflagged_pool": len(relevant),
                                                        "irrelevant_unflagged_pool": len(other)}}


# =============================================================================== R4
SMS_DS = "dbarbedillo/SMS_Spam_Multilingual_Collection_Dataset"


def load_sms(fetcher: Fetcher) -> list[dict[str, Any]]:
    rows: list[dict] = []
    off = 0
    while True:
        r = fetcher.get(f"https://datasets-server.huggingface.co/rows?dataset={SMS_DS}&config=default&split=train&offset={off}&length=100")
        if r.status != 200:
            raise RuntimeError(f"HF datasets-server {r.status} em offset {off}")
        d = json.loads(r.text)
        rows += [x["row"] for x in d["rows"]]
        off += 100
        if off >= d["num_rows_total"]:
            return rows


def run_r4(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Camada de linguagem vs rótulos de terceiros (UCI SMS Spam, Almeida et al. 2011) em en / pt(MT) / es(MT)."""
    from .runner import SCAM_KEYWORDS
    from ..textutil import norm_text
    dummy = Brand(name="Acme", handle="acme")
    out: dict[str, Any] = {"n": len(rows), "spam": sum(r["labels"] == "spam" for r in rows),
                           "ham": sum(r["labels"] == "ham" for r in rows), "langs": {}}
    for lang, col in (("en", "text"), ("pt", "text_pt"), ("es", "text_es")):
        c: Counter = Counter()
        for r in rows:
            t = r.get(col) or ""
            spam = r["labels"] == "spam"
            rep = analyze_bio(Profile(display_name=None, bio=t, links=find_links(t)), dummy)
            lvl = rep.abuse_level
            kw = any(k in norm_text(t) for k in SCAM_KEYWORDS)
            for name, hit in (("sosia_moderate_plus", lvl in ("moderate", "strong")), ("sosia_strong", lvl == "strong"),
                              ("sosia_any_signal", lvl != "none"), ("keyword_baseline", kw)):
                c[(name, spam, hit)] += 1
        res = {}
        for name in ("sosia_any_signal", "sosia_moderate_plus", "sosia_strong", "keyword_baseline"):
            tp, fn = c[(name, True, True)], c[(name, True, False)]
            fp, tn = c[(name, False, True)], c[(name, False, False)]
            res[name] = {"recall": ci(tp, tp + fn), "false_positive_rate": ci(fp, fp + tn),
                         "precision": ci(tp, tp + fp) if tp + fp else "n/a", "tp": tp, "fp": fp, "fn": fn, "tn": tn}
        out["langs"][lang] = res
    return out


# =============================================================================== orquestração (CLI: sosia bench-real)
def fetch_tranco(cache_dir: Path) -> Path:
    """Baixa a lista Tranco COMPLETA (o Fetcher corta em 3 MB; aqui lemos tudo)."""
    import urllib.request
    dest = cache_dir / "tranco-top-1m.zip"
    if not dest.exists():
        req = urllib.request.Request("https://tranco-list.eu/top-1m.csv.zip", headers={"User-Agent": "SOSIA-bench/1.1"})
        with urllib.request.urlopen(req, timeout=120) as r:                       # noqa: S310
            dest.write_bytes(r.read())
    return dest


def draw_brands(tranco_zip: Path, n_global: int, n_br: int, seed: int, exclude: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Sorteio determinístico (sem escolha manual). Filtro pré-declarado: rótulo [a-z]{5,14}; global: rank 100–6000; br: .com.br até 60k."""
    import zipfile
    rows = [l.split(",") for l in zipfile.ZipFile(tranco_zip).read("top-1m.csv").decode().splitlines()]
    dom = [(int(r), d) for r, d in rows]

    def label(d: str) -> str | None:
        parts = d.split(".")
        return parts[-3] if d.endswith(".com.br") else (parts[-2] if len(parts) >= 2 else None)

    ok = lambda lab: bool(lab and re.fullmatch(r"[a-z]{5,14}", lab))
    glob = [(r, d, label(d)) for r, d in dom[:6000] if not d.endswith(".br") and ok(label(d)) and d.count(".") == 1][100:]
    br = [(r, d, label(d)) for r, d in dom[:60000] if d.endswith(".com.br") and ok(label(d))]
    rng = random.Random(seed)
    seen: set[str] = set()
    pick: list[dict[str, Any]] = []
    for pool, k, tag in ((glob, n_global, "global"), (br, n_br, "br")):
        cand = pool[:]
        rng.shuffle(cand)
        n = 0
        for r, d, lab in cand:
            if lab in seen:
                continue
            seen.add(lab)
            pick.append({"rank": r, "domain": d, "label": lab, "group": tag})
            n += 1
            if n == k:
                break
    return [b for b in pick if b["label"] not in exclude]      # exclusões (ex.: conteúdo adulto) declaradas no relatório


def run_real(cache_dir: str | Path, *, seed: int = 20261017, n_global: int = 16, n_br: int = 16, exclude: tuple[str, ...] = (),
             stages: tuple[str, ...] = ("r1", "r3", "r4"), progress: Any = None) -> dict[str, Any]:
    """Executa o bench real. Respostas ficam em cache_dir (texto de terceiros: NÃO versionar). Retorna só agregados."""
    say = progress or (lambda _m: None)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    brands = draw_brands(fetch_tranco(cache), n_global, n_br, seed, exclude)
    inner = UrlLibFetcher(min_interval=0.3, timeout=15, retries=1, host_intervals=HOST_INTERVAL)
    f = CachingFetcher(inner, cache / "http")
    out: dict[str, Any] = {"seed": seed, "brands": [{"label": b["label"], "rank": b["rank"], "group": b["group"]} for b in brands],
                           "excluded": list(exclude)}
    accounts: dict[str, list[dict]] = {}
    if {"r1", "r2", "r3"} & set(stages):
        say(f"descoberta independente (Bluesky/Mastodon) para {len(brands)} marcas")
        for b in brands:
            accounts[b["label"]] = discover(b["label"], f, ())              # só consulta pura da marca
    if "r1" in stages:
        out["r1"] = run_r1(brands, accounts)
    if "r3" in stages:
        out["r3"] = run_r3(brands, accounts, cache / "r3_review_sample.jsonl")     # amostra com texto: fica LOCAL
    if "r4" in stages:
        say("R4: SMS spam multilíngue (rótulos de terceiros)")
        out["r4"] = run_r4(load_sms(CachingFetcher(UrlLibFetcher(min_interval=0.25, timeout=40), cache / "hf", max_body=2_000_000)))
    if "r2" in stages:
        import threading
        res: dict[str, Any] = {}
        ts = [threading.Thread(target=lambda p=p: res.__setitem__(p, run_r2_platform(p, brands, accounts, f))) for p in ORACLES]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        out["r2"] = {p: summarize_r2(r) for p, r in res.items()}
        if "bluesky" in res:
            out["r2"]["bluesky_page_differential"] = eval_spa_differential(f, res["bluesky"].get("truth_map", {}))
    return out


SPA_PAGE_PLATFORM = {"id": "bluesky_page", "name": "Bluesky (página SPA, conector ingênuo)", "tier": "walled",
                     "url": "https://bsky.app/profile/{u}.bsky.social", "probe_url": "https://bsky.app/profile/{u}.bsky.social",
                     "username": {"regex": "^[a-z0-9-]{3,63}$", "min": 3, "max": 63, "forbid": ["^-", "-$"], "separators": "-"},
                     "check": {"type": "status_code", "found_status": [200], "missing_status": [404]}, "bio": {"type": "html"},
                     "positive_control": "jay", "known_profiles": ["jay", "pfrazee"]}


def eval_spa_differential(fetcher: Fetcher, truth: dict[str, bool], seed: int = 5) -> dict[str, Any]:
    """O conector 'status 200 da página' do Bluesky (SPA) tem FPR 100%. A calibração o recupera em modo diferencial?
    Reusa as páginas já buscadas pelo estágio R2 (cache); mede contra o oráculo resolveHandle."""
    import tempfile
    from ..calibrate import calibrate, decide, validate_differential
    from ..checks import Kind
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "p.json"
        f.write_text(json.dumps({"platforms": [SPA_PAGE_PLATFORM]}))
        p = load_platforms(f, ["bluesky_page"])["bluesky_page"]
    cal = calibrate(p, fetcher, rng=random.Random(seed))
    cal, val = validate_differential(p, cal, fetcher, rng=random.Random(seed + 1))
    c: Counter = Counter()
    for u, t in truth.items():
        v = decide(p, cal, fetcher, u)
        c[(t, "found" if v.kind == Kind.FOUND else "missing" if v.kind == Kind.MISSING else "inconclusive")] += 1
    T, N = sum(v for (t, _), v in c.items() if t), sum(v for (t, _), v in c.items() if not t)
    return {"state": cal.state.value, "validation": val.to_dict() if val else None, "candidates": len(truth), "exist": T, "missing": N,
            "recall": ci(c[(True, "found")], T), "false_positive_rate": ci(c[(False, "found")], N),
            "inconclusive": c[(True, "inconclusive")] + c[(False, "inconclusive")],
            "fn_silent": c[(True, "missing")]}
