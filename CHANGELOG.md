# Changelog

## 1.2.0 — 2026-10-23
**Descoberta por busca integrada, regras corrigidas pelo bench real, Watch, relatórios HTML/PDF.**

- `scan`/`watch`/webapp usam por padrão a **busca nativa** (Bluesky/Mastodon) para achar candidatas (`--no-discover` desliga). Achado do bench real: a busca lista
  ~100% dos handles que contêm a marca; a enumeração de variantes, 2–3%. A descoberta falhar nunca derruba a varredura e é reportada como "indisponível".
- **Marca saturada** (≥40 handles com a marca **ou** ≥150 resultados do Bluesky; 13% das 140 marcas do bench) ativa `ambiguous` automaticamente: prioridade limitada a ALTO.
- Triagem corrigida com dados reais (ver `docs/REAL_BENCH.md`): abuso sem relação com a marca não é alerta; `lookalike_link` não é evidência dura; domínio irmão (mesmo rótulo, outro TLD) é neutro;
  "oficial" sem abuso = MÉDIO; semelhança sozinha = BAIXO; menção na bio é contexto (ALTO/CRÍTICO exigem semelhança de handle/nome).
- `sosia bench-real`: bench com dados e oráculos reais (cache local; nenhum texto de terceiros é versionado).
- `sosia watch`: monitoramento com estado e eventos (perfil novo, bio alterada, escalonamento, remoção, **perda de cobertura de conector**).
- Relatórios HTML/PDF e frontend Gradio (extras `[web]`, `[pdf]`).
- Correções: histórico do Watch não sobrescreve rodadas no mesmo segundo; `discover` reporta erros de rede/JSON; consulta URL-encoded.

## 1.1.0 — 2026-10-15
Núcleo: variantes, calibração de conectores (incl. modo diferencial validado e canário), leitura de bio com negação/mitigadores, triagem multidimensional,
pacote de evidências com manifesto SHA-256, STIX 2.1, `diff`, `eval`, `fit-priors`, bench sintético, validação ao vivo de 17 conectores.
