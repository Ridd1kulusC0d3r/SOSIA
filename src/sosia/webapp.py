"""Frontend opcional SÓSIA. Instale com: pip install gradio reportlab.

Interface não hospedada permanentemente. Recomenda-se Colab com autenticação.
"""
from __future__ import annotations

import html
import json
import re
import time
import uuid
import zipfile
from pathlib import Path

from .model import Brand


THEME_CSS = """
:root {--sosia-bg:#081322;--sosia-green:#64e7c7}
.gradio-container {background:linear-gradient(125deg,#071222,#112638)!important}
#sosia-hero {background:linear-gradient(110deg,#102338,#164747);border:1px solid #31766e;
border-radius:22px;padding:34px 28px;margin-bottom:12px;color:#f4fbff}
#sosia-hero h1 {margin:0;font-size:clamp(33px,5vw,57px);letter-spacing:-.05em}
#sosia-hero h1 span {color:#72ecc7}
#sosia-hero p {color:#c1dfdf;max-width:850px;font-size:16px}
#sosia-hero .eyebrow {color:#8af3d4;font-size:12px;letter-spacing:2px;font-weight:bold}
#sosia-banner {background:#1a2738;border:1px solid #58627c;
border-radius:12px;padding:13px 18px;color:#ead7ad}
#sosia-caption {color:#a1bdcb;padding:10px 0}
"""


def _split(value: str) -> list[str]:
    return [s.strip() for s in (value or "").split(",") if s.strip()]


def make_brand(name: str, handle: str, domains: str,
               official: str, extra_affixes: str) -> Brand:
    """Use textos fornecidos pelo operador apenas para a marca representada."""
    name, handle = name.strip(), handle.strip().lower().lstrip("@")
    if not name or not re.fullmatch(r"[a-z0-9_.-]{2,64}", handle):
        raise ValueError("Informe BRAND e HANDLE válido (2-64 caracteres: letras, números, _, . e -).")
    normalized_domains = []
    for domain in _split(domains):
        domain = domain.lower().strip(".")
        if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", domain):
            raise ValueError("DOMAINS deve ter nomes de domínio sem https://, /caminho ou espaços.")
        normalized_domains.append(domain)
    return Brand(
        name=name, handle=handle, domains=normalized_domains,
        official={"*": {x.lower().lstrip("@") for x in _split(official)}},
        extra_affixes=[x.lower() for x in _split(extra_affixes)],
    )


def list_variants(name: str, handle: str, domains: str,
                  official: str, affixes: str, limit: int):
    from .variants import VariantEngine
    brand = make_brand(name, handle, domains, official, affixes)
    results = VariantEngine(brand.handle, extra_affixes=brand.extra_affixes).generate(
        exclude=brand.official["*"]
    )
    rows = [
        [v.value, ", ".join(sorted(v.families)), round(v.similarity, 3)]
        for v in results[:int(limit)]
    ]
    return (
        "### Resultado da geração\n**" + str(len(results)) +
        " candidatos** foram gerados antes do limite de exibição. "
        "Uma variante não indica que o perfil exista nem que represente abuso.",
        rows,
    )


def inspect_bio(name: str, handle: str, domains: str, official: str,
                affixes: str, username: str, display_name: str, bio: str):
    from .profiles import Profile, find_links
    from .signals import analyze_bio
    brand = make_brand(name, handle, domains, official, affixes)
    prof = Profile(display_name=display_name.strip(), bio=bio or None,
                   links=find_links(bio or ""))
    rep = analyze_bio(prof, brand)
    signal_rows = [
        ["Sinal", sig.id, sig.group, sig.evidence, str(sig.negated)]
        for sig in rep.signals
    ] + [
        ["Mitigador", sig.id, sig.group, sig.evidence, str(sig.negated)]
        for sig in rep.mitigators
    ]
    summary = (
        "### Triagem contextual (offline)\n"
        "- **Candidato:** " + html.escape(username.strip() or "não informado") + "\n"
        "- **Grupos de sinais:** " +
        html.escape(", ".join(rep.groups) or "nenhum") + "\n"
        "- **Menção à marca:** " + ("sim" if rep.brand_mention else "não") + "\n"
        "- **Bio disponível:** " + ("sim" if rep.bio_available else "não") + "\n"
        "- **Disclaimer:** " + ("identificado" if rep.disclaimed else "não identificado") + "\n\n"
        "**Atenção:** nenhuma consulta foi feita à plataforma. "
        "Sinais textuais não confirmam existência, vínculo oficial ou fraude."
    )
    return summary, signal_rows


def run_investigation(name: str, handle: str, domains: str, official: str,
                      affixes: str, platforms: list[str], budget: int,
                      rate: float, confirmed: bool, selected_formats: list[str]):
    if not confirmed:
        raise ValueError("Confirme a autorização para proteger a marca antes de consultar plataformas.")
    brand = make_brand(name, handle, domains, official, affixes)
    if not platforms:
        raise ValueError("Selecione ao menos uma plataforma.")
    if not selected_formats:
        raise ValueError("Selecione ao menos um formato de exportação.")
    from .exports import export_reports
    from .net import UrlLibFetcher
    from .platforms import load_platforms
    from .report import write_case, summary_counts
    from .scanner import Scanner, ScanConfig
    from .textutil import slugify

    requested = load_platforms(only=platforms)
    if not requested:
        raise ValueError("Nenhum conector selecionado é reconhecido.")
    rate = max(float(rate), 0.7)
    budget = max(5, min(int(budget), 200))
    result = Scanner(
        brand, requested,
        UrlLibFetcher(min_interval=rate, timeout=12),
        ScanConfig(budget=budget, save_raw=False, concurrency=min(4, len(requested)), discover=True),
    ).run()
    out = Path("/content/runs_frontend") / (
        (slugify(brand.handle) or "brand") + "-" +
        time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:7]
    )
    write_case(result, out)
    want_html = "HTML" in selected_formats or "Pacote completo" in selected_formats
    want_pdf = "PDF" in selected_formats or "Pacote completo" in selected_formats
    export_reports(result, out, html_report=want_html, pdf_report=want_pdf)

    mapping = {
        "JSON": "case.json", "CSV": "findings.csv",
        "Markdown": "report.md", "JSONL": "findings.jsonl",
        "STIX 2.1": "stix.json", "HTML": "report.html", "PDF": "report.pdf",
    }
    full = "Pacote completo" in selected_formats
    members = sorted(
        [p for p in out.rglob("*") if p.is_file() and p.name != "download-selected.zip"]
        if full else
        [out / mapping[label] for label in selected_formats if label in mapping]
    )
    if not members:
        raise ValueError("Escolha ao menos um arquivo ou o pacote completo.")
    bundle = out / "download-selected.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.write(path, arcname=path.relative_to(out).as_posix())
    rows = []
    for finding in result.sorted_findings()[:100]:
        assessment = finding.assessment
        rows.append([
            finding.platform, finding.username, finding.existence.value,
            assessment.priority.value if assessment else "—",
            round(assessment.confidence, 2) if assessment else 0,
        ])
    t = result.stats["totals"]
    summary = (
        "### Varredura concluída\n"
        "**Consultas:** " + str(t["requests"]) +
        " · **Encontrados:** " + str(t["found"]) +
        " · **Inconclusivos:** " + str(t["inconclusive"]) +
        " · **Conectores utilizáveis:** " + str(t["platforms_usable"]) + "\n\n"
        "**Prioridades:** " + html.escape(json.dumps(summary_counts(result), ensure_ascii=False)) +
        "\n\nResultados dependem do IP e da plataforma. Prioridade não é veredito."
    )
    return (
        summary, rows, str(bundle),
        str(out / "report.html") if want_html else None,
        str(out / "report.pdf") if want_pdf else None,
    )


def create_app():
    """Cria Gradio Blocks sem instalar Gradio no núcleo da aplicação."""
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("Frontend opcional requer: pip install gradio>=5,<7 reportlab>=4") from exc
    from .platforms import load_platforms
    platform_choices = sorted(load_platforms().keys())
    with gr.Blocks(title="SÓSIA | Brand Impersonation Intelligence") as app:
        gr.HTML("""
        <section id="sosia-hero">
        <div class="eyebrow">BRAND IMPERSONATION INTELLIGENCE / OSINT PASSIVO</div>
        <h1>SÓSIA<span>.</span></h1>
        <p>Da variante do username à evidência contextual. Descubra, calibre, investigue e
        revise com incertezas explícitas.</p></section>
        """)
        gr.HTML("""<div id="sosia-banner"><b>Ambiente de investigação autorizado.</b>
        A interface não verifica vínculo legal com marcas; informe apenas marcas que você
        representa. Links compartilhados do Colab são acessíveis a quem os conhece:
        utilize sempre uma senha forte. Sem bypass de login, WAF ou CAPTCHA.</div>""")
        with gr.Accordion("01  Identidade protegida | configuração da marca", open=True):
            with gr.Row():
                name = gr.Textbox(label="BRAND · Nome da marca", value="Marca Zeta",
                    info="Nome público da marca. Ex.: Marca Zeta.")
                handle = gr.Textbox(label="HANDLE · Usuário de referência", value="marcazeta",
                    info="Base do gerador; escreva sem @.")
                domains = gr.Textbox(label="DOMAINS · Domínios oficiais", value="marcazeta.com.br",
                    info="Separados por vírgula, sem https://. Referência de links, não prova de vínculo.")
            with gr.Row():
                official = gr.Textbox(label="OFFICIAL · Perfis autorizados", value="marcazeta, marcazeta_sac",
                    info="Separados por vírgula. Allowlist GLOBAL: perfis ignorados em todas as plataformas.")
                affixes = gr.Textbox(label="EXTRA_AFFIXES · Termos adicionais", value="clube, cartao",
                    info="Palavras específicas do setor que o gerador combina com o handle.")
        inputs = [name, handle, domains, official, affixes]
        with gr.Tabs():
            with gr.Tab("02 · Variantes"):
                gr.Markdown("### Descoberta offline\nGere variantes sem acesso à internet. Similaridade não comprova impersonação.")
                limit = gr.Slider(10, 300, value=50, step=10, label="Variantes exibidas")
                generate = gr.Button("Gerar variantes", variant="primary")
                variant_summary = gr.Markdown()
                variant_grid = gr.Dataframe(headers=["Username", "Família", "Similaridade"],
                    datatype=["str", "str", "number"], type="array", interactive=False)
                generate.click(list_variants, inputs=inputs+[limit],
                               outputs=[variant_summary, variant_grid])
            with gr.Tab("03 · Leitura de bio"):
                gr.Markdown("### Bio Intelligence · sem acesso à rede\n"
                    "Um sinal contextual nunca é prova de autoria ou fraude.")
                with gr.Row():
                    username = gr.Textbox(label="Username a examinar", value="marcazeta_suporte01")
                    display_name = gr.Textbox(label="Nome de exibição", value="Marca Zeta Suporte")
                bio = gr.Textbox(lines=3, label="Bio para análise",
                    value="Suporte oficial Marca Zeta. Chame no WhatsApp e faça o Pix da taxa de liberação.")
                triage = gr.Button("Interpretar bio", variant="primary")
                triage_summary = gr.Markdown()
                signal_grid = gr.Dataframe(
                    headers=["Tipo", "Sinal", "Grupo", "Trecho", "Negado"],
                    type="array", interactive=False)
                triage.click(inspect_bio, inputs=inputs+[username,display_name,bio],
                             outputs=[triage_summary, signal_grid])
            with gr.Tab("04 · Varredura autorizada"):
                gr.Markdown("### Conectores públicos (rede)\n"
                    "A calibração ocorre antes da verificação; alguns conectores podem ficar "
                    "**inconclusivos** por limitação de plataforma.")
                chosen = gr.CheckboxGroup(
                    choices=platform_choices,
                    value=[x for x in ["bluesky", "gitlab", "telegram"] if x in platform_choices],
                    label="Plataformas a consultar")
                with gr.Row():
                    budget = gr.Slider(5, 200, step=5, value=40,
                        label="Orçamento de candidatos por plataforma")
                    rate = gr.Slider(0.7, 3.0, step=0.1, value=1.0,
                        label="Intervalo mínimo por host (segundos)")
                allowed = gr.Checkbox(
                    value=False, label="Declaro que represento a marca e autorizo esta consulta a dados públicos.")
                format_choices = gr.CheckboxGroup(
                    choices=["HTML","PDF","CSV","JSON","Markdown","JSONL","STIX 2.1","Pacote completo"],
                    value=["HTML","PDF","CSV","Pacote completo"],
                    label="Formatos para download")
                scan = gr.Button("Iniciar varredura e gerar arquivos", variant="primary")
                scan_summary = gr.Markdown()
                findings_grid = gr.Dataframe(
                    headers=["Plataforma","Username","Existência","Prioridade","Confiança"],
                    type="array", interactive=False)
                with gr.Row():
                    zip_out = gr.File(label="Baixar formatos selecionados (ZIP)")
                    html_out = gr.File(label="Relatório HTML")
                    pdf_out = gr.File(label="Relatório PDF")
                scan.click(run_investigation,
                    inputs=inputs+[chosen,budget,rate,allowed,format_choices],
                    outputs=[scan_summary,findings_grid,zip_out,html_out,pdf_out])
        gr.Markdown("**Sobre os resultados:** o SÓSIA não automatiza denúncia e não transforma "
                    "evidência insuficiente em afirmação. O pacote de evidências original "
                    "pode ser verificado com MANIFEST.sha256.")
    return app
