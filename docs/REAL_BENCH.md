# Bench REAL — dados e oráculos reais, e o que ele desmentiu

> Data: 2026-10-17 · Reprodução: `sosia bench-real --stages r1,r3,r4` (e `r2`, ~1 h por limites de taxa).
> Texto de terceiros (bios) **não é versionado**: o cache fica local. Aqui há só agregados.

Este documento existe porque o bench sintético (`BENCH_RESULTS.md`) mede como o motor se comporta contra um mundo **que eu mesmo projetei**.
Aqui as perguntas são feitas a dados que eu não controlo. O resultado, em uma linha:

> **Sem corpus real de impersonadores rotulados, o recall do SÓSIA é desconhecido; e a precisão que eu reportava era um artefato do corpus sintético.**
> Em contas reais, a versão original gerava dezenas de falsos alertas por conjunto; corrigi as regras com base nisso (abaixo), e o que sobra é uma
> carga de alertas baixa — mas **não há como dizer, com estes dados, quantos impersonadores ele deixa passar**.

## 1. Desenho

| Item | Escolha | Por quê / limite |
|---|---|---|
| Marcas | Sorteio **determinístico** da lista [Tranco](https://tranco-list.eu/) (a mesma família usada no estudo CISPA/USENIX 2024): 16 globais (rank 100–6000) + 16 `.com.br` (até 60 mil), rótulo `[a-z]{5,14}`; **5 conjuntos disjuntos = 139 marcas** | Inclui infraestrutura (CDN, parking) e palavras comuns (`washington`, `privacy`, `stone`) — **sem filtrar**. Única exclusão: `redtube` (conteúdo adulto) |
| Descoberta independente | `searchActors` (Bluesky) e `/api/v2/search` (Mastodon) pelo nome da marca | Independe do meu gerador. **Viés:** ranking por popularidade/relevância da plataforma; só 2 redes, e **não são onde a maioria dos golpes brasileiros acontece** (Instagram, WhatsApp, Telegram, X) |
| Oráculos de existência (R2) | Bluesky `resolveHandle`, Mastodon `webfinger`, página do DEV/GitLab | Independentes do conector; podem errar (contas suspensas, grupos GitLab) |
| Texto de golpe rotulado por terceiros (R4) | [UCI SMS Spam](https://huggingface.co/datasets/dbarbedillo/SMS_Spam_Multilingual_Collection_Dataset): 5.572 SMS, 747 spam; `en` + tradução automática `pt`/`es` | **Não é bio de perfil nem golpe de marca**; mede só a camada de linguagem. Domínio muito diferente (SMS britânicos de 2000s) |
| Revisão manual | Eu li todos os sinalizados (≥ALTO) e todos os MÉDIO dos conjuntos mais novos | **Um único revisor, não independente do autor das regras.** Rótulos aqui são julgamento, não verdade |

**Disciplina de conjuntos.** `dev` (31 marcas) revelou os defeitos; `hold-out #1` (27) revelou mais; `#2` revelou o problema da fila; `#3` testou as
correções; `#4` (27 marcas, 708 contas) foi colhido **depois de congelar as regras** e não foi usado em nenhuma decisão. Mesmo assim, a seleção de
marcas, as consultas e o limite de 200 contas por busca são minhas — não é um experimento pré-registrado.

## 2. R1 — o teto da enumeração (o achado mais incômodo)

139 marcas, **5.327 contas** devolvidas pela busca nativa:

| Classe do handle (vs. marca) | Contas | % |
|---|---|---|
| Sem relação (aparece pelo nome de exibição/bio) | 2.584 | 48,5% |
| **Contém a marca** (ou muito parecido) | **2.261** | **42,4%** |
| Domínio próprio (`marca.com.br`, não enumerável) | 314 | 5,9% |
| Nome exato da marca | 168 | 3,2% |

Cobertura do gerador sobre os 2.261 handles que contêm a marca (IC 95% de Wilson):

| Estratégia | Orçamento 200 | Lista inteira |
|---|---|---|
| tipo-Sherlock (só separadores) | 0,0% [0,0–0,2] | 0,0% |
| tipo-dnstwist (typos/homóglifos) | 1,0% [0,6–1,5] | 1,0% |
| **SÓSIA** (typos + afixos pt-BR + dígitos) | **2,0% [1,5–2,7]** | **3,3% [2,6–4,1]** |
| SÓSIA, excluindo as 17 marcas "saturadas"* (n=375) | 2,9% [1,6–5,2] | 5,1% [3,3–7,8] |

\* ≥ 40 handles contendo a marca (12% das marcas): `alelo`, `penso`, `washington`, `privacy`, `stone`, `charter`, `amplify`, `bumble`, `safra`… — palavras
comuns ou marcas gigantes, onde "contém a marca" quase nunca é impersonação.

**Leitura crítica**
1. O que as plataformas associam a uma marca é, em sua maioria, *fãs, funcionários, homônimos e palavras comuns*, não impersonadores. Os resíduos reais depois da marca
   (`downloader`, `app`, `gold`, `center`, `sarkari`, `1`, `br`, `official`) **quase não coincidem com o meu léxico de autoridade/atendimento/Pix**.
   A hipótese que embasou o ranking de variantes (afixos de golpe em pt-BR dominam) **não encontra suporte** nestes dados — com a ressalva de que Bluesky/Mastodon não são o
   habitat desses golpes.
2. A enumeração cobre ~3–5% do que a busca devolve. Para quem quer **listar candidatos**, a busca é muito mais eficiente (`sosia discover`); enumeração fica para
   o que a busca não indexa (checagem direta de um handle suspeito, confundíveis visuais, monitoramento do que já se conhece).
3. O bench sintético prometia 24,1% @200 (e 72% em `affix_in`). Aquilo mediu o meu gerador contra o meu atacante simulado.

## 3. R3 — triagem em bios reais: o que quebrou, e as correções

Mesmas 5.327 contas. (O `dev` inicial incluía ~12 mil contas de buscas "isca" — `marca suporte`, `marca sorteio` —, que retornam contas genéricas sem relação com a marca; foram descartadas daqui em diante, mas é delas que vêm os 504 ALTO do defeito #1.)

### Defeitos encontrados (todos meus) e correção

| # | Defeito | Evidência real | Correção |
|---|---|---|---|
| 1 | `abuso forte` → **ALTO sem exigir relação com a marca** | `dev`: 486 de 504 ALTO eram hosts de sorteio, criadores com doação via Pix, artistas — `brand_mention=False`, semelhança ~0,2 | Linguagem de golpe sem referência à marca ⇒ BAIXO ("não é impersonação desta marca") |
| 2 | `lookalike_domain` contava como evidência **dura** | 0 de 14 (`dev`) eram impersonação: domínios irmãos (`transfermarkt.de/.com`), podcasts, sites de fãs, produtos homônimos | Mesmo rótulo em outro TLD = `sibling_tld` (neutro); `lookalike_link` saiu de HARD e vira sinal brando |
| 3 | "handle parecido + alegação de oficial, sem abuso" ⇒ ALTO | `hold-out #1`: ~25 de 26 ALTO eram entidades legítimas de nome comum ("Official account of …": órgãos públicos, times e veículos cujo nome coincide com a marca) | ⇒ MÉDIO |
| 4 | Semelhança sozinha ⇒ MÉDIO | `hold-out #2`: **49% das contas** (718/1.455) em MÉDIO | Semelhança sozinha = BAIXO (lista). Fila (MÉDIO) só com algo específico: alegação, desvio de canal, confundível visual |
| 5 | Menção à marca na bio contava como identidade | `hold-out #3`: 3 ALTO eram pessoas listando "Pix (Nubank)" como chave de doação | ALTO (abuso moderado) exige semelhança de handle/nome ≥ 0,7 e CRÍTICO ≥ 0,6; menção é só contexto. *Resta* o caso `strong` + menção ⇒ ALTO (1 falso positivo em 5.327: `tailwindcss`) — deixado assim de propósito, para não cegar o detector a golpes com nome genérico |
| 6 | Watch: histórico com resolução de 1 s sobrescrevia rodadas rápidas | teste intermitente | timestamp com microssegundos |

### Efeito (contas reais, regras finais)

| Conjunto | Marcas | Contas | CRÍTICO | ALTO | MÉDIO | Observação |
|---|---|---|---|---|---|---|
| `dev` (só busca pura) | 31 | 852 | 0 | 0 | 4 | antes das correções: **504 ALTO** (buscas isca incluídas) |
| hold-out #1 | 27 | 1.374 | 3 | 4 | 70 | **ainda ruim**: 7 sinalizados, todos colisão de marca-palavra (`privacy` ×4, `blockchain` ×2, `tailwindcss` ×1) — ver §5 |
| hold-out #2 | 27 | 1.455 | 0 | 0 | 18 | antes da regra 4: 718 MÉDIO |
| hold-out #3 | 27 | 938 | 0 | 0 | 18 | antes da regra 5: 3 ALTO |
| **hold-out #4 (regras congeladas)** | 27 | **708** | **0** | **0** | **9** | nunca usado em decisão |
| **Total** | **139** | **5.327** | **3** | **4** | **119** | 7 sinalizados (0,13%), **0 corretos** |

**Precisão dos sinalizados (revisão manual, 1 revisor)** — antes das correções 3–5, no hold-out #1: 35 sinalizados (9 CRÍTICO + 26 ALTO), **~3 plausíveis**
(ex.: perfis de "atendimento/suporte" de marca conhecida, com domínio parecido ou telefone, que não consegui verificar como legítimos ou falsos) e **~32 falsos positivos** ⇒ precisão ≲ 10%.
Depois das correções, restam **7 sinalizados em 5.327 contas** (todos no hold-out #1) e **todos são falsos positivos** por colisão de nome de marca comum.

**O que não consigo afirmar**
- **Recall é desconhecido.** Em ~5 mil contas reais encontrei **um** caso genuinamente suspeito (uma conta com o nome da marca e bio "Suporte Oficial <marca>", que caiu em MÉDIO por causa da correção #3)
  e talvez dois (perfis de "atendimento" com domínio parecido, não verificáveis por mim). Com ≤3 positivos prováveis, qualquer taxa de detecção seria ruído.
- A carga baixa de alertas (0 CRÍTICO/ALTO em 708 contas inéditas) é **compatível com um detector bom e com um detector cego**. Só dados positivos distinguem os dois.
- Tudo aqui é Bluesky/Mastodon, buscando pelo nome da marca. Não representa Instagram, WhatsApp, Telegram, X, TikTok.

### Contraste com o sintético (mesmas regras finais)

| Triagem sintética, split de teste | Antes das correções | Depois |
|---|---|---|
| CRÍTICO vs golpe | P 100% / **R 42%** | P 100% / **R 31%** |
| ≥ALTO vs golpe ∪ impersonação | P 100% / **R 76%** | P 100% / **R 23%** |

Os dois bancos puxam em direções opostas: **o real diz "alertas demais", o sintético diz "golpes de menos"**. A verdade sobre o equilíbrio só virá de um corpus real
com positivos. Até lá, trate os limiares como hipóteses.

## 4. R4 — camada de linguagem contra rótulos de terceiros (UCI SMS Spam)

747 spam / 4.825 ham. Texto original em inglês e tradução automática para pt/es. "Alerta" = `abuse_level` ≥ nível indicado, **sem** contexto de marca.

| Idioma | Nível | Recall [IC 95%] | Taxa de falso positivo | Precisão |
|---|---|---|---|---|
| en | qualquer sinal | 2,3% | 0,2% | 68,0% |
| **pt (MT)** | qualquer sinal | **13,4%** [11,1–16,0] | 0,6% | 78,1% |
| pt (MT) | moderado+ | 7,6% [5,9–9,8] | 0,3% | 81,4% |
| pt (MT) | **forte** (pré-requisito de CRÍTICO) | **1,3%** [0,7–2,4] | 0,0% | 100% (n=10) |
| es (MT) | qualquer sinal | 8,6% | 0,3% | 81,0% |
| baseline "palavra-chave" (v1.1) | pt | 15,3% | 0,5% | 83,2% |

**Leitura crítica.** O léxico detecta uma fração mínima de spam real, e o nível "forte" praticamente nunca dispara (SMS de prêmio/ligue-já não usa Pix/WhatsApp).
Isso **não** significa que falhe em bios brasileiras de golpe — o domínio é outro —, mas mostra que (a) a cobertura lexical é estreita, (b) inglês está quase descoberto,
(c) a "detecção de golpe" do SÓSIA hoje é **um conjunto de padrões pt-BR escritos à mão, sem validação em golpes reais**. A baixa taxa de falso positivo (0–0,6%) é o lado bom.

## 5. Causa raiz que ainda não está resolvida: marcas que são palavras comuns

12% das marcas sorteadas são "saturadas" (≥ 40 handles com a marca). Nelas, similaridade e menção não significam nada. Mitigações implementadas, **não resolutivas**:
`ambiguous = true` no `sosia.toml` (limita a prioridade a ALTO) e `sosia discover`, que mede a saturação da busca e avisa. Para essas marcas,
só evidência *fora do texto* (domínio verificado, telefone, similaridade de imagem, link recíproco) pode sustentar um alerta — e isso o SÓSIA ainda não faz.

## 6. R2 — existência contra oráculos independentes (distribuição real)

Candidatas = 10 contas semente (descobertas pela busca, existem) + melhores variantes do gerador, por marca, 31 marcas do `dev`. Cada candidata é consultada pelo
**conector do SÓSIA**, por um **oráculo independente** e (quando aplicável) pela estratégia **ingênua** "a página responde 200 ⇒ existe".

| Plataforma | Candidatas | Existem (oráculo) | SÓSIA: recall [IC 95%] | SÓSIA: FPR [IC 95%] | Ingênuo (página 200): FPR | Observação |
|---|---|---|---|---|---|---|
| Bluesky (API `getProfile`) | 1.063 | 114 | **94,7%** [89,0–97,6] | **0/949** [0,0–0,4%] | **949/949 = 100%** | página `bsky.app` é SPA: 200 para tudo |
| **Bluesky, conector-página SPA recuperado pela calibração** | 1.063 | 114 | **96,5%** [91,3–98,6] | **0/949** [0,0–0,4%] | — | `differential` + validação (2/2, 6/6) |
| Mastodon (`accounts/lookup`) | 253 | 8 | 100% [67,6–100] (n=8) | 0/245 [0,0–1,5%] | 0/245 | página `/@user` devolve 404 corretamente: ingênuo = SÓSIA |
| DEV (API) | 930 | 6 | 100% [61,0–100] (n=6) | 0/924 [0,0–0,4%] | n/a (ingênuo ≡ oráculo) | |
| GitLab | — | — | — | — | — | **Oráculo inválido**: a página devolveu 403 em 882/931 requisições (WAF). Sem conclusão |

**O que isso sustenta**
- **Confirma, em plataforma real, o argumento central da calibração**: o SPA do Bluesky faz o ingênuo marcar 100% das variantes como existentes (949 falsos positivos);
  um conector configurado do mesmo jeito foi **recuperado** pela calibração diferencial + validação (FPR 0/949, recall 96,5%), em vez de inundar o relatório.
- 0 falsos positivos em 2.100+ negativos reais (variantes de 31 marcas) nas 3 plataformas com oráculo válido.

**Ressalvas (leia antes de citar)**
1. **Prevalência baixíssima** (Mastodon 8, DEV 6 positivos): os ICs de recall são enormes. Recall só tem poder razoável no Bluesky (n=114).
2. Os positivos são em boa parte **sementes** vindas da busca (existem por construção), não achados naturais do gerador — isso mede *confirmação de existência*, não descoberta.
3. Os "falsos negativos" do Bluesky (4) são **contas suspensas** (`AccountTakedown`) ou **desativadas** (DID resolve, perfil não): o oráculo `resolveHandle` diz "existe", o conector diz "não há
   perfil visível" — para o objetivo (perfil público visível), o conector está certo. Dois outros existentes ficaram **inconclusivos** (429).
4. 177 candidatas do Bluesky foram **excluídas** por erro do oráculo (rate limit); 1 no Mastodon.
5. Negativos fáceis: variantes quase nunca existem, e APIs distinguem bem. A diferença só aparece onde o **ingênuo** é enganado (SPA), e isso depende da plataforma.
6. Um único conector-SPA (Bluesky) foi testado em larga escala; X/Threads/Twitch passaram em validações **pequenas** (2 conhecidos + 6 negativos) — evidência fraca.


## 7. O que este bench derruba nas minhas afirmações anteriores

| Afirmação anterior | Status |
|---|---|
| "Precisão 100% no CRÍTICO" (bench sintético) | **Retirada.** Artefato do corpus e de regras escritas com visibilidade dele. Em dados reais a versão original tinha precisão ≲ 10% nos sinalizados |
| "Recall de aliases 24% @200" | **Qualificada:** vale só contra o atacante simulado. Em handles reais que contêm a marca: **2–3%** |
| "O ranking por afixos de golpe cobre o que importa" | **Sem suporte** nos dados reais de Bluesky/Mastodon |
| "Cálculo de confiança/priorização é explicável" | Mantida (cada alerta tem razões), mas **explicável ≠ correto** |
| Calibração de conectores | **Mantida** (validada ao vivo; ver R2) |

## 8. O que mediria de verdade (e que só você pode fornecer)

1. **Histórico real de takedowns** da sua marca (handles + prints/bios), com **dois revisores** e divergências registradas → `sosia eval` e `sosia fit-priors`.
2. Plataformas onde o problema ocorre (Instagram/Telegram/X/TikTok), com coleta autorizada e compatível com os Termos de cada uma.
3. Rodar `sosia discover` + `scan` em produção por semanas e **rotular os alertas** (verdadeiro/falso) para ter precisão de campo; sem positivos, só se mede carga.
4. Um conjunto pré-registrado de marcas, limiares fixados *antes* de ver os dados.

> **Nota de privacidade.** Este relatório não lista handles, nomes de exibição nem bios de terceiros. Contas citadas como "plausíveis" são **hipóteses de triagem**, não acusações: não consegui verificar vínculo com a marca.
