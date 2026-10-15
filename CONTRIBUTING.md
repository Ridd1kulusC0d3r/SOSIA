# Contribuindo para o SÓSIA

Contribuições são bem-vindas quando tornam a detecção mais **reprodutível, segura e explicável**.

## Ambiente local

```bash
python -m pip install -e .
python -m unittest discover -s tests
```

O motor requer Python 3.11+ e não possui dependências de runtime externas.

## Requisitos mínimos de um PR

- **Conectores:** controles negativos e positivos, tratamento de soft-404 e respostas bloqueadas como inconclusivas.
- **Triagem:** exemplos com negações, perfis de fãs e diferenças entre menção e pedido de pagamento.
- **Bench:** seed, corpus e limitações explícitas; nunca anunciar resultado sintético como taxa real.
- **Visuais:** textos alternativos, contraste, responsividade e rótulos para mockups.
- **Privacidade:** usar entidades inventadas, nunca dados de clientes ou perfis pessoais de terceiros.

Roteiros e boas práticas de mídia: [docs/MEDIA_GUIDE.md](docs/MEDIA_GUIDE.md). Decisões técnicas: [docs/DESIGN.md](docs/DESIGN.md).