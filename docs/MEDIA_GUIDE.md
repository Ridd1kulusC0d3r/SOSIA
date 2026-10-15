# Guia de mídia: GIFs, vídeos e demonstrações

Este guia define como mostrar o SÓSIA **sem confundir arte conceitual com evidência de uma execução real**.

## Assets disponíveis

| Mídia | Uso | Tipo |
|---|---|---|
| [Capa SVG](../assets/brand-hero.svg) | Cabeçalho do README | Identidade visual original |
| [Fluxo SVG](../assets/pipeline.svg) | Explicação técnica | Diagrama conceitual |
| [Painel SVG](../assets/triage-dashboard.svg) | Prévia de produto | Mockup, não interface funcional |
| [Tour GIF](../assets/sosia-tour.gif) | Seis quadros do pipeline | Animação ilustrativa, não gravação |
| [Laboratório HTML](demo/index.html) | Exemplos em formato interativo | Simulação offline, sem backend |

## Roteiro de vídeo 1: demonstração real da CLI

**Estado:** roteiro proposto; vídeo ainda não gravado. Grave apenas terminal e exemplos artificiais, sem dados pessoais.

| Cena | Comando ou tela | Explicação |
|---|---|---|
| 1 | `sosia --version` | Identifique a versão exibida |
| 2 | `sosia variants "Marca Zeta" --handle marcazeta --limit 12` | Gerar candidatos não significa confirmar a existência |
| 3 | `sosia triage "Marca Zeta" --handle marcazeta --username marcazeta_fas --text "Perfil de fãs. Não oficial. Memes."` | Disclaimers e negações reduzem suspeitas precipitadas |
| 4 | `sosia triage "Marca Zeta" --handle marcazeta --username marcazeta_suporte01 --text "Suporte oficial Marca Zeta. Faça o Pix da taxa de liberação."` | Grupos de sinais indicam o que investigar |
| 5 | Abrir `docs/BENCH_RESULTS.md` | Benchmarks sintéticos não medem detecção de campo |
| 6 | Encerrar no fluxo de calibração | Evidência, incerteza e decisão humana |

Com ferramentas **opcionais** de gravação [asciinema](https://asciinema.org/) e [agg](https://github.com/asciinema/agg):

```bash
asciinema rec demo.cast
# Execute os comandos offline, termine a gravação
agg --theme monokai --font-size 18 demo.cast demo-terminal.gif
```

Se houver FFmpeg instalado, converta um GIF gravado em vídeo:

```bash
ffmpeg -i demo-terminal.gif \
  -vf "fps=24,scale=960:-2:flags=lanczos,format=yuv420p" \
  -movflags +faststart demo-terminal.mp4
```

**Não atribua ao SÓSIA saídas geradas por outra ferramenta.** Revise o vídeo, indique commit/versão e mantenha os comandos legíveis.

## Roteiro de vídeo 2: tour visual de produto

Abra `docs/demo/index.html` por servidor local e clique em **Reproduzir tour**. Ao gravar, mantenha visível a legenda "SIMULAÇÃO LOCAL, SEM REDE". O painel representa uma ideia de UI futura; não existe integração de frontend com o motor na versão atual.

## Diretrizes editoriais

- Vídeos 16:9, com legendas legíveis; GIFs curtos com texto alternativo.
- Não publicar exemplos com clientes, telefones, URLs pessoais ou capturas de usuários reais.
- Distinguir sempre **mockup**, **teste sintético**, **validação pontual** e **execução real**.
- Para o produto real, incluir logs de versão, comando e reprodutibilidade.
- Não usar gifs hospedados em links de terceiros desconhecidos; guardar assets próprios em `assets/`.

O GIF presente no README é uma **animação original criada para o fluxo**, não uma gravação da CLI. Para uma gravação autêntica, siga os passos acima.
