"""Saídas: Markdown, CSV, JSONL, STIX 2.1 e pacote de evidências com manifesto de hashes."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from pathlib import Path

from .model import Existence, Finding, Priority, ScanResult
from .variants import display_variants, pivots

_STIX_NS = uuid.UUID("5a0f1d34-6a7e-4b6b-9a58-50510a000001")


# --------------------------------------------------------------------------- texto
def summary_counts(res: ScanResult) -> dict[str, int]:
    counts = {p.value: 0 for p in Priority}
    for f in res.findings:
        if f.assessment:
            counts[f.assessment.priority.value] += 1
    return counts


def to_markdown(res: ScanResult) -> str:
    m, b = res.meta, res.brand
    out: list[str] = [f"# SÓSIA — relatório: {b['name']}", ""]
    out += [f"- Versão: `{m['version']}` · início: `{m['started_at']}` · duração: {m['duration_s']}s · seed: `{m['seed']}`",
            f"- Handle base: `{b['handle']}` · domínios oficiais: {', '.join(b['domains']) or '—'}",
            f"- Canais oficiais (allowlist): {json.dumps(b['official'], ensure_ascii=False) or '—'}", ""]
    t = res.stats["totals"]
    out += ["## Resumo", "",
            f"Requisições: **{t['requests']}** · candidatos gerados: {t['candidates_generated']} · "
            f"encontrados: **{t['found']}** · inexistentes: {t['not_found']} · **inconclusivos: {t['inconclusive']}** · "
            f"não consultados: {t['skipped']}", ""]
    c = summary_counts(res)
    out += ["| " + " | ".join(c) + " |", "|" + "---|" * len(c), "| " + " | ".join(str(v) for v in c.values()) + " |", ""]

    out += ["## Saúde dos conectores (calibração)", "",
            "| plataforma | estado | motivo | requisições | encontrados | inconclusivos | meio da varredura |", "|---|---|---|---|---|---|---|"]
    for cal in res.calibrations:
        s = res.stats["platforms"][cal.platform]
        out.append(f"| {cal.platform} | `{s['state']}` | {s['reason']} | {s['requests']} | {s['found']} | {s['inconclusive']} | {s['midrun'] or '—'} |")
    out += ["", "> Conectores `soft404`, `blind`, `blocked`, `error`, `unstable` e `degraded` **não geram ausência**: "
            "geram *inconclusivo*, com o motivo acima. " +
            ("Conectores sem validação ao vivo neste repositório: " + ", ".join(m["unverified_connectors"]) + "." if m["unverified_connectors"] else ""), ""]

    findings = res.sorted_findings()
    hits = [f for f in findings if f.existence in (Existence.CONFIRMED, Existence.PROBABLE)]
    out += ["## Perfis encontrados (ordenados por prioridade)", ""]
    if not hits:
        out += ["_Nenhum perfil encontrado nas plataformas utilizáveis._", ""]
    for f in hits:
        a = f.assessment
        assert a is not None
        out += [f"### [{a.priority.value}] {f.platform}/{f.username}", "",
                f"- URL: {f.url}",
                f"- Existência: **{f.existence.value}** (confiança do conector {a.existence_confidence:.2f}) · confiança geral {a.confidence:.2f}"
                + (" · **revisão humana necessária**" if a.needs_review else ""),
                f"- Variante: famílias `{', '.join(f.variant.get('families', []))}` · distância {f.variant.get('distance')}",
                f"- Vínculo: {a.affiliation} · Abuso: {a.abuse_level} · Severidade potencial: {a.severity}"]
        if f.profile and (f.profile.get("display_name") or f.profile.get("bio")):
            out.append(f"- Nome: {f.profile.get('display_name')!r}")
            out.append(f"- Bio: {(f.profile.get('bio') or '')[:280]!r}")
        out.append("- Por quê:")
        out += [f"  - {r}" for r in a.reasons]
        out += [f"- Evidência: HTTP {f.evidence.get('http_status')} · `{f.evidence.get('body_sha256', '')[:16]}…` · {f.evidence.get('fetched_at')}", ""]

    inc = [f for f in findings if f.existence == Existence.INCONCLUSIVE]
    if inc:
        out += ["## Inconclusivos (não são ausência)", "", "| plataforma | username | motivo |", "|---|---|---|"]
        out += [f"| {f.platform} | {f.username} | {f.reason} |" for f in inc[:200]]
        out.append("")

    out += ["## Descoberta além da enumeração de handles", "",
            "Clones que usam um handle totalmente diferente (copiando nome de exibição, logo e discurso) **não são "
            "encontrados por enumeração**. Consultas sugeridas (execução manual/assistida):", ""]
    for p in pivots([b["name"], *b["display_names"]], b["domains"])[:14]:
        out.append(f"- `{p['query']}`")
    dv = display_variants(b["name"], 8)
    if dv:
        out += ["", "Nomes de exibição a buscar: " + ", ".join(f"`{d['value']}`" for d in dv), ""]
    out += ["## Limites", "",
            "- Verificação passiva de presença pública; existência ≠ impersonação; prioridade ≠ veredito jurídico.",
            "- Sem login, sem CAPTCHA-bypass, sem rotação de IP/UA. Plataformas muradas tendem a ser inconclusivas.",
            "- Pesos de sinais/famílias são priors heurísticos; meça com `sosia bench` e validação humana.", ""]
    return "\n".join(out)


def to_csv(res: ScanResult) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "platform", "username", "url", "priority", "existence", "confidence", "similarity", "abuse",
                "severity", "affiliation", "needs_review", "reasons"])
    for f in res.sorted_findings():
        a = f.assessment
        w.writerow([f.id, f.platform, f.username, f.url, a.priority.value if a else "", f.existence.value,
                    a.confidence if a else "", a.similarity if a else "", a.abuse_level if a else "",
                    a.severity if a else "", a.affiliation if a else "", a.needs_review if a else "",
                    " | ".join(a.reasons) if a else f.reason])
    return buf.getvalue()


def to_jsonl(res: ScanResult) -> str:
    return "\n".join(json.dumps(f.to_dict(), ensure_ascii=False) for f in res.sorted_findings()) + "\n"


# --------------------------------------------------------------------------- STIX 2.1
def to_stix(res: ScanResult, min_priority: Priority = Priority.MEDIUM) -> dict:
    now = res.meta["started_at"].replace("+00:00", "Z")
    ident_id = f"identity--{uuid.uuid5(_STIX_NS, res.brand['name'].lower())}"
    objs: list[dict] = [{
        "type": "identity", "spec_version": "2.1", "id": ident_id, "created": now, "modified": now,
        "name": res.brand["name"], "identity_class": "organization",
    }]
    refs = [ident_id]
    for f in res.sorted_findings():
        a = f.assessment
        if not a or a.priority.rank < min_priority.rank or f.existence == Existence.INCONCLUSIVE:
            continue
        ind_id = f"indicator--{uuid.uuid5(_STIX_NS, f.platform + '|' + f.username)}"
        objs.append({
            "type": "indicator", "spec_version": "2.1", "id": ind_id, "created": now, "modified": now,
            "name": f"Possível perfil de impersonação: {f.platform}/{f.username}",
            "description": " | ".join(a.reasons),
            "indicator_types": ["malicious-activity"] if a.priority.rank >= Priority.HIGH.rank else ["anomalous-activity"],
            "pattern": f"[url:value = '{f.url}']", "pattern_type": "stix", "valid_from": now,
            "confidence": int(a.confidence * 100),
            "labels": ["brand-impersonation", f"priority-{a.priority.value.lower()}", f"abuse-{a.abuse_level}"],
            "x_sosia_priority": a.priority.value, "x_sosia_severity": a.severity,
            "x_sosia_needs_review": a.needs_review, "x_sosia_evidence_sha256": f.evidence.get("body_sha256"),
        })
        rel = f"relationship--{uuid.uuid5(_STIX_NS, ind_id + ident_id)}"
        objs.append({"type": "relationship", "spec_version": "2.1", "id": rel, "created": now, "modified": now,
                     "relationship_type": "related-to", "source_ref": ind_id, "target_ref": ident_id})
        refs += [ind_id, rel]
    objs.append({"type": "report", "spec_version": "2.1", "id": f"report--{uuid.uuid5(_STIX_NS, now + res.brand['name'])}",
                 "created": now, "modified": now, "name": f"SÓSIA — {res.brand['name']}", "published": now,
                 "report_types": ["threat-report"], "object_refs": refs})
    return {"type": "bundle", "id": f"bundle--{uuid.uuid5(_STIX_NS, now + res.brand['name'] + 'b')}", "objects": objs}


# --------------------------------------------------------------------------- pacote de evidências
def write_case(res: ScanResult, outdir: str | Path) -> Path:
    out = Path(outdir)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}
    files["case.json"] = json.dumps(res.to_dict(), ensure_ascii=False, indent=2).encode()
    files["findings.jsonl"] = to_jsonl(res).encode()
    files["findings.csv"] = to_csv(res).encode()
    files["report.md"] = to_markdown(res).encode()
    files["stix.json"] = json.dumps(to_stix(res), ensure_ascii=False, indent=2).encode()
    cals = {c.platform: c.to_dict() for c in res.calibrations}
    for f in res.sorted_findings():
        if f.existence in (Existence.CONFIRMED, Existence.PROBABLE):
            doc = {"finding": f.to_dict(), "connector_calibration": cals.get(f.platform),
                   "tool": res.meta["tool"], "version": res.meta["version"]}
            files[f"evidence/{f.id}.json"] = json.dumps(doc, ensure_ascii=False, indent=2).encode()
            if f.raw_body is not None:
                files[f"raw/{f.evidence['body_sha256'][:16]}.bin"] = f.raw_body
    for name, data in files.items():
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    manifest = "\n".join(f"{hashlib.sha256(d).hexdigest()}  {n}" for n, d in sorted(files.items())) + "\n"
    (out / "MANIFEST.sha256").write_text(manifest)
    return out


def finding_line(f: Finding) -> str:
    a = f.assessment
    tag = a.priority.value if a else f.existence.value
    return f"[{tag:<7}] {f.platform:<10} {f.username:<28} {f.existence.value:<12}" + (f" conf={a.confidence:.2f} abuso={a.abuse_level}" if a else f" ({f.reason})")
