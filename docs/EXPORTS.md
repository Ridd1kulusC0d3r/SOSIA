# Exportação e download seletivo de relatórios

O SÓSIA agora oferece **dois caminhos de uso no Google Colab**, que compartilham o mesmo motor:

| Máquina | Notebook | Melhor uso |
|---|---|---|
| **Colab 1 · CLI / análise** | [sosia_colab.ipynb](../notebooks/sosia_colab.ipynb) | Execução passo a passo, parâmetros visíveis, experimentos e download por checkbox |
| **Colab 2 · Intelligence Console** | [sosia_frontend_colab.ipynb](../notebooks/sosia_frontend_colab.ipynb) | Interface Gradio com variantes, análise de bio, varredura autorizada e relatórios visuais |

## Quais formatos posso escolher?

| Formato | Arquivo | Utilidade |
|---|---|---|
| **HTML** | \`report.html\` | Relatório responsivo com métricas, saúde dos conectores e tabela de achados; abre em qualquer navegador |
| **PDF** | \`report.pdf\` | Relatório paginado para leitura offline e revisão interna |
| **CSV** | \`findings.csv\` | Triagem tabular, planilhas e análise quantitativa |
| **JSON** | \`case.json\` | Dados estruturados do caso para APIs e análise programática |
| **JSONL** | \`findings.jsonl\` | Um achado por linha, adequado a pipelines |
| **Markdown** | \`report.md\` | Relatório editável em texto |
| **STIX 2.1** | \`stix.json\` | Interoperabilidade com ferramentas de inteligência |
| **MANIFEST** | \`MANIFEST.sha256\` | Comprovação de integridade dos arquivos completos do pacote |
| **Pacote completo** | \`*-completo.zip\` | Evidências, JSON, CSV, STIX, Markdown, HTML, PDF e manifesto disponíveis |

### No Colab principal

1. Execute as células de configuração, calibração e varredura.
2. Chegue à seção **7. Exportar por escolha**.
3. Marque apenas os formatos necessários, por exemplo **PDF + HTML + CSV**.
4. Escolha **Selecionados (ZIP)**, **Arquivos individuais** ou **Pacote completo (ZIP)**.
5. Execute a célula para gerar/download os arquivos.

**Observação:** a opção de arquivos individuais pode acionar várias permissões de download do navegador. Para evitar isso, escolha ZIP.

### No frontend Gradio

1. Execute o segundo notebook Colab; defina uma senha de pelo menos 12 caracteres.
2. Entre no link temporário com seu usuário e senha.
3. Configure BRAND, HANDLE, DOMAINS, OFFICIAL e EXTRA_AFFIXES.
4. Use abas offline para testar variantes e bio.
5. Na aba de varredura, selecione plataformas e formatos, confirme que você representa a marca e execute.
6. Baixe o ZIP selecionado, além do HTML/PDF se marcados.

O frontend não dispensa confirmação de autorização nem revisão das evidências.

## Como gerar HTML e PDF a partir de um caso salvo

O pacote Python mantém a geração HTML sem dependências externas. PDF precisa da biblioteca opcional **ReportLab**.

\`\`\`bash
python -m pip install -e .
python -m pip install 'reportlab>=4'
\`\`\`

Depois de ter um pacote \`runs/minha-marca/case.json\`, gere relatórios usando somente dados locais:

\`\`\`python
import json
from pathlib import Path
from sosia.exports import export_reports

out = Path("runs/minha-marca")
case = json.loads((out / "case.json").read_text(encoding="utf-8"))
export_reports(case, out, html_report=True, pdf_report=True)
print("HTML:", out / "report.html", "PDF:", out / "report.pdf")
\`\`\`

**Integridade:** se \`MANIFEST.sha256\` existir, \`export_reports\` inclui/atualiza os hashes dos novos relatórios. O manifesto original de evidências é preservado para os outros arquivos. Para verificar o pacote completo, confira cada caminho no manifesto contra o SHA-256 do arquivo correspondente.

## Segurança e privacidade

- **HTML é estático**, sem JavaScript de rastreamento. Dados das plataformas são escapados antes de serem inseridos na página.
- Não publique o HTML/PDF indiscriminadamente: ambos podem conter usernames, bios e URLs públicos vinculados ao caso.
- Um **ZIP selecionado** nem sempre contém todos os arquivos citados no manifesto. Para evidência completa com verificação de integridade, use **Pacote completo**.
- Gradio no Colab fornece um **link temporário**. Se \`share=True\`, o endereço é acessível a terceiros que conheçam o link; o notebook força autenticação, mas um servidor privado é mais adequado a material sensível.
- Não há coleta de dados autenticados, bypass de CAPTCHA/WAF ou denúncia automática.

## Reprodutibilidade

A geração HTML recebe \`ScanResult\` ou um dicionário extraído de \`case.json\`. PDF usa os mesmos dados. A exportação não faz chamadas externas e não altera classificações produzidas pelo motor.

Testes: \`python -m unittest discover -s tests -v\`. A CI do GitHub executa \`unittest\` e benchmark rápido; os testes de PDF dependem de ReportLab opcional.
