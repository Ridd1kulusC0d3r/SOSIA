# SÓSIA Bench — resultados (SINTÉTICOS)

> **Isto é um harness de regressão com verdade-terreno simulada.** Os números mostram como o motor se comporta frente a modos de falha conhecidos (soft-404, shell de SPA, login wall, rate limit, CAPTCHA, drift) e a um atacante simulado independente do gerador. **Não são taxas de detecção do mundo real**, e os baselines são reimplementações mínimas da lógica *documentada* de Sherlock/dnstwist/Maigret — essas ferramentas não foram executadas.

seed `7` · marcas: 10 (dev 4 / test 6) · aliases: 600

## 1. Geração de candidatos — recall de aliases por orçamento de consultas

Aliases vêm de um atacante simulado independente (mutações aleatórias, afixos dentro e **fora** do léxico, handles sem relação com a marca). `unrelated` é o teto: enumeração nunca os encontra.

| grupo | estratégia | @25 | @50 | @100 | @200 | @400 | @800 | lista inteira |
|---|---|---|---|---|---|---|---|---|
| all_discoverable | sherlock_like | 2.6% | 2.6% | 2.6% | 2.6% | 2.6% | 2.6% | 2.6% |
| all_discoverable | dnstwist_like | 8.9% | 13.8% | 14.8% | 14.8% | 14.8% | 14.8% | 14.8% |
| all_discoverable | sosia_random_order | 0.8% | 1.4% | 3.0% | 5.1% | 11.3% | 19.2% | 38.3% |
| all_discoverable | sosia | 8.7% | 13.4% | 16.0% | 24.1% | 30.2% | 37.9% | 38.3% |
| cls:typo | sherlock_like | 10.0% | 10.0% | 10.0% | 10.0% | 10.0% | 10.0% | 10.0% |
| cls:typo | dnstwist_like | 34.6% | 53.8% | 57.7% | 57.7% | 57.7% | 57.7% | 57.7% |
| cls:typo | sosia_random_order | 0.0% | 0.8% | 1.5% | 4.6% | 16.2% | 29.2% | 57.7% |
| cls:typo | sosia | 33.8% | 52.3% | 56.2% | 56.9% | 57.7% | 57.7% | 57.7% |
| cls:affix_in | sherlock_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cls:affix_in | dnstwist_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cls:affix_in | sosia_random_order | 2.6% | 3.2% | 7.7% | 12.2% | 22.4% | 35.3% | 72.4% |
| cls:affix_in | sosia | 0.0% | 0.0% | 5.1% | 30.1% | 49.4% | 72.4% | 72.4% |
| cls:affix_out | sherlock_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cls:affix_out | dnstwist_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cls:affix_out | sosia_random_order | 0.0% | 0.6% | 0.6% | 0.6% | 0.6% | 1.3% | 1.3% |
| cls:affix_out | sosia | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 1.3% | 1.3% |
| cls:combo | sherlock_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cls:combo | dnstwist_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cls:combo | sosia_random_order | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 3.0% | 6.1% |
| cls:combo | sosia | 0.0% | 0.0% | 0.0% | 1.5% | 1.5% | 3.0% | 6.1% |
| split:test | sherlock_like | 2.2% | 2.2% | 2.2% | 2.2% | 2.2% | 2.2% | 2.2% |
| split:test | dnstwist_like | 7.5% | 10.0% | 11.4% | 11.4% | 11.4% | 11.4% | 11.4% |
| split:test | sosia_random_order | 0.3% | 0.6% | 2.2% | 4.2% | 9.7% | 16.9% | 30.8% |
| split:test | sosia | 7.2% | 10.0% | 11.9% | 18.9% | 23.9% | 30.6% | 30.8% |
| unrelated | sherlock_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| unrelated | dnstwist_like | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| unrelated | sosia_random_order | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| unrelated | sosia | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

Tamanho médio da lista: `sherlock_like` 20.1, `dnstwist_like` 133.8, `sosia_random_order` 1443.7, `sosia` 1443.7.
`cls:affix_in` usa afixos que também estão no léxico do motor (parcialmente circular); `cls:affix_out` mede generalização.

## 2. Confirmação de existência — por comportamento de plataforma

Orçamento 160/plataforma (inclui watchlist de aliases). `FP` = marcado como existente sem existir; `FN` = existia e foi dado como ausente **sem aviso**; `INC` = existia e ficou inconclusivo (visível, com motivo).

| plataforma (comportamento) | estratégia | TP | **FP** | **FN silencioso** | INC | precisão | recall | requisições |
|---|---|---|---|---|---|---|---|---|
| cleana (clean) | naive_status | 268 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| cleana (clean) | configured_check | 268 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| cleana (clean) | sosia | 268 | 0 | 0 | 0 | 100.0% | 100.0% | 1750 |
| cleanb (clean) | naive_status | 276 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| cleanb (clean) | configured_check | 276 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| cleanb (clean) | sosia | 276 | 0 | 0 | 0 | 100.0% | 100.0% | 1750 |
| apijson (api_json) | naive_status | 265 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| apijson (api_json) | configured_check | 265 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| apijson (api_json) | sosia | 265 | 0 | 0 | 0 | 100.0% | 100.0% | 1750 |
| softpos (soft404) | naive_status | 301 | 1299 | 0 | 0 | 18.8% | 100.0% | 1600 |
| softpos (soft404) | configured_check | 301 | 1299 | 0 | 0 | 18.8% | 100.0% | 1600 |
| softpos (soft404) | sosia | 301 | 0 | 0 | 0 | 100.0% | 100.0% | 1830 |
| softnopos (soft404) | naive_status | 276 | 1324 | 0 | 0 | 17.2% | 100.0% | 1600 |
| softnopos (soft404) | configured_check | 276 | 1324 | 0 | 0 | 17.2% | 100.0% | 1600 |
| softnopos (soft404) | sosia | 0 | 0 | 0 | 276 | —% | 0.0% | 30 |
| softmsg (soft404_msg) | naive_status | 259 | 1341 | 0 | 0 | 16.2% | 100.0% | 1600 |
| softmsg (soft404_msg) | configured_check | 259 | 0 | 0 | 0 | 100.0% | 100.0% | 1600 |
| softmsg (soft404_msg) | sosia | 259 | 0 | 0 | 0 | 100.0% | 100.0% | 1750 |
| spashell (spa_shell) | naive_status | 264 | 1336 | 0 | 0 | 16.5% | 100.0% | 1600 |
| spashell (spa_shell) | configured_check | 264 | 1336 | 0 | 0 | 16.5% | 100.0% | 1600 |
| spashell (spa_shell) | sosia | 0 | 0 | 0 | 264 | —% | 0.0% | 40 |
| loginwall (login_wall) | naive_status | 286 | 1314 | 0 | 0 | 17.9% | 100.0% | 1600 |
| loginwall (login_wall) | configured_check | 286 | 1314 | 0 | 0 | 17.9% | 100.0% | 1600 |
| loginwall (login_wall) | sosia | 0 | 0 | 0 | 286 | —% | 0.0% | 40 |
| ratelimit (ratelimit) | naive_status | 97 | 0 | 205 | 0 | 100.0% | 32.1% | 1600 |
| ratelimit (ratelimit) | configured_check | 97 | 0 | 205 | 0 | 100.0% | 32.1% | 1600 |
| ratelimit (ratelimit) | sosia | 85 | 0 | 0 | 217 | 100.0% | 28.1% | 480 |
| captcha (captcha) | naive_status | 269 | 988 | 0 | 0 | 21.4% | 100.0% | 1600 |
| captcha (captcha) | configured_check | 57 | 0 | 212 | 0 | 100.0% | 21.2% | 1600 |
| captcha (captcha) | sosia | 57 | 0 | 0 | 212 | 100.0% | 21.2% | 430 |
| flaky (flaky) | naive_status | 270 | 0 | 17 | 0 | 100.0% | 94.1% | 1600 |
| flaky (flaky) | configured_check | 270 | 0 | 17 | 0 | 100.0% | 94.1% | 1600 |
| flaky (flaky) | sosia | 287 | 0 | 0 | 0 | 100.0% | 100.0% | 2350 |
| drift (drift) | naive_status | 289 | 696 | 0 | 0 | 29.3% | 100.0% | 1600 |
| drift (drift) | configured_check | 289 | 696 | 0 | 0 | 29.3% | 100.0% | 1600 |
| drift (drift) | sosia | 289 | 0 | 0 | 0 | 100.0% | 100.0% | 2120 |

**Agregado (todas as plataformas e marcas):**

| estratégia | TP | FP | FN silencioso | INC (existentes) | precisão | recall estrito | cobertura (recall + INC) | requisições |
|---|---|---|---|---|---|---|---|---|
| naive_status | 3120 | 8298 | 222 | 0 | 27.3% | 93.4% | 93.4% | 19200 |
| configured_check | 2908 | 5969 | 434 | 0 | 32.8% | 87.0% | 87.0% | 19200 |
| sosia | 2087 | 0 | 0 | 1255 | 100.0% | 62.4% | 100.0% | 14320 |

Estado final dos conectores no SÓSIA (contagem de execuções): `cleana`: trusted×10; `cleanb`: trusted×10; `apijson`: trusted×10; `softpos`: differential×10; `softnopos`: soft404×10; `softmsg`: trusted×10; `spashell`: soft404×10; `loginwall`: soft404×10; `ratelimit`: degraded×10; `captcha`: degraded×10; `flaky`: trusted×10; `drift`: differential×10

## 3. Triagem de abuso

Aliases existentes (exceto `unrelated`, que a enumeração não acha). Verdade: `scam` = golpe; `nonscam` = impersonação sem golpe; `fan`, `benign`, `reseller` (revenda legítima que "aceita Pix") = não acionáveis. 12% das bios vazias. Templates de bio de **teste** diferem dos de **dev**, e o teste inclui 4 golpes *fora do léxico*.

> ⚠️ **Contaminação declarada:** as regras de léxico/negação/"aceitamos Pix" foram escritas pelo mesmo autor do corpus sintético, com visibilidade dos templates (inclusive os de teste). Os números do SÓSIA aqui são **otimistas**: demonstram o *mecanismo* (negação, allowlist, evidência em grupos, disclaimers) contra um gatilho por palavra-chave, não a precisão esperada em campo. Para medir de verdade: `sosia eval` com perfis reais rotulados por revisores independentes.

### CRÍTICO vs golpe

| split | estratégia | TP | FP | FN | precisão | recall | F1 | acurácia | acurácia de "tudo negativo" | FPs por papel |
|---|---|---|---|---|---|---|---|---|---|---|
| dev | handle_only | 16 | 27 | 71 | 37.2% | 18.4% | 24.6% | 52.9% | 79.3% | {'fan': 12, 'benign': 6, 'reseller': 6, 'nonscam': 3} |
| dev | bio_keyword_v1.1 | 87 | 67 | 0 | 56.5% | 100.0% | 72.2% | 67.8% | 26.0% | {'benign': 15, 'nonscam': 20, 'reseller': 18, 'fan': 14} |
| dev | sosia_multisignal | 66 | 0 | 21 | 100.0% | 75.9% | 86.3% | 89.9% | 68.3% | — |
| test | handle_only | 17 | 42 | 83 | 28.8% | 17.0% | 21.4% | 58.1% | 80.2% | {'reseller': 9, 'benign': 15, 'nonscam': 5, 'fan': 13} |
| test | bio_keyword_v1.1 | 100 | 94 | 0 | 51.5% | 100.0% | 68.0% | 68.5% | 34.9% | {'reseller': 35, 'nonscam': 17, 'fan': 24, 'benign': 18} |
| test | sosia_multisignal | 42 | 0 | 58 | 100.0% | 42.0% | 59.2% | 80.5% | 85.9% | — |
| all | handle_only | 33 | 69 | 154 | 32.4% | 17.6% | 22.8% | 55.9% | 79.8% | {'fan': 25, 'benign': 21, 'reseller': 15, 'nonscam': 8} |
| all | bio_keyword_v1.1 | 187 | 161 | 0 | 53.7% | 100.0% | 69.9% | 68.2% | 31.2% | {'benign': 33, 'nonscam': 37, 'reseller': 53, 'fan': 38} |
| all | sosia_multisignal | 108 | 0 | 79 | 100.0% | 57.8% | 73.2% | 84.4% | 78.7% | — |

### ≥ALTO vs (golpe ∪ impersonação)

| split | estratégia | TP | FP | FN | precisão | recall | F1 | acurácia | acurácia de "tudo negativo" | FPs por papel |
|---|---|---|---|---|---|---|---|---|---|---|
| dev | handle_only | 95 | 89 | 13 | 51.6% | 88.0% | 65.1% | 51.0% | 11.5% | {'benign': 30, 'fan': 36, 'reseller': 23} |
| dev | bio_keyword_v1.1 | 108 | 93 | 0 | 53.7% | 100.0% | 69.9% | 55.3% | 3.4% | {'benign': 32, 'fan': 38, 'reseller': 23} |
| dev | sosia_multisignal | 92 | 0 | 16 | 100.0% | 85.2% | 92.0% | 92.3% | 55.8% | — |
| test | handle_only | 113 | 147 | 21 | 43.5% | 84.3% | 57.4% | 43.6% | 12.8% | {'reseller': 39, 'benign': 46, 'fan': 62} |
| test | bio_keyword_v1.1 | 131 | 154 | 3 | 46.0% | 97.8% | 62.5% | 47.3% | 4.4% | {'reseller': 42, 'benign': 49, 'fan': 63} |
| test | sosia_multisignal | 102 | 0 | 32 | 100.0% | 76.1% | 86.4% | 89.3% | 65.8% | — |
| all | handle_only | 208 | 236 | 34 | 46.8% | 86.0% | 60.6% | 46.6% | 12.3% | {'benign': 76, 'fan': 98, 'reseller': 62} |
| all | bio_keyword_v1.1 | 239 | 247 | 3 | 49.2% | 98.8% | 65.7% | 50.6% | 4.0% | {'benign': 81, 'fan': 101, 'reseller': 65} |
| all | sosia_multisignal | 194 | 0 | 48 | 100.0% | 80.2% | 89.0% | 90.5% | 61.7% | — |

### Matriz de confusão do SÓSIA (papel verdadeiro × prioridade) — split test

| papel | CRITICO | ALTO | MEDIO | BAIXO | INFO |
|---|---|---|---|---|---|
| benign | 0 | 0 | 29 | 25 | 1 |
| fan | 0 | 0 | 32 | 35 | 0 |
| nonscam | 0 | 17 | 17 | 0 | 0 |
| reseller | 0 | 0 | 42 | 0 | 0 |
| scam | 42 | 43 | 15 | 0 | 0 |

> Acurácia isolada engana: com maioria de perfis não acionáveis, um classificador que nunca alerta já tem a acurácia da coluna "tudo negativo" e detecta zero golpes. Use precisão/recall por classe.
