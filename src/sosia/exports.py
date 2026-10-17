"""Relatórios HTML/PDF e manifesto de exportações.

HTML usa somente a biblioteca padrão; PDF requer reportlab, instalado
opcionalmente no Colab. Os relatórios derivam de ScanResult ou case.json,
sem consultas adicionais à rede.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .model import ScanResult


def _document(source: ScanResult | dict) -> dict:
    if isinstance(source, dict):
        return source
    return source.to_dict()


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else "—"), quote=True)


def _profile_link(value: object) -> str:
    url = str(value or "")
    try:
        parsed = urlsplit(url)
    except ValueError:
        return _esc(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return _esc(url)
    safe = _esc(url)
    return '<a href="' + safe + '" target="_blank" rel="noopener noreferrer">' + safe + "</a>"


def render_html(source: ScanResult | dict) -> str:
    """Relatório responsivo sem JS externo e com dados não confiáveis escapados."""
    d = _document(source)
    b = d.get("brand", {})
    m = d.get("meta", {})
    stats = d.get("stats", {})
    totals = stats.get("totals", {})
    findings = d.get("findings", [])
    cals = d.get("calibrations", [])
    name = _esc(b.get("name", "Marca"))
    cards = [
        ("Requisições", totals.get("requests", 0)),
        ("Candidatos gerados", totals.get("candidates_generated", 0)),
        ("Encontrados", totals.get("found", 0)),
        ("Inconclusivos", totals.get("inconclusive", 0)),
    ]
    cards_html = "".join(
        '<article class="metric"><span>' + _esc(label) + '</span><strong>'
        + _esc(value) + "</strong></article>" for label, value in cards
    )
    cal_rows = []
    for c in cals:
        p = str(c.get("platform", ""))
        per = stats.get("platforms", {}).get(p, {})
        state = per.get("state") or c.get("state", "unvalidated")
        cal_rows.append(
            "<tr><td>" + _esc(p) + "</td><td><code>" + _esc(state)
            + "</code></td><td>" + _esc(per.get("reason") or c.get("reason", ""))
            + "</td><td>" + _esc(per.get("requests", c.get("requests", "—")))
            + "</td></tr>"
        )
    finding_rows = []
    for f in findings:
        a = f.get("assessment") or {}
        reasons = a.get("reasons") or [f.get("reason", "")]
        profile = f.get("profile") or {}
        priority = a.get("priority") or "—"
        css_tag = "high" if priority in ("CRITICO", "ALTO") else "neutral"
        finding_rows.append(
            "<tr><td><span class=\"flag " + css_tag + "\">" + _esc(priority)
            + "</span></td><td>" + _esc(f.get("platform", "")) + "</td><td><strong>"
            + _esc(f.get("username", "")) + "</strong></td><td>"
            + _esc(f.get("existence", "")) + "</td><td>"
            + _profile_link(f.get("url")) + "</td><td>"
            + _esc((profile.get("bio") or "")[:280])
            + "</td><td>" + _esc(" | ".join(str(x) for x in reasons))
            + "</td></tr>"
        )
    off = json.dumps(b.get("official", {}), ensure_ascii=False, sort_keys=True)
    css = """
    :root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif}
    *{box-sizing:border-box}body{background:#081322;color:#eaf5fb;margin:0;line-height:1.5}
    .shell{max-width:1300px;margin:auto;padding:35px 26px 70px}
    .kicker{color:#68e3c4;letter-spacing:.13em;font-weight:800;font-size:12px}
    h1{font-size:clamp(32px,5vw,58px);letter-spacing:-.04em;margin:8px 0}
    h1 span{color:#6fe3c3}h2{font-size:22px;margin:40px 0 16px}
    .muted{color:#aac2d1}.intro{font-size:16px;color:#c6d9e5;max-width:860px}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:28px 0}
    .metric,.info,.table-wrap{border:1px solid #2a4b5d;background:#11273a;border-radius:15px}
    .metric{padding:21px}.metric span{color:#a8bfce;font-size:13px;display:block}
    .metric strong{font-size:32px;display:block;margin-top:7px}
    .info{padding:19px 22px;margin-top:18px}.info p{margin:7px 0}
    .notice{border-left:4px solid #eec17e;padding:13px 20px;background:#2b2c35;color:#f7e9d1;border-radius:6px;margin:24px 0}
    .table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}
    th{text-align:left;font-size:12px;color:#9cbbc9;letter-spacing:.05em;background:#163347}
    td,th{padding:14px 12px;border-bottom:1px solid #254157;vertical-align:top}
    tbody tr:hover{background:#192e42}
    code,.flag{border-radius:6px;background:#274052;padding:4px 7px;font-size:12px;color:#b9f1e0}
    .flag.high{background:#553340;color:#ffbdc7}.flag.neutral{background:#294a49}
    a{color:#83e2d2;overflow-wrap:anywhere}
    .footer{color:#a5b9c7;margin-top:32px;font-size:13px}
    @media(max-width:820px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:500px){.shell{padding:20px 12px}.grid{grid-template-columns:1fr 1fr}.metric{padding:12px}.metric strong{font-size:24px}}
    @media print{:root{color-scheme:light}body{background:white;color:#102333}
    .metric,.info,.table-wrap{background:white;border-color:#b4c8d5}
    .muted,.intro{color:#42596b}th{background:#e4edf4;color:#13293b}
    td,th{border-color:#d7e0e8}a{color:#164d7b}.notice{background:#fff4dc;color:#5a3b18}}
    """
    return (
        "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        "<title>SÓSIA | Relatório " + name + "</title>"
        "<style>" + css + "</style></head><body><main class=\"shell\">"
        '<div class="kicker">SÓSIA / BRAND IMPERSONATION INTELLIGENCE</div>'
        "<h1>Relatório <span>" + name + "</span></h1>"
        '<p class="intro">Investigação passiva de perfis públicos. A prioridade sugere revisão, '
        "não comprova fraude ou autoria. Este relatório reflete apenas o momento da coleta.</p>"
        '<div class="grid">' + cards_html + "</div>"
        '<section class="info"><strong>Configuração e contexto</strong><p>Handle: <code>'
        + _esc(b.get("handle", "")) + "</code> · Domínios: "
        + _esc(", ".join(b.get("domains", []))) + "</p><p>Oficiais: "
        + _esc(off) + "</p><p>Versão: " + _esc(m.get("version", "—"))
        + " · Início: " + _esc(m.get("started_at", "—"))
        + " · Duração: " + _esc(m.get("duration_s", "—")) + " s</p></section>"
        '<aside class="notice"><strong>Leitura responsável:</strong> existência não é impersonação; '
        "bloqueio, CAPTCHA e resposta incerta não significam ausência. Revise as fontes originais "
        "antes de agir. Nenhuma denúncia automática é realizada.</aside>"
        "<h2>Saúde dos conectores</h2><div class=\"table-wrap\"><table><thead><tr>"
        "<th>Plataforma</th><th>Estado</th><th>Motivo</th><th>Requisições</th></tr></thead><tbody>"
        + ("".join(cal_rows) or '<tr><td colspan="4">Sem calibrações registradas</td></tr>')
        + "</tbody></table></div>"
        "<h2>Perfis e achados</h2><div class=\"table-wrap\"><table><thead><tr>"
        "<th>Prioridade</th><th>Plataforma</th><th>Handle</th><th>Existência</th>"
        "<th>Fonte</th><th>Bio pública</th><th>Motivos</th></tr></thead><tbody>"
        + ("".join(finding_rows) or '<tr><td colspan="7">Nenhum perfil registrado na execução</td></tr>')
        + "</tbody></table></div>"
        '<p class="footer">Produzido localmente a partir de case.json. Conteúdo de plataformas '
        "pode estar incompleto; o pacote original e seu manifesto SHA-256 são a referência "
        "de integridade, quando disponíveis.</p></main></body></html>"
    )


def render_pdf(source: ScanResult | dict) -> bytes:
    """PDF textual paginado. reportlab é dependência exclusiva desta função."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except ImportError as exc:
        raise RuntimeError("Para exportar PDF, instale a dependência opcional: pip install reportlab>=4") from exc
    import io

    d = _document(source)
    b, m = d.get("brand", {}), d.get("meta", {})
    stats = d.get("stats", {})
    totals = stats.get("totals", {})
    buffer = io.BytesIO()
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="SosiaTitle", parent=base["Title"], fontName="Helvetica-Bold",
                            fontSize=23, leading=30, textColor=colors.HexColor("#0b2a3d"), spaceAfter=15))
    base.add(ParagraphStyle(name="SosiaSection", parent=base["Heading2"], fontSize=14,
                            textColor=colors.HexColor("#125c63"), spaceBefore=16, spaceAfter=9))
    base.add(ParagraphStyle(name="SosiaBody", parent=base["BodyText"], fontSize=9, leading=13,
                            spaceAfter=7, wordWrap="CJK"))
    base.add(ParagraphStyle(name="SosiaSmall", parent=base["BodyText"], fontSize=7.4, leading=10,
                            wordWrap="CJK"))
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=35, leftMargin=35,
                            topMargin=45, bottomMargin=40, title="SÓSIA - relatório")
    story = [
        Paragraph("SÓSIA | Relatório de investigação", base["SosiaTitle"]),
        Paragraph("<b>Marca:</b> " + _esc(b.get("name", "—")) +
                  "<br/><b>Handle:</b> " + _esc(b.get("handle", "—")) +
                  "<br/><b>Domínios oficiais:</b> " + _esc(", ".join(b.get("domains", []))) +
                  "<br/><b>Data:</b> " + _esc(m.get("started_at", "—")) +
                  "<br/><b>Versão:</b> " + _esc(m.get("version", "—")), base["SosiaBody"]),
        Spacer(1, 9),
        Paragraph("<b>Atenção:</b> uma conta encontrada não é necessariamente impostora. "
                  "Bloqueios são inconclusivos. Revise manualmente qualquer achado.",
                  base["SosiaBody"]),
        Paragraph("Resumo executivo", base["SosiaSection"]),
    ]
    metrics = [
        ["Requisições", "Candidatos", "Encontrados", "Inconclusivos"],
        [str(totals.get(key, 0)) for key in
         ("requests", "candidates_generated", "found", "inconclusive")],
    ]
    table = Table(metrics, colWidths=[132] * 4, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123e54")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#edf7f5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7dce0")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Paragraph("Saúde dos conectores", base["SosiaSection"]))
    cals = d.get("calibrations", [])
    if not cals:
        story.append(Paragraph("Nenhuma calibração registrada.", base["SosiaBody"]))
    for c in cals:
        platform = str(c.get("platform", ""))
        detail = stats.get("platforms", {}).get(platform, {})
        state = detail.get("state") or c.get("state") or "—"
        reason = detail.get("reason") or c.get("reason") or ""
        story.append(Paragraph("<b>" + _esc(platform) + ":</b> " + _esc(state)
                               + " · " + _esc(str(reason)[:350]), base["SosiaSmall"]))
    story.append(Paragraph("Perfis e achados", base["SosiaSection"]))
    findings = d.get("findings", [])
    if not findings:
        story.append(Paragraph("Nenhum achado registrado.", base["SosiaBody"]))
    for i, finding in enumerate(findings):
        a = finding.get("assessment") or {}
        reasons = a.get("reasons") or [finding.get("reason", "")]
        profile = finding.get("profile") or {}
        story.append(Paragraph(
            "<b>" + _esc(a.get("priority", "—")) + " | " + _esc(finding.get("platform", "")) +
            " / " + _esc(finding.get("username", "")) + "</b><br/>"
            "Existência: " + _esc(finding.get("existence", "—")) +
            " · URL: " + _esc(finding.get("url", "")) + "<br/>"
            "Bio: " + _esc(str(profile.get("bio") or "")[:260]) + "<br/>"
            "Motivos: " + _esc(" | ".join(str(r) for r in reasons)[:650]),
            base["SosiaSmall"]))
        story.append(Spacer(1, 5))
    story.append(Paragraph("Limitações e interpretação", base["SosiaSection"]))
    story.append(Paragraph(
        "A ferramenta realiza verificações passivas. Uma menção à marca, um domínio na "
        "bio ou um username parecido não constituem prova de vínculo, abuso ou autoria. "
        "Conectores podem mudar de resposta por IP, região e horário. Os achados exigem "
        "revisão humana antes de qualquer ação externa.", base["SosiaBody"]))

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#486473"))
        canvas.drawString(35, 23, "SÓSIA | Intelligence report · revisão humana necessária")
        canvas.drawRightString(A4[0] - 35, 23, "Página " + str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def export_reports(source: ScanResult | dict, outdir: str | Path,
                   *, html_report: bool = True, pdf_report: bool = False) -> list[Path]:
    """Gera formatos opcionais no pacote e atualiza hashes do manifesto."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    if html_report:
        target = out / "report.html"
        target.write_text(render_html(source), encoding="utf-8")
        exported.append(target)
    if pdf_report:
        target = out / "report.pdf"
        target.write_bytes(render_pdf(source))
        exported.append(target)
    manifest = out / "MANIFEST.sha256"
    if manifest.exists() and exported:
        entries = {}
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if "  " in line:
                digest, relative = line.split("  ", 1)
                if re.fullmatch(r"[0-9a-f]{64}", digest):
                    entries[relative] = digest
        for target in exported:
            entries[target.relative_to(out).as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest.write_text("".join(entries[k] + "  " + k + "\n" for k in sorted(entries)),
                            encoding="utf-8")
    return exported
