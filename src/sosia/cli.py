"""Interface de linha de comando. Saída amigável a pipelines (JSONL, códigos de saída)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .calibrate import calibrate, validate
from .config import TEMPLATE, load_config
from .diff import diff_cases
from .model import Brand, Existence, Priority
from .net import DEFAULT_UA, UrlLibFetcher
from .platforms import load_platforms
from .profiles import Profile, find_links
from .report import finding_line, summary_counts, to_jsonl, to_markdown, write_case
from .scanner import ScanConfig, Scanner
from .watch import exit_code as watch_exit_code, watch_step
from .scoring import assess
from .signals import analyze_bio
from .textutil import similarity, slugify
from .variants import VariantEngine, display_variants, pivots

EXIT_OK, EXIT_HIGH, EXIT_CRITICAL, EXIT_USAGE, EXIT_NO_PLATFORM = 0, 10, 20, 2, 3


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _brand_from_args(a: argparse.Namespace) -> tuple[Brand, dict]:
    scan_cfg: dict = {}
    if getattr(a, "config", None):
        brand, scan_cfg = load_config(a.config)
    else:
        if not a.brand:
            raise SystemExit("informe a marca (nome) ou --config sosia.toml")
        brand = Brand(name=a.brand, handle=a.handle or slugify(a.brand))
    if getattr(a, "handle", None):
        brand.handle = a.handle
    brand.domains += [d for d in (a.domain or []) if d not in brand.domains]
    for spec in a.official or []:
        plat, _, handle = spec.rpartition("=")
        brand.official.setdefault(plat or "*", set()).add(handle.lower())
    return brand, scan_cfg


# ------------------------------------------------------------------ comandos
def cmd_init(a: argparse.Namespace) -> int:
    p = Path(a.path)
    if p.exists() and not a.force:
        _err(f"{p} já existe (use --force)")
        return EXIT_USAGE
    p.write_text(TEMPLATE, encoding="utf-8")
    print(f"criado {p}")
    return EXIT_OK


def cmd_variants(a: argparse.Namespace) -> int:
    brand, _ = _brand_from_args(a)
    eng = VariantEngine(brand.handle, extra_affixes=brand.extra_affixes, masses=_load_masses(a.priors))
    constraint = None
    if a.platform:
        constraint = load_platforms(a.platforms_file)[a.platform].constraint
    vs = eng.generate(exclude=set().union(*brand.official.values()) if brand.official else (), constraint=constraint)
    if a.limit:
        vs = vs[: a.limit]
    if a.format == "json":
        print(json.dumps([v.to_dict() for v in vs], ensure_ascii=False, indent=2))
    elif a.format == "jsonl":
        for v in vs:
            print(json.dumps(v.to_dict(), ensure_ascii=False))
    else:
        for v in vs:
            print(f"{v.value}\t{v.similarity:.2f}\t{','.join(sorted(v.families))}")
    _err(f"{len(vs)} variantes de '{eng.base}'" + (f" válidas em {a.platform}" if a.platform else ""))
    return EXIT_OK


def cmd_platforms(a: argparse.Namespace) -> int:
    for p in load_platforms(a.platforms_file).values():
        print(f"{p.id:<10} {p.tier:<7} {p.check.get('type'):<12} validado_ao_vivo={p.verified_on or 'não'}  {p.name}")
    return EXIT_OK


def _fetcher(a: argparse.Namespace) -> UrlLibFetcher:
    return UrlLibFetcher(user_agent=a.user_agent, min_interval=a.rate, timeout=a.timeout)


def cmd_calibrate(a: argparse.Namespace) -> int:
    plats = load_platforms(a.platforms_file, a.platform or None)
    f = _fetcher(a)
    rc = EXIT_OK
    out = []
    for p in plats.values():
        cal = calibrate(p, f, negatives=a.negatives)
        d = cal.to_dict()
        val = validate(p, cal, f) if (a.validate and cal.usable) else None
        if val:
            d["validation"] = val.to_dict()
        out.append(d)
        if a.json:
            continue
        mark = "OK " if cal.usable else "-- "
        print(f"{mark}{p.id:<10} {cal.state.value:<20} conf={cal.confidence:.2f}  {cal.reason}  ({cal.requests} req)")
        if val:
            print(f"     validação: conhecidos {val.known_hit}/{val.known_total} · aleatórios ausentes {val.random_hit}/{val.random_total} "
                  f"→ {'PASSOU' if val.passed else 'FALHOU'}")
            for w in val.wrong:
                print(f"       - {w}")
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    if not any(c["usable"] for c in out):
        rc = EXIT_NO_PLATFORM
    return rc


def cmd_scan(a: argparse.Namespace) -> int:
    brand, scan_cfg = _brand_from_args(a)
    ids = a.platform or scan_cfg.get("platforms")
    plats = load_platforms(a.platforms_file, ids)
    rate = a.rate if a.rate is not None else scan_cfg.get("rate", 1.0)
    f = UrlLibFetcher(user_agent=a.user_agent, min_interval=rate, timeout=a.timeout)
    cfg = ScanConfig(budget=a.budget or scan_cfg.get("budget", 150), concurrency=a.concurrency, seed=a.seed,
                     save_raw=a.save_raw, extra_candidates=a.watch or [], masses=_load_masses(a.priors))
    _err("SÓSIA: use apenas para proteger marca/pessoa que você representa. Verificação passiva de dados públicos; "
         "sem login, sem contornar CAPTCHA/bloqueios.")
    res = Scanner(brand, plats, f, cfg, progress=_err if not a.quiet else None).run()
    if a.out:
        write_case(res, a.out)
        _err(f"pacote de evidências em {a.out}/ (MANIFEST.sha256 incluso)")
    if a.format == "json":
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    elif a.format == "jsonl":
        print(to_jsonl(res), end="")
    elif a.format == "md":
        print(to_markdown(res))
    else:
        t = res.stats["totals"]
        print(f"\nrequisições={t['requests']} encontrados={t['found']} inconclusivos={t['inconclusive']} "
              f"plataformas utilizáveis={t['platforms_usable']}/{len(plats)}"
              + (f" descartadas={t['platforms_discarded']}" if t["platforms_discarded"] else ""))
        print("prioridades:", ", ".join(f"{k}={v}" for k, v in summary_counts(res).items()))
        for fd in res.sorted_findings():
            if fd.existence in (Existence.CONFIRMED, Existence.PROBABLE):
                print(finding_line(fd))
    top = max((fd.assessment.priority.rank for fd in res.findings if fd.assessment), default=-1)
    if res.stats["totals"]["platforms_usable"] == 0:
        return EXIT_NO_PLATFORM
    return EXIT_CRITICAL if top >= Priority.CRITICAL.rank else EXIT_HIGH if top >= Priority.HIGH.rank else EXIT_OK


def cmd_watch(a: argparse.Namespace) -> int:
    """Uma rodada de monitoramento: varre, compara com o estado e emite eventos (feito para cron/Actions)."""
    brand, scan_cfg = _brand_from_args(a)
    plats = load_platforms(a.platforms_file, a.platform or scan_cfg.get("platforms"))
    rate = a.rate if a.rate is not None else scan_cfg.get("rate", 1.0)
    f = UrlLibFetcher(user_agent=a.user_agent, min_interval=rate, timeout=a.timeout)
    cfg = ScanConfig(budget=a.budget or scan_cfg.get("budget", 150), concurrency=a.concurrency, seed=a.seed,
                     extra_candidates=a.watch or [], masses=_load_masses(a.priors))
    res = Scanner(brand, plats, f, cfg, progress=None if a.quiet else _err).run()
    if res.stats["totals"]["platforms_usable"] == 0:
        _err("nenhum conector utilizável: estado NÃO atualizado (evita falso 'perfil removido')")
        return EXIT_NO_PLATFORM
    events, baseline = watch_step(res.to_dict(), a.state)
    if baseline:
        _err(f"baseline criado em {a.state}/ — próximas execuções geram eventos")
    for e in events:
        print(json.dumps(e, ensure_ascii=False) if a.format == "jsonl" else
              f"[{e.get('priority','-'):<7}] {e['event']:<17} {e['platform']}/{e.get('username','')} "
              + (f"({e['from']}→{e['to']})" if e["event"] == "connector_change" else e.get("url", "")))
    return watch_exit_code(events)


def cmd_triage(a: argparse.Namespace) -> int:
    """Lê uma bio (stdin ou --text) e mostra a leitura explicável, sem rede."""
    brand, _ = _brand_from_args(a)
    text = a.text if a.text is not None else sys.stdin.read()
    prof = Profile(display_name=a.display_name, bio=text.strip() or None, links=find_links(text))
    rep = analyze_bio(prof, brand)
    sim = similarity(brand.handle, a.username) if a.username else 0.0
    asm = assess(brand, a.platform or "*", a.username or "", sim, 0.95, prof, rep)
    doc = {"assessment": asm.to_dict(), "signals": rep.to_dict()}
    if a.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print(f"prioridade: {asm.priority.value} · abuso: {asm.abuse_level} · severidade: {asm.severity} · vínculo: {asm.affiliation}")
        for r in asm.reasons:
            print(" -", r)
    return EXIT_OK


def cmd_pivots(a: argparse.Namespace) -> int:
    brand, _ = _brand_from_args(a)
    for d in display_variants(brand.name):
        print(f"[nome]  {d['value']}\t({d['family']})")
    for p in pivots(brand.names, brand.domains, brand.handle):
        print(f"[{p['kind']}] {p['query']}")
    return EXIT_OK


def cmd_diff(a: argparse.Namespace) -> int:
    print(json.dumps(diff_cases(a.old, a.new), ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_stix(a: argparse.Namespace) -> int:
    """Imprime o stix.json que acompanha um case.json (gerado por `scan --out`)."""
    path = Path(a.case).with_name("stix.json")
    if not path.exists():
        _err("stix.json não encontrado ao lado do case.json; reexecute o scan com --out")
        return EXIT_USAGE
    print(path.read_text(encoding="utf-8"))
    return EXIT_OK


def _load_masses(path: str | None) -> dict[str, float] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("masses", data)


def cmd_fit_priors(a: argparse.Namespace) -> int:
    """Estima massas por família a partir de handles de impersonação REAIS já conhecidos (seu histórico de takedowns)."""
    from collections import Counter
    from . import lexicon as L
    eng = VariantEngine(a.handle)
    index = {v.value: v.families for v in eng.generate()}
    aliases = [x.strip().lower() for x in Path(a.aliases).read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]
    counts: Counter = Counter()
    matched, unmatched = 0, []
    for al in aliases:
        fams = index.get(al)
        if not fams:
            unmatched.append(al)
            continue
        matched += 1
        for f in fams:
            counts[f] += 1.0 / len(fams)
    default = L.FAMILY_MASS
    z = sum(default.values())
    alpha = a.alpha
    masses = {f: round((counts.get(f, 0.0) + alpha * m / z) / (matched + alpha), 4) for f, m in default.items()}
    out = {"handle": a.handle, "n_aliases": len(aliases), "n_matched": matched, "coverage_pct": round(100 * matched / max(len(aliases), 1), 1),
           "alpha": alpha, "masses": masses, "unmatched": unmatched}
    Path(a.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _err(f"{matched}/{len(aliases)} aliases explicados pelo motor ({out['coverage_pct']}%); não explicados: {len(unmatched)} → {a.output}")
    for u in unmatched[:15]:
        _err(f"  não gerado: {u}")
    return EXIT_OK


def cmd_eval(a: argparse.Namespace) -> int:
    """Mede a triagem em perfis REAIS rotulados por revisores (JSONL). É aqui que a precisão de campo se prova."""
    from collections import Counter
    from .bench.runner import triage_stats
    default_brand = None
    if a.brand or a.config:
        default_brand, _ = _brand_from_args(a)
    conf: Counter = Counter()
    misses: list[str] = []
    n = 0
    for line in Path(a.file).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        b = Brand(name=r["brand"], handle=r.get("handle") or slugify(r["brand"]), domains=r.get("domains", []),
                  official={"*": {h.lower() for h in r.get("official", [])}}) if r.get("brand") else default_brand
        if b is None:
            raise ValueError("linha sem 'brand' e nenhuma marca padrão (--config/BRAND)")
        bio = r.get("bio") or ""
        prof = Profile(display_name=r.get("display_name"), bio=bio or None, links=find_links(bio))
        rep = analyze_bio(prof, b)
        asm = assess(b, r.get("platform", "*"), r["username"], similarity(b.handle, r["username"]), 0.95, prof, rep)
        conf[(r["label"], asm.priority.value)] += 1
        n += 1
        crit, scam = asm.priority == Priority.CRITICAL, r["label"] == "scam"
        if crit != scam:
            misses.append(f"{'FP' if crit else 'FN'} {r['username']} (rotulo={r['label']}, previsto={asm.priority.value}): {' | '.join(asm.reasons[:3])}")
    out = {"n": n, "critical_vs_scam": triage_stats(conf, {"scam"}, 4),
           "actionable_vs_scam_or_nonscam": triage_stats(conf, {"scam", "nonscam"}, 3),
           "confusion": {f"{k[0]}→{k[1]}": v for k, v in sorted(conf.items())}}
    if a.json:
        out["misses"] = misses
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for key in ("critical_vs_scam", "actionable_vs_scam_or_nonscam"):
            m = out[key]
            print(f"{key}: precisão {m['precision_pct']}% · recall {m['recall_pct']}% · F1 {m['f1_pct']}% (TP {m['tp']} FP {m['fp']} FN {m['fn']}) "
                  f"· acurácia {m['accuracy_pct']}% vs tudo-negativo {m['always_negative_accuracy_pct']}%")
        print("\n".join(misses[: a.show]))
    return EXIT_OK


def cmd_bench(a: argparse.Namespace) -> int:
    from .bench.runner import render_markdown, run_bench
    res = run_bench(seed=a.seed, quick=a.quick, progress=_err)
    md = render_markdown(res)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "bench_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "BENCH_RESULTS.md").write_text(md, encoding="utf-8")
        _err(f"gravado em {out}/")
    print(md)
    return EXIT_OK


# ------------------------------------------------------------------ parser
def _common(p: argparse.ArgumentParser, brand_required: bool = False) -> None:
    p.add_argument("brand", nargs="?", help="nome da marca/pessoa (ou use --config)")
    p.add_argument("-c", "--config", help="arquivo sosia.toml")
    p.add_argument("--handle", help="handle base (padrão: slug do nome)")
    p.add_argument("--domain", action="append", help="domínio oficial (repetível)")
    p.add_argument("--official", action="append", metavar="[PLAT=]HANDLE", help="canal oficial (allowlist), repetível")
    p.add_argument("--platforms-file", help="JSON/dir com conectores extras ou que sobrescrevem os padrões")
    p.add_argument("--priors", help="priors.json gerado por `sosia fit-priors`")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sosia", description="SÓSIA — proteção de marca/pessoa contra perfis falsos (OSINT passivo).")
    ap.add_argument("--version", action="version", version=f"sosia {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="cria sosia.toml de exemplo")
    p.add_argument("path", nargs="?", default="sosia.toml")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("variants", help="gera variantes de username (offline)")
    _common(p)
    p.add_argument("--platform", help="filtra pelas regras de username da plataforma")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--format", choices=["text", "jsonl", "json"], default="text")
    p.set_defaults(fn=cmd_variants)

    p = sub.add_parser("platforms", help="lista conectores")
    p.add_argument("--platforms-file")
    p.set_defaults(fn=cmd_platforms)

    net = argparse.ArgumentParser(add_help=False)
    net.add_argument("--rate", type=float, default=None, help="segundos entre requisições ao mesmo host (padrão 1.0)")
    net.add_argument("--timeout", type=float, default=12.0)
    net.add_argument("--user-agent", default=DEFAULT_UA)

    p = sub.add_parser("calibrate", parents=[net], help="mede a saúde dos conectores (rede)")
    p.add_argument("--platform", action="append")
    p.add_argument("--platforms-file")
    p.add_argument("--negatives", type=int, default=3)
    p.add_argument("--validate", action="store_true", help="além de calibrar, mede acerto com perfis conhecidos + 6 aleatórios novos")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_calibrate, rate=1.0)

    p = sub.add_parser("scan", parents=[net], help="varredura completa (rede)")
    _common(p)
    p.add_argument("--platform", action="append")
    p.add_argument("--budget", type=int, default=0, help="candidatos por plataforma")
    p.add_argument("--watch", action="append", help="username extra sempre consultado (repetível)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--seed", type=int)
    p.add_argument("--out", help="diretório do pacote de evidências")
    p.add_argument("--save-raw", action="store_true", help="guarda o corpo bruto das respostas encontradas")
    p.add_argument("--format", choices=["summary", "json", "jsonl", "md"], default="summary")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("watch", parents=[net], help="uma rodada de monitoramento com estado (cron/Actions)")
    _common(p)
    p.add_argument("--state", required=True, help="diretório de estado (latest.json, history/, alerts.jsonl)")
    p.add_argument("--platform", action="append")
    p.add_argument("--budget", type=int, default=0)
    p.add_argument("--watch", action="append", help="username extra sempre consultado")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--seed", type=int)
    p.add_argument("--format", choices=["text", "jsonl"], default="text")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("triage", help="lê uma bio e explica a triagem (offline)")
    _common(p)
    p.add_argument("--text", help="bio (padrão: stdin)")
    p.add_argument("--display-name")
    p.add_argument("--username")
    p.add_argument("--platform")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_triage)

    p = sub.add_parser("pivots", help="consultas para clones sem handle parecido")
    _common(p)
    p.set_defaults(fn=cmd_pivots)

    p = sub.add_parser("diff", help="compara dois case.json (novos, bio alterada, escalonamentos)")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(fn=cmd_diff)

    p = sub.add_parser("stix", help="imprime o stix.json de um pacote de evidências")
    p.add_argument("case")
    p.set_defaults(fn=cmd_stix)

    p = sub.add_parser("fit-priors", help="estima massas por família a partir de aliases reais conhecidos")
    p.add_argument("handle")
    p.add_argument("aliases", help="arquivo com um username por linha")
    p.add_argument("-o", "--output", default="priors.json")
    p.add_argument("--alpha", type=float, default=10.0, help="pseudo-observações do prior padrão (suavização)")
    p.set_defaults(fn=cmd_fit_priors)

    p = sub.add_parser("eval", help="mede a triagem em perfis reais rotulados (JSONL)")
    _common(p)
    p.add_argument("file", help="JSONL: username, display_name, bio, label[scam|nonscam|fan|benign|reseller], brand?, handle?, domains?, official?")
    p.add_argument("--show", type=int, default=20, help="quantos erros listar")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_eval)

    p = sub.add_parser("bench", help="benchmark sintético reproduzível")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_bench)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (SystemExit, KeyboardInterrupt):
        raise
    except (KeyError, ValueError, FileNotFoundError) as e:
        _err(f"erro: {e}")
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
