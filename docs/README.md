# Documentação

Esta pasta concentra a documentação técnica do **url-shortener**. O [README da raiz](../README.md)
é o ponto de entrada e um resumo; aqui está o detalhe. Documentação em **português**; código em
**inglês**.

## Documentos

| Documento | Para quê serve |
|---|---|
| [CHALLENGE.md](CHALLENGE.md) | O *brief* do desafio: contexto, requisitos, critérios de aceite, e o mapeamento do capítulo 8 do Alex Xu — o que foi mantido e o que foi tirado. **Comece por aqui.** |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitetura hexagonal, estrutura de pacotes, os contratos de dependência verificados por ferramenta, o modelo de execução síncrono, os dois fluxos em diagrama de sequência e o modelo de dados. |
| [API.md](API.md) | Referência do contrato HTTP: as quatro rotas, corpos de requisição e resposta, a taxonomia de erros (RFC 7807) e o *walkthrough* do fluxo com `curl`. |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Como rodar localmente com e sem Docker, comandos do `uv`, migrations, configuração, o pipeline de CI e onde achar cada coisa no código. |
| [TESTS.md](TESTS.md) | Estratégia de testes, a separação unitário/integração, Testcontainers, Object Mother, estilo de teste e os dois gates de cobertura. |
| [SECURITY.md](SECURITY.md) | A superfície de ataque de um encurtador, o que a política de destino recusa, as defesas da imagem e da configuração — e o que **não** está defendido. |
| [PROGRESS-V1.md](PROGRESS-V1.md) | O roadmap do escopo mínimo, fase a fase, com o registro do que foi de fato construído em cada uma. |
| [PROGRESS-V2.md](PROGRESS-V2.md) | O que ficou de fora de propósito, e em que ordem entraria se o projeto continuasse. |

## ADRs

Architecture Decision Records — o *porquê* de cada decisão estrutural.

| ADR | Tema |
|---|---|
| [0001](adr/0001-redirect-302.md) | O redirect é `302`, não `301` |
| [0002](adr/0002-base62-sobre-a-sequence.md) | Código gerado por base 62 sobre a sequence, não por hash da URL |
| [0003](adr/0003-sem-fila.md) | Sem fila, e o lugar exato onde ela entraria |
| [0004](adr/0004-fronteira-sem-objeto-de-dominio.md) | A fronteira da aplicação não carrega objeto de domínio |
| [0005](adr/0005-corpo-de-requisicao-sem-httpurl.md) | O corpo do `POST /links` carrega uma string, não um `HttpUrl` |
| [0006](adr/0006-envelope-de-erro-problem-details.md) | Todo erro da API sai no mesmo envelope Problem Details |
| [0007](adr/0007-fronteira-da-transacao.md) | A transação commita antes de a resposta ser enviada |
| [0008](adr/0008-health-responde-503-no-mesmo-envelope.md) | O `/health` responde `503` no mesmo envelope, e é o único `503` da API |
| [0009](adr/0009-migracao-e-passo-de-deploy.md) | A migração é um passo do deploy, não do startup da aplicação |

## Por onde começar

- Quero **entender o problema e o que foi cortado** -> [CHALLENGE.md](CHALLENGE.md)
- Quero **entender a arquitetura e os fluxos** -> [ARCHITECTURE.md](ARCHITECTURE.md)
- Quero **usar a API** (rotas, corpos, erros, exemplos) -> [API.md](API.md)
- Quero **rodar localmente** -> [DEVELOPMENT.md](DEVELOPMENT.md)
- Quero **escrever ou rodar testes** -> [TESTS.md](TESTS.md)
- Quero **saber o que é recusado e o que não é defendido** -> [SECURITY.md](SECURITY.md)
- Quero **o porquê das decisões** -> [ADRs](#adrs)
- Quero **acompanhar o progresso** -> [PROGRESS-V1.md](PROGRESS-V1.md) · [PROGRESS-V2.md](PROGRESS-V2.md)

## Convenções de manutenção

- **Mermaid sempre que possível** — diagramas viram código versionável e revisável em diff.
- **Tabelas em vez de prosa** ao enumerar rotas, colunas, comandos, status ou erros.
- **Linkar entre docs** quando um conceito aparece em mais de um lugar, em vez de duplicar. Cada
  documento declara o próprio escopo na abertura e entrega o resto por link.
- **Um ADR antes de mudar uma decisão estrutural** — nunca em silêncio. Ao substituir uma decisão,
  datar o status do ADR antigo em vez de reescrevê-lo.
- **Nenhuma afirmação sem verificação.** Este repositório já derrubou frases falsas da própria
  documentação em revisão adversarial mais de uma vez; um número ou um comportamento citado aqui
  tem que ter sido medido, não lembrado.
- **Documentação em português; código em inglês** — identificadores, nomes de arquivo, colunas e
  comandos aparecem exatamente como estão no código, sem tradução.
- **`ruff format` também processa Markdown** e roda no CI, então um bloco de código Python mal
  formatado dentro de um documento reprova o pipeline.
