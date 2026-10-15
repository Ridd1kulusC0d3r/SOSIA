# Validação ao vivo dos conectores

**Data:** 2026-10-15 · **Ambiente:** sandbox em nuvem com proxy de saída (um único IP/região) · **Comando:** `sosia calibrate --validate --rate 0.7`
Saída bruta em [`live_validation_raw.txt`](live_validation_raw.txt).

Cada conector recebe 3 negativos aleatórios válidos + 1 controle positivo (calibração) e, com `--validate`, mais **≥2 perfis conhecidos e 6 negativos novos**.

| conector | estado | validação | observação |
|---|---|---|---|
| GitLab | trusted | 2/2 · 6/6 ✅ | |
| Bluesky | trusted | 2/2 · 6/6 ✅ | API pública; bio, seguidores, data de criação |
| Mastodon (mastodon.social) | trusted | 2/2 · 6/6 ✅ | `note` em HTML é limpo |
| DEV Community | trusted | 2/2 · 6/6 ✅ | |
| Telegram | trusted | 3/3 · 6/6 ✅ | bio genérica ignorada (placeholder) |
| YouTube | trusted | 2/2 · 6/6 ✅ | corpo >2 MB; metatags lidas |
| TikTok | trusted | 2/2 · 6/6 ✅ | |
| Linktree | trusted | 2/2 · 6/6 ✅ | |
| X | trusted | 2/2 · 6/6 ✅ | surpreendente (esperava shell de SPA); **depende de IP/região** |
| Twitch | differential | 2/2 · 6/6 ✅ | só usável porque passou na validação |
| Threads | differential | 2/2 · 6/6 ✅ | idem |
| Instagram | unstable | — | 2/3 negativos "existem" ⇒ inconclusivo (correto). Numa execução anterior o diferencial **reprovou** (0/2) — origem da regra "diferencial só com validação" |
| Pinterest | soft404 | — | descartado: tudo "existe", sem como distinguir |
| Facebook | soft404 | — | descartado |
| GitHub | blocked | — | 403 **do proxy do sandbox** (rotas fora do repositório da sessão); não valida o conector — rode no seu ambiente |
| Reddit | blocked | — | 403 (reputação de IP) |
| Medium | blocked | — | 403 (WAF) |

## Leitura honesta

- É **uma execução, um IP, 8 consultas por conector**: evidência fraca. Serve para achar bugs (achou vários — ver `DESIGN.md §5`), não para certificar.
- Resultados mudam com IP, região, horário e user-agent. **Reexecute no seu ambiente** antes de confiar em qualquer plataforma.
- Por isso nenhum conector tem `verified_on` preenchido no `platforms.json`.

## Varredura real de fumaça

`sosia scan` com 9 conectores `trusted`, orçamento 40/plataforma, para o handle do próprio autor: 429 requisições, 0 achados, 0 inconclusivos,
pacote de evidências gerado (manifesto SHA-256 verificado por teste). Leitura de bio verificada ao vivo em Telegram, Bluesky, DEV, Mastodon e YouTube
com contas públicas de organizações (via `--watch`).
