# Decisões de design — e o que o bench derrubou

Este arquivo registra **o que foi decidido e por quê**, incluindo os erros do próprio motor que o `sosia bench` e a validação ao vivo expuseram
durante a construção. Se algo aqui parecer "feio", é de propósito: é o rastro de auditoria.

## 1. Calibração de conector (`calibrate.py`)

Pedido original: *"testa cada plataforma com um nome impossível e descarta a que responde 'existe' para tudo"*.

Problemas dessa formulação (e correções):

| problema | correção |
|---|---|
| um nome "impossível" pode ser **inválido** na plataforma e cair em outra rota do servidor | nomes aleatórios **sintaticamente válidos** (regra de username da plataforma), 3 por calibração |
| um único negativo não distingue "responde existe para tudo" de ruído | 3 negativos; 1–2 "existe" → `unstable` (repete 1× antes de desistir) |
| só olhar negativos não prova que o conector enxerga perfis reais | **controle positivo** conhecido; negativos ausentes + positivo ausente = `blind` |
| descartar soft-404 desperdiça plataformas utilizáveis | **modo diferencial**: negativos com corpo estável (Jaccard de shingles ≥0,85) e positivo distinto (<0,75) ⇒ classifica por impressão digital |
| o diferencial pode enganar | achado ao vivo: **Instagram passou na calibração diferencial e reprovou na validação (0/2 conhecidos)**. Regra: diferencial só vale se passar em `validate` (≥2 perfis conhecidos + 6 negativos novos); sem perfis conhecidos ⇒ `unvalidated` |
| a plataforma muda no meio da varredura | **canário** a cada N consultas (negativo novo; alternando com positivo) + guarda de razão de "encontrados" (>50% após 12 consultas força canário). Falhou ⇒ recalibra, reprocessa o período suspeito; não recuperou ⇒ `degraded` e o pendente vira inconclusivo |
| 503 transitório derrubava o conector inteiro | retry em erro de rede e 502/503/504 (na sonda e na calibração) |

## 2. Bloqueio nunca é ausência (`checks.py`)

Herdado do guia do Maigret: rate limit, CAPTCHA e desafios pertencem a `errors` → resultado **desconhecido**, não "não encontrado".
Marcadores de bloqueio só valem se o corpo **não** satisfizer a evidência positiva do conector (um perfil que menciona "captcha" na bio não é
bloqueio). Sequência de 3 bloqueios seguidos abre o circuit breaker da plataforma.

## 3. Ranking de variantes (`variants.py`) — três versões, duas erradas

1. **v1: prior por candidato × similaridade.** O bench mostrou **starvation**: com orçamento de 50, o gerador "tipo-dnstwist" achava 55% dos typos e o SÓSIA **1,5%** — afixos (prior 0,95) ocupavam todo o topo.
2. **v2: penalização geométrica dentro da família (MMR).** Melhorou, mas ainda comparava probabilidade *por candidato* entre famílias de tamanhos muito diferentes (9 omissões vs 80 afixos).
3. **v3 (atual): massa de probabilidade por família** (`lexicon.FAMILY_MASS`) dividida entre os membros pelo peso de similaridade. Famílias pequenas não são soterradas; typos empatam com o gerador tipo-dnstwist e os afixos entram em seguida.

**Ressalva:** as massas são uma hipótese do autor; o atacante simulado do bench tem proporções parecidas, então o ranking v3 está **parcialmente
circular** no bench. A saída honesta é `sosia fit-priors` com aliases reais conhecidos.

Adicionado depois de ver a lacuna no bench de desenvolvimento: afixo + cauda numérica (`marca_suporte01`) — hábito comum em golpes, mas o atacante
simulado também o usa, então o ganho de recall em `affix_in` é parcialmente circular.

## 4. Leitura de bio (`signals.py`, `scoring.py`)

- **Negação** em janela de 40 caracteres: "nunca pedimos senha ou Pix" vira *aviso de segurança* (mitigador), não evidência.
- **"Aceitamos Pix e cartão"** ≠ pedido de Pix: regra adicionada após o bench mostrar revenda legítima sendo promovida a CRÍTICO.
- **Ofuscação leet** só dentro de palavras mistas (`p1x` → `pix`), sem estragar números soltos.
- **Grupos independentes**: `strong` exige ≥2 grupos de risco (com ao menos um "duro") ou grupo duro + alegação de identidade. Uma palavra isolada nunca basta.
- **CRÍTICO** (ver README) exige existência ≥0,80 de confiança do conector ⇒ o modo diferencial (0,65) nunca promove sozinho.
- **Homônimo**: handle muito parecido com bio *sem relação com a marca* cai para BAIXO (achado do bench: antes ficava em MÉDIO e poluía a fila).
- Link para domínio oficial é só "alegação não verificada": qualquer um pode linkar; prova de vínculo exige link recíproco.
- Anotação de **alavancas psicológicas** (autoridade, urgência, escassez, recompensa, medo, prova social, isolamento, comprometimento) por sinal, para
  apoiar a investigação e o texto do relatório.

## 5. Bugs reais encontrados pela validação ao vivo

| achado | correção |
|---|---|
| YouTube serve >512 KB antes das metatags `og:*` | limite de corpo 3 MB; não cortar o parse em `</head>` (a string aparece dentro de scripts inline) |
| Telegram devolve "You can contact @x right away." como `og:description` de quem não tem bio | `bio.placeholders` por plataforma: texto genérico não conta como bio |
| Telegram: `tgme_page_title` presente só em perfis reais; ausente tem `tgme_page_icon` | marcadores positivo **e** negativo no conector |
| Twitch: endpoint `passport.twitch.tv/usernames` retornou 404 vazio | conector reescrito (`www.twitch.tv`, SPA); a calibração o trata como diferencial *validado* |
| GitLab: `gitlab-org` é grupo, não usuário (controle positivo errado) | `dzaporozhets`; a calibração acusou `blind` — o mecanismo funcionou |
| controles "conhecidos" errados (`devteam`, `bsky`) | corrigidos; a validação acusou |

## 6. O que o bench é — e não é

Ver `docs/BENCH_RESULTS.md` (gerado) e README. Em uma frase: **harness de regressão com verdade-terreno simulada**, que prova que o motor não
cai em modos de falha conhecidos e deixa explícito o teto de cada técnica; não prova taxa de detecção em campo. Separação dev/test é por **marca e
por template de bio** (não por gerador de atacante, que é compartilhado). Nenhuma calibração foi feita *com* os resultados de teste, mas o autor
conhecia os templates ao escrever as regras (contaminação declarada). Para a prova real: `sosia eval` com perfis reais, dois revisores, divergências registradas.

## 7. Watch (`watch.py`)

Compara execuções e emite `new_profile`, `escalated`/`deescalated`, `profile_changed` (nome, bio, links), `profile_gone` e `connector_change`.
Decisões: (1) **queda de cobertura é evento** — `trusted→blocked` alerta, porque "nenhum achado" deixaria de significar "nenhum perfil";
(2) com **zero conectores utilizáveis o estado não é atualizado**, evitando um falso "perfil removido" na rodada seguinte;
(3) `latest.json` é gravado de forma atômica; histórico e `alerts.jsonl` ficam no diretório de estado;
(4) `profile_gone` é ambíguo (takedown bem-sucedido *ou* falha de leitura): interprete junto de `connector_change`.
Limite: ainda não compara avatar/logo (pHash exigiria decodificar imagens; fora do escopo "zero dependências").

## 8. Não-objetivos

Contornar login/CAPTCHA/WAF, rotação de IP/UA, scraping autenticado, coleta em massa de pessoas, automação de denúncia sem revisão humana.


## 9. O que o bench real derrubou (2026-10-17)

Detalhes e números em [`REAL_BENCH.md`](REAL_BENCH.md). Resumo das decisões que mudaram:

- **Abuso forte sem relação com a marca não é alerta** (era ALTO em 486/504 casos reais). Agora BAIXO, com razão explícita.
- **`lookalike_link` deixou de ser evidência dura**; `sibling_tld` (mesmo rótulo, outro TLD) é neutro.
- **"Oficial/atendimento" sem abuso ⇒ MÉDIO** (era ALTO; ~25/26 eram entidades legítimas).
- **Semelhança de handle sozinha ⇒ BAIXO** (lista, não fila); MÉDIO exige algo específico (alegação, desvio de canal, confundível visual).
- **Menção à marca na bio é contexto, não identidade**: ALTO por abuso moderado exige semelhança ≥ 0,7; CRÍTICO ≥ 0,6.
- **Descoberta por busca (`sosia discover`)** passa a ser o caminho principal para *listar* candidatas; a enumeração fica para checagem direta e confundíveis.
- Preço: no bench sintético, recall de CRÍTICO 42% → 31%. Sem positivos reais, não sei qual lado do trade-off é o certo.

**Lição de processo.** Cada correção foi ditada pelo conjunto de dados que a expôs, então aquele conjunto deixa de ser teste. Por isso há 5 conjuntos
disjuntos, e só o último (#4, regras congeladas) é limpo. Mesmo ele só mede *carga de alertas*, não detecção.
