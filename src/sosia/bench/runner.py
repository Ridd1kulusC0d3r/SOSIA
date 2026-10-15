"""SÓSIA Bench: três experimentos (geração, existência, triagem) com baselines e ablações.

LEIA ANTES DE CITAR NÚMEROS: tudo aqui é *sintético*. Mede comportamento do motor frente a modos de
falha conhecidos e regressões — não é taxa de detecção no mundo real nem comparação de desempenho com
produtos de terceiros. Baselines "tipo Sherlock/dnstwist/Maigret" são reimplementações mínimas da *lógica
documentada* (não executam essas ferramentas).
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Any, Callable

from ..checks import Kind, classify
from ..model import Existence
from ..profiles import Profile, find_links
from ..scanner import ScanConfig, Scanner
from ..scoring import assess
from ..signals import analyze_bio
from ..textutil import norm_text, similarity
from ..variants import VariantEngine
from .corpus import BrandCase, SITES, build_corpus, build_world, sim_platforms

BUDGETS = [25, 50, 100, 200, 400, 800]
DNSTWIST_FAMILIES = {"omission", "repetition", "transposition", "replacement", "insertion", "vowel_swap", "homoglyph", "separator"}


def _pct(a: float, b: float) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


# =============================================================================== exp 1: geração
def exp_generation(cases: list[BrandCase], seed: int) -> dict[str, Any]:
    strategies = ["sherlock_like", "dnstwist_like", "sosia_random_order", "sosia"]
    hits: dict[tuple[str, int, str], list[int]] = defaultdict(lambda: [0, 0])   # (strategy,budget,group) -> [hit,total]
    sizes: dict[str, list[int]] = defaultdict(list)
    for case in cases:
        eng = VariantEngine(case.handle)
        excl = set(case.officials)
        full = eng.generate(exclude=excl)
        dns = [v for v in eng.generate(exclude=excl, families=DNSTWIST_FAMILIES) if v.families <= DNSTWIST_FAMILIES]
        lists = {
            "sherlock_like": [v.value for v in dns if v.families == {"separator"}],
            "dnstwist_like": [v.value for v in dns],
            "sosia": [v.value for v in full],
        }
        shuffled = [v.value for v in full]
        random.Random(f"{seed}:{case.handle}").shuffle(shuffled)
        lists["sosia_random_order"] = shuffled
        for k in strategies:
            sizes[k].append(len(lists[k]))
        for a in case.aliases:
            groups = ["all_discoverable" if a.cls != "unrelated" else "unrelated", f"cls:{a.cls}", f"split:{case.split}"]
            for k in strategies:
                pos = {u: i for i, u in enumerate(lists[k])}.get(a.handle)
                for b in BUDGETS:
                    for g in groups:
                        c = hits[(k, b, g)]
                        c[1] += 1
                        if pos is not None and pos < b:
                            c[0] += 1
                # recall sem orçamento (lista completa)
                for g in groups:
                    c = hits[(k, 0, g)]
                    c[1] += 1
                    if pos is not None:
                        c[0] += 1
    table = {}
    for (k, b, g), (h, t) in hits.items():
        table.setdefault(g, {}).setdefault(k, {})[b] = {"recall_pct": _pct(h, t), "hit": h, "n": t}
    return {"strategies": strategies, "budgets": BUDGETS, "list_size_mean": {k: round(sum(v) / len(v), 1) for k, v in sizes.items()},
            "recall": table}


# =============================================================================== exp 2: existência
def _naive_status(scanner: Scanner, world, platforms, variants, case) -> dict[str, dict[str, Any]]:
    out = {}
    for sid, p in platforms.items():
        flagged, req = set(), 0
        for v in scanner.candidates_for(p, variants):
            r = world.get(p.probe(v.value))
            req += 1
            if r.status == 200:
                flagged.add(v.value)
        out[sid] = {"flagged": flagged, "inconclusive": set(), "requests": req}
    return out


def _configured_check(scanner: Scanner, world, platforms, variants, case) -> dict[str, dict[str, Any]]:
    out = {}
    for sid, p in platforms.items():
        flagged, req = set(), 0
        for v in scanner.candidates_for(p, variants):
            r = world.get(p.probe(v.value))
            req += 1
            if classify(p, r, v.value).kind == Kind.FOUND:
                flagged.add(v.value)
        out[sid] = {"flagged": flagged, "inconclusive": set(), "requests": req}
    return out


def _sosia(scanner: Scanner, world, platforms, variants, case) -> dict[str, dict[str, Any]]:
    res = scanner.run()
    out = {}
    for sid, p in platforms.items():
        st = res.stats["platforms"][sid]
        cands = {v.value for v in scanner.candidates_for(p, variants)}
        probed = set(st.get("probed_users", []))
        flagged = {f.username for f in res.findings if f.platform == sid and f.existence in (Existence.CONFIRMED, Existence.PROBABLE)}
        inc = {f.username for f in res.findings if f.platform == sid and f.existence == Existence.INCONCLUSIVE}
        inc |= (cands - probed)                              # nunca consultados (conector descartado/bloqueado)
        out[sid] = {"flagged": flagged, "inconclusive": inc - flagged, "requests": st["requests"], "state": st["state"]}
    return out


def exp_existence(cases: list[BrandCase], seed: int, budget: int = 160) -> dict[str, Any]:
    strategies: dict[str, Callable] = {"naive_status": _naive_status, "configured_check": _configured_check, "sosia": _sosia}
    agg: dict[tuple[str, str], Counter] = defaultdict(Counter)
    states: dict[str, Counter] = defaultdict(Counter)
    platforms = sim_platforms()
    for case in cases:
        brand = case.brand()
        variants = VariantEngine(case.handle).generate(exclude=set(case.officials))
        watch = [a.handle for a in case.aliases]
        for name, fn in strategies.items():
            world = build_world(case, seed)
            cfg = ScanConfig(budget=budget, seed=seed, extra_candidates=watch, record_probed=True, concurrency=6, shuffle_seed=seed)
            scanner = Scanner(brand, platforms, world, cfg)
            out = fn(scanner, world, platforms, variants, case)
            truth_by_site = {s.id: {a.handle for a in case.aliases if s.id in a.sites} for s in SITES}
            for sid, r in out.items():
                cands = {v.value for v in scanner.candidates_for(platforms[sid], variants)}
                truth = truth_by_site[sid] & cands
                flagged, inc = r["flagged"], r["inconclusive"]
                c = agg[(sid, name)]
                c["truth"] += len(truth)
                c["tp"] += len(flagged & truth)
                c["fp"] += len(flagged - truth)
                c["inc_truth"] += len(inc & truth)
                c["inc_nontruth"] += len(inc - truth)
                c["fn_silent"] += len(truth - flagged - inc)
                c["requests"] += r["requests"]
                if name == "sosia":
                    states[sid][r.get("state", "")] += 1
    rows: dict[str, Any] = {}
    overall: dict[str, Counter] = defaultdict(Counter)
    for (sid, name), c in agg.items():
        beh = next(s.behavior.value for s in SITES if s.id == sid)
        rows.setdefault(sid, {"behavior": beh})[name] = _metrics(c)
        overall[name].update(c)
    return {"budget_per_platform": budget, "sites": rows, "overall": {n: _metrics(c) for n, c in overall.items()},
            "sosia_connector_states": {k: dict(v) for k, v in states.items()}}


def _metrics(c: Counter) -> dict[str, Any]:
    tp, fp = c["tp"], c["fp"]
    return {"truth": c["truth"], "tp": tp, "fp": fp, "fn_silent": c["fn_silent"], "inconclusive_truth": c["inc_truth"],
            "inconclusive_total": c["inc_truth"] + c["inc_nontruth"],
            "precision_pct": _pct(tp, tp + fp) if tp + fp else None,
            "recall_pct": _pct(tp, c["truth"]), "coverage_pct": _pct(tp + c["inc_truth"], c["truth"]),
            "requests": c["requests"]}


# =============================================================================== exp 3: triagem
SCAM_KEYWORDS = ["pix", "whatsapp", "whats", "zap", "suporte", "oficial", "sorteio", "senha", "investimento", "atendimento",
                 "premio", "telegram", "lucro", "reembolso", "bloqueada"]
AUTH_WORDS = ["oficial", "official", "suporte", "support", "sac", "atendimento"]


def _rank(p: str) -> int:
    return {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAIXO": 1, "INFO": 0}[p]


def _pred_handle_only(case: BrandCase, a, base_sim: float) -> str:
    if any(w in a.handle for w in AUTH_WORDS) and base_sim >= 0.7:
        return "CRITICO"
    return "ALTO" if base_sim >= 0.8 else "MEDIO" if base_sim >= 0.6 else "BAIXO"


def _pred_bio_keyword(case: BrandCase, a, base_sim: float) -> str:
    """O v1.1 como descrito na proposta: qualquer termo "de golpe" na bio => CRITICO."""
    text = norm_text(a.display_name + " " + a.bio)
    if any(k in text for k in SCAM_KEYWORDS):
        return "CRITICO"
    return _pred_handle_only(case, a, base_sim).replace("CRITICO", "ALTO")


def _pred_sosia(case: BrandCase, a, base_sim: float) -> tuple[str, Any]:
    prof = Profile(display_name=a.display_name, bio=a.bio or None, links=find_links(a.bio))
    rep = analyze_bio(prof, case.brand())
    asm = assess(case.brand(), "cleana", a.handle, base_sim, 0.95, prof, rep)
    return asm.priority.value, asm


def triage_stats(conf: Counter, positive_roles: set[str], thr: int) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    fp_roles: Counter = Counter()
    for (role, pr), n in conf.items():
        pred, truth = _rank(pr) >= thr, role in positive_roles
        if pred and truth:
            tp += n
        elif pred:
            fp += n
            fp_roles[role] += n
        elif truth:
            fn += n
        else:
            tn += n
    p, r = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision_pct": round(100 * p, 1), "recall_pct": round(100 * r, 1),
            "f1_pct": round(100 * (2 * p * r / (p + r)) if p + r else 0.0, 1),
            "accuracy_pct": _pct(tp + tn, tp + fp + fn + tn), "fp_by_role": dict(fp_roles),
            "always_negative_accuracy_pct": _pct(fn + tn, tp + fp + fn + tn)}



def exp_triage(cases: list[BrandCase]) -> dict[str, Any]:
    strategies = ["handle_only", "bio_keyword_v1.1", "sosia_multisignal"]
    cm = {s: defaultdict(Counter) for s in strategies}      # split -> role -> priority
    for case in cases:
        for a in case.aliases:
            if a.cls == "unrelated":
                continue
            sim = similarity(case.handle, a.handle)
            preds = {"handle_only": _pred_handle_only(case, a, sim), "bio_keyword_v1.1": _pred_bio_keyword(case, a, sim),
                     "sosia_multisignal": _pred_sosia(case, a, sim)[0]}
            for s, pr in preds.items():
                cm[s][case.split][(a.role, pr)] += 1
                cm[s]["all"][(a.role, pr)] += 1

    out: dict[str, Any] = {"strategies": strategies, "critical_vs_scam": {}, "actionable_vs_scam_or_nonscam": {}, "confusion_sosia": {}}
    for split in ("dev", "test", "all"):
        out["critical_vs_scam"][split] = {s: triage_stats(cm[s][split], {"scam"}, 4) for s in strategies}
        out["actionable_vs_scam_or_nonscam"][split] = {s: triage_stats(cm[s][split], {"scam", "nonscam"}, 3) for s in strategies}
        conf: dict[str, dict[str, int]] = defaultdict(dict)
        for (role, pr), n in cm["sosia_multisignal"][split].items():
            conf[role][pr] = n
        out["confusion_sosia"][split] = {r: dict(v) for r, v in conf.items()}
    return out


# =============================================================================== orquestração + relatório
def run_bench(seed: int = 7, quick: bool = False, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    say = progress or (lambda _m: None)
    cases = build_corpus(seed=seed, n_aliases=40 if quick else 60)
    if quick:
        cases = [c for c in cases if c.split == "dev"][:2] + [c for c in cases if c.split == "test"][:2]
    say(f"corpus: {len(cases)} marcas, {sum(len(c.aliases) for c in cases)} aliases")
    say("exp 1/3 — geração de candidatos")
    gen = exp_generation(cases, seed)
    say("exp 2/3 — confirmação de existência (12 comportamentos de plataforma)")
    ex = exp_existence(cases, seed)
    say("exp 3/3 — triagem de abuso")
    tri = exp_triage(cases)
    return {"seed": seed, "quick": quick, "brands": [{"handle": c.handle, "split": c.split} for c in cases],
            "n_aliases": sum(len(c.aliases) for c in cases),
            "generation": gen, "existence": ex, "triage": tri}


def render_markdown(r: dict[str, Any]) -> str:
    L: list[str] = ["# SÓSIA Bench — resultados (SINTÉTICOS)", "",
                    "> **Isto é um harness de regressão com verdade-terreno simulada.** Os números mostram como o motor se comporta frente a "
                    "modos de falha conhecidos (soft-404, shell de SPA, login wall, rate limit, CAPTCHA, drift) e a um atacante simulado "
                    "independente do gerador. **Não são taxas de detecção do mundo real**, e os baselines são reimplementações mínimas da lógica "
                    "*documentada* de Sherlock/dnstwist/Maigret — essas ferramentas não foram executadas.", "",
                    f"seed `{r['seed']}` · marcas: {len(r['brands'])} (dev {sum(b['split']=='dev' for b in r['brands'])} / "
                    f"test {sum(b['split']=='test' for b in r['brands'])}) · aliases: {r['n_aliases']}", ""]

    g = r["generation"]
    L += ["## 1. Geração de candidatos — recall de aliases por orçamento de consultas", "",
          "Aliases vêm de um atacante simulado independente (mutações aleatórias, afixos dentro e **fora** do léxico, handles sem relação com a marca). "
          "`unrelated` é o teto: enumeração nunca os encontra.", "",
          "| grupo | estratégia | " + " | ".join(f"@{b}" for b in g["budgets"]) + " | lista inteira |", "|---|---|" + "---|" * (len(g["budgets"]) + 1)]
    for grp in ("all_discoverable", "cls:typo", "cls:affix_in", "cls:affix_out", "cls:combo", "split:test", "unrelated"):
        for k in g["strategies"]:
            cells = [f"{g['recall'][grp][k][b]['recall_pct']}%" for b in g["budgets"]] + [f"{g['recall'][grp][k][0]['recall_pct']}%"]
            L.append(f"| {grp} | {k} | " + " | ".join(cells) + " |")
    L += ["", f"Tamanho médio da lista: " + ", ".join(f"`{k}` {v}" for k, v in g["list_size_mean"].items()) + ".",
          "`cls:affix_in` usa afixos que também estão no léxico do motor (parcialmente circular); `cls:affix_out` mede generalização.", ""]

    e = r["existence"]
    L += ["## 2. Confirmação de existência — por comportamento de plataforma", "",
          f"Orçamento {e['budget_per_platform']}/plataforma (inclui watchlist de aliases). `FP` = marcado como existente sem existir; "
          "`FN` = existia e foi dado como ausente **sem aviso**; `INC` = existia e ficou inconclusivo (visível, com motivo).", "",
          "| plataforma (comportamento) | estratégia | TP | **FP** | **FN silencioso** | INC | precisão | recall | requisições |", "|---|---|---|---|---|---|---|---|---|"]
    for sid, row in e["sites"].items():
        for name in ("naive_status", "configured_check", "sosia"):
            m = row[name]
            L.append(f"| {sid} ({row['behavior']}) | {name} | {m['tp']} | {m['fp']} | {m['fn_silent']} | {m['inconclusive_truth']} | "
                     f"{m['precision_pct'] if m['precision_pct'] is not None else '—'}% | {m['recall_pct']}% | {m['requests']} |")
    L += ["", "**Agregado (todas as plataformas e marcas):**", "",
          "| estratégia | TP | FP | FN silencioso | INC (existentes) | precisão | recall estrito | cobertura (recall + INC) | requisições |", "|---|---|---|---|---|---|---|---|---|"]
    for name, m in e["overall"].items():
        L.append(f"| {name} | {m['tp']} | {m['fp']} | {m['fn_silent']} | {m['inconclusive_truth']} | {m['precision_pct']}% | "
                 f"{m['recall_pct']}% | {m['coverage_pct']}% | {m['requests']} |")
    L += ["", "Estado final dos conectores no SÓSIA (contagem de execuções): " +
          "; ".join(f"`{sid}`: " + ", ".join(f"{k}×{v}" for k, v in d.items()) for sid, d in e["sosia_connector_states"].items()), ""]

    t = r["triage"]
    L += ["## 3. Triagem de abuso", "",
          "Aliases existentes (exceto `unrelated`, que a enumeração não acha). Verdade: `scam` = golpe; `nonscam` = impersonação sem golpe; "
          "`fan`, `benign`, `reseller` (revenda legítima que \"aceita Pix\") = não acionáveis. 12% das bios vazias. "
          "Templates de bio de **teste** diferem dos de **dev**, e o teste inclui 4 golpes *fora do léxico*.", "",
          "> ⚠️ **Contaminação declarada:** as regras de léxico/negação/\"aceitamos Pix\" foram escritas pelo mesmo autor do corpus sintético, "
          "com visibilidade dos templates (inclusive os de teste). Os números do SÓSIA aqui são **otimistas**: demonstram o *mecanismo* "
          "(negação, allowlist, evidência em grupos, disclaimers) contra um gatilho por palavra-chave, não a precisão esperada em campo. "
          "Para medir de verdade: `sosia eval` com perfis reais rotulados por revisores independentes.", ""]
    for key, title in (("critical_vs_scam", "CRÍTICO vs golpe"), ("actionable_vs_scam_or_nonscam", "≥ALTO vs (golpe ∪ impersonação)")):
        L += [f"### {title}", "", "| split | estratégia | TP | FP | FN | precisão | recall | F1 | acurácia | acurácia de \"tudo negativo\" | FPs por papel |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for split in ("dev", "test", "all"):
            for s in t["strategies"]:
                m = t[key][split][s]
                L.append(f"| {split} | {s} | {m['tp']} | {m['fp']} | {m['fn']} | {m['precision_pct']}% | {m['recall_pct']}% | {m['f1_pct']}% | "
                         f"{m['accuracy_pct']}% | {m['always_negative_accuracy_pct']}% | {m['fp_by_role'] or '—'} |")
        L.append("")
    L += ["### Matriz de confusão do SÓSIA (papel verdadeiro × prioridade) — split test", "",
          "| papel | CRITICO | ALTO | MEDIO | BAIXO | INFO |", "|---|---|---|---|---|---|"]
    for role, row in sorted(t["confusion_sosia"]["test"].items()):
        L.append(f"| {role} | " + " | ".join(str(row.get(p, 0)) for p in ("CRITICO", "ALTO", "MEDIO", "BAIXO", "INFO")) + " |")
    L += ["", "> Acurácia isolada engana: com maioria de perfis não acionáveis, um classificador que nunca alerta já tem a acurácia da coluna "
          "\"tudo negativo\" e detecta zero golpes. Use precisão/recall por classe.", ""]
    return "\n".join(L)
