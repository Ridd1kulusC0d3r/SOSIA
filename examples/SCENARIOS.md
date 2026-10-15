# Exemplos investigativos do SÓSIA

**Todos os perfis e nomes são fictícios.** A marca "Marca Zeta" foi criada para treinamento e os comandos abaixo não fazem consultas externas.

## Preparar

```bash
python -m pip install -e .
sosia variants "Marca Zeta" --handle marcazeta --limit 12
```

## Caso 1: falsa central de suporte

- **Perfil fictício:** `@marcazeta_suporte01`
- **Bio:** "Suporte oficial Marca Zeta. Chame no WhatsApp e faça o Pix da taxa de liberação."
- **Pistas:** nome semelhante, alegação de oficialidade e solicitação de pagamento.
- **Perguntas:** a conta realmente existe? Há vínculo recíproco com os canais oficiais? A bio está atualizada?

```bash
sosia triage "Marca Zeta" --handle marcazeta \
 --username marcazeta_suporte01 \
 --text "Suporte oficial Marca Zeta. Chame no WhatsApp e faça o Pix da taxa de liberação."
```

A saída de `triage` é **análise textual offline**, não confirmação de perfil. Um caso só pode ser considerado CRÍTICO pelo fluxo completo se satisfizer as demais condições do motor.

## Caso 2: perfil de fãs

- **Perfil fictício:** `@marcazeta_fas`
- **Bio:** "Perfil de fãs. Não oficial. Memes."
- **Lição:** o aviso de não oficialidade é mitigador; handle semelhante não é prova de abuso.

```bash
sosia triage "Marca Zeta" --handle marcazeta \
 --username marcazeta_fas --text "Perfil de fãs. Não oficial. Memes."
```

## Caso 3: revenda legítima presumida

- **Perfil fictício:** `@marcazeta_revenda`
- **Bio:** "Revenda autorizada. Aceitamos Pix e cartão. Atendimento via WhatsApp."
- **Lição:** aceitar pagamento não é o mesmo que solicitá-lo como condição de liberação. Também não se pode tomar "autorizada" como comprovação de vínculo.

```bash
sosia triage "Marca Zeta" --handle marcazeta \
 --username marcazeta_revenda \
 --text "Revenda autorizada. Aceitamos Pix e cartão. Atendimento via WhatsApp."
```

## Caso 4: resposta de rede inconclusiva

Cenário **hipotético**. Se a plataforma retornar HTTP 200 para o candidato *e para nomes aleatórios inexistentes*, poderá ser soft-404. Se responder com 403, 429 ou CAPTCHA, não há base para afirmar que o perfil não existe.

| Resultado | Conduta |
|---|---|
| HTTP 200 indiscriminado | Testar negativos e controle positivo |
| Corpo diferencial | Exigir validação independente do conector |
| 403 / 429 / CAPTCHA | Registrar **inconclusivo**, com motivo |
| Drift durante varredura | Canário e recalibração |

## Da descoberta ao relatório

Para uma **marca que você está autorizado a proteger**, configure `sosia.toml`, execute `sosia calibrate --validate` em seu ambiente e depois `sosia scan -c sosia.toml --out runs/minha-marca`. Revise `case.json`, `report.md` e `MANIFEST.sha256` antes de encaminhar qualquer achado.

Mesmo que duas contas compartilhem avatar, domínio ou telefone, essa coincidência não comprova autoria comum.

[Decisões de design](../docs/DESIGN.md) · [Benchmarks](../docs/BENCH_RESULTS.md) · [Tour interativo](../docs/demo/index.html)
