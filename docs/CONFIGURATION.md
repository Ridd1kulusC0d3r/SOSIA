# Guia de configuração do SÓSIA

Este guia explica **o que cada campo faz, por que preencher, quando deixar vazio e quais erros evitar**. Aplica-se aos dois notebooks Colab, ao frontend Gradio e, com diferenças indicadas, ao arquivo \`sosia.toml\`.

A marca de exemplo **Marca Zeta é fictícia**. Use marcas ou pessoas que você representa.

## Comece com estes cinco campos

| Campo | Obrigatório? | Exemplo | Como o motor utiliza |
|---|---|---|---|
| **BRAND** | Sim | \`Marca Zeta\` | Nome de referência da marca, menções na bio, relatório e pivôs para nomes de exibição |
| **HANDLE** | Sim no Colab | \`marcazeta\` | Username-base sem \`@\`; geração de typos, homóglifos, separadores, dígitos e variantes com afixos |
| **DOMAINS** | Opcional | \`marcazeta.com.br\` | Referências para classificar links de bios: oficial conhecido, suspeito de semelhança ou externo |
| **OFFICIAL** | Fortemente recomendado | \`marcazeta, marcazeta_sac\` | **Allowlist** de contas comprovadamente autorizadas; não entram na lista de suspeitos |
| **EXTRA_AFFIXES** | Opcional | \`clube, cartao\` | Vocabulário específico do setor para ampliar o espaço de variantes geradas |

## 1. BRAND: nome público da identidade protegida

**Exemplo:** \`Marca Zeta\`.

**Por que preencher?** Define qual organização, marca ou pessoa é analisada. O nome aparece nos relatórios, ajuda o motor a interpretar referências à marca em conteúdo público e alimenta pesquisas de nomes de exibição por \`sosia pivots\`.

**O que não colocar:** URL inteira, um perfil suspeito como identidade principal ou marca que você não representa.

**Se o nome não for igual ao username?** Normal. \`BRAND="Marca Zeta"\` e \`HANDLE="marcazeta"\` são campos complementares, não duplicados.

## 2. HANDLE: username-base usado para gerar variantes

**Exemplo:** \`marcazeta\`, sem arroba.

A partir desta base, o gerador pode produzir exemplos como:
- \`marcazeta_suporte\` (termo de atendimento, se gerado pelo léxico ou afixos);
- \`marcazeta.clube\` (separador + afixo, sujeito às famílias implementadas);
- \`marcazzeta\` (repetição);
- \`marcazeta01\` (sufixo numérico).

Os exemplos acima são **ilustrativos**, não uma promessa de que cada combinação estará entre os primeiros resultados. A plataforma pode restringir caracteres e tamanho.

**Por que preencher?** O sistema compara os candidatos com essa base e calcula semelhança, em vez de criar usernames a partir da grafia do nome de exibição.

**Se preencher errado:** você pode perder perfis parecidos ou gerar muitos falsos candidatos. Verifique no canal oficial da marca.

**No CLI com \`sosia.toml\`:** se \`handle\` não for definido, a configuração deriva uma base simplificada de \`name\`. No Colab atual, o campo HANDLE é explicitamente fornecido.

## 3. DOMAINS: referências de domínios oficiais

**Exemplo:** \`marcazeta.com.br\`.

**Formato válido:**
- Um domínio: \`marcazeta.com.br\`.
- Vários domínios no Colab: \`marcazeta.com.br, zetaoficial.com.br\`.
- Não use \`https://\`, \`www.\` ou \`/login\` se não fizerem parte do domínio registrável pretendido.

**Por que preencher?** Se uma bio incluir URLs, o SÓSIA utiliza os domínios conhecidos para diferenciar links direcionados ao domínio legítimo, domínios visualmente parecidos e links externos. Isso fornece **contexto de investigação**, não um veredito.

**Limite crucial:** qualquer perfil pode colocar um link para o site legítimo. **Um link para domínio oficial não prova que o perfil é autorizado.** Um vínculo mais robusto exigiria confirmação recíproca pelos canais oficiais.

**Se não tiver site oficial:** deixe vazio. Não invente um endereço.

## 4. OFFICIAL: allowlist de contas legítimas

**Exemplo do Colab:** \`marcazeta, marcazeta_sac\`.

**Por que preencher?** Para que a ferramenta não trate seus próprios perfis autorizados como candidatos de impersonação. Contas na allowlist são removidas da geração e reconhecidas como autorizadas na triagem.

**Cuidado com falso negativo:** **não adicione contas que apenas dizem ser oficiais.** A conta deve ter autorização confirmada pela organização. Uma allowlist errada pode esconder exatamente o risco que se deseja encontrar.

### Escopo global versus por plataforma

No formulário do Colab e do frontend, o campo aceita usernames separados por vírgulas e os registra em \`official={"*": {...}}\`. Isto significa **allowlist global em todas as plataformas**.

Caso \`marcazeta_sac\` seja oficial somente no Instagram, não é seguro afirmar que a mesma conta é oficial em outras plataformas. O arquivo \`sosia.toml\` permite mapear contas separadamente:

\`\`\`toml
[official]
"*" = ["marcazeta"]
instagram = ["marcazeta_sac"]
x = ["marcazeta_br"]
\`\`\`

**Recomendação:** use \`"*"\` só para usernames realmente autorizados em *todas* as plataformas que serão verificadas. Para operação com marcas reais, prefira a configuração por plataforma no \`sosia.toml\`.

## 5. EXTRA_AFFIXES: vocabulário adicional de candidatos

**Exemplo:** \`clube, cartao\`.

**Por que preencher?** Algumas marcas são imitados com palavras do seu negócio, por exemplo \`clube\`, \`beneficios\`, \`premios\`, \`ingressos\` e \`cartao\`. O gerador já possui famílias de mutação e um léxico padrão, mas os termos adicionais possibilitam variações específicas do seu setor.

**Como funciona:** cada termo passa a ser um elemento adicional do motor de variantes. Não é uma lista de contas autorizadas, não é uma palavra-chave que sozinho confirma golpe e **não significa que um perfil com o termo exista**.

**Cuidado com volume:** muitos afixos aumentam o número de candidatos e podem consumir o orçamento de consultas em plataformas. Use termos plausíveis para sua marca e acompanhe o resultado do benchmark.

**Quando deixar vazio:** se você ainda não conhece termos específicos do seu setor. O motor continuará com as famílias e afixos padrão.

## Exemplo equivalente em TOML

\`\`\`toml
[brand]
name = "Marca Zeta"
handle = "marcazeta"
display_names = ["Marca Zeta", "MarcaZeta Brasil"]
domains = ["marcazeta.com.br"]
extra_affixes = ["clube", "cartao"]

[official]
"*" = ["marcazeta"]
instagram = ["marcazeta_sac"]

[scan]
platforms = ["bluesky", "gitlab", "telegram"]
budget = 80
rate = 1.0
\`\`\`

Os campos \`display_names\`, \`platforms\`, \`budget\` e \`rate\` são configurações adicionais do modo TOML. Respectivamente, expandem nomes de exibição a pesquisar, escolhem conectores, limitam consultas por plataforma e espaçam requisições por host.

Para criar a estrutura inicial: \`sosia init\`. Edite o arquivo antes de \`sosia scan -c sosia.toml --out runs/minha-marca\`.

## Erros frequentes

| Erro | Consequência | Correção |
|---|---|---|
| HANDLE contém \`@\` | Entrada mal formatada ou geração inesperada | Informar \`marcazeta\` |
| DOMAIN contém \`https://\` ou caminho | Comparações de links incorretas | Informar somente \`marcazeta.com.br\` |
| OFFICIAL contém conta apenas suspeita | Possível falso negativo por allowlist | Só adicionar conta autenticada pela própria marca |
| Colab usa OFFICIAL global para uma conta exclusiva do Instagram | Pode ignorar homônimo em outra plataforma | Usar allowlist por plataforma via \`sosia.toml\` |
| EXTRA_AFFIXES contém dezenas de palavras genéricas | Explosão de candidatos e consumo do budget | Priorizar termos do setor; medir cobertura |
| Domínio da bio aponta para o site oficial | Falsa conclusão de vínculo legítimo | Conferir confirmação recíproca |
| Operador vê \`403\` e marca a conta como ausente | Falso negativo silencioso | Tratar como inconclusivo |

## Experimentos recomendados

1. Preencha a marca fictícia e rode a geração de variantes **offline**.
2. Remova temporariamente um afixo e compare a quantidade de candidatos.
3. Compare os sinais de bios "Aceitamos Pix" versus "Faça um Pix para desbloquear".
4. Confira que contas da allowlist não aparecem como candidatos.
5. Antes de consultar qualquer plataforma real, confirme a finalidade defensiva e os dados de autorização.

## Acessos rápidos

- [Colab principal (CLI + download seletivo)](../notebooks/sosia_colab.ipynb)
- [Segundo Colab com frontend](../notebooks/sosia_frontend_colab.ipynb)
- [Guia de exportações HTML/PDF](EXPORTS.md)
- [README](../README.md)

**Aviso:** os valores de Marca Zeta são fictícios. Os campos são entradas de investigação e não substituem evidência independente de identidade, vínculo ou abuso.
