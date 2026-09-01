# Desafio — url-shortener

Serviço HTTP que recebe uma URL longa, devolve um código curto de sete caracteres e redireciona
esse código de volta ao destino, registrando cada acesso. Back-end puro, sem front-end: a interface
é a documentação interativa que o próprio FastAPI gera. Projeto de estudo e portfólio, desenhado
para ser **defendido decisão por decisão** numa entrevista técnica.

> Este documento é o **brief** do desafio (o *quê*). O *como* está nos docs vivos: arquitetura e
> fluxos em [`ARCHITECTURE.md`](ARCHITECTURE.md); contrato HTTP em [`API.md`](API.md); decisões em
> [`adr/`](README.md#adrs); execução em [`DEVELOPMENT.md`](DEVELOPMENT.md); testes em
> [`TESTS.md`](TESTS.md). Índice geral em [`README.md`](README.md).

- [1. Contexto e objetivo](#1-contexto-e-objetivo)
- [2. O que construir](#2-o-que-construir)
- [3. Requisitos técnicos](#3-requisitos-técnicos)
- [4. A origem: o capítulo 8 do Alex Xu](#4-a-origem-o-capítulo-8-do-alex-xu)
- [5. O que ficou de fora, e por quê](#5-o-que-ficou-de-fora-e-por-quê)
- [6. Critérios de aceite](#6-critérios-de-aceite)

## 1. Contexto e objetivo

Um encurtador de URL é um problema pequeno o bastante para caber inteiro na cabeça e grande o
bastante para conter quase toda a lista de armadilhas de um serviço web real: **geração de
identificador sem colisão**, **condição de corrida entre duas requisições simultâneas**, **escrita
no caminho de leitura**, **cache de redirect no navegador** e **validação de destino como
superfície de ataque**. É por isso que ele é o exercício canônico de *system design*, e é por isso
que este projeto o constrói do zero em vez de instalar um pronto.

**O projeto é pequeno de propósito, e isso é o ponto.** Ele não é julgado pelo tanto que faz; é
julgado pelo tanto que cada decisão consegue ser justificada. Quatro rotas com testes de integração
contra um banco de verdade, um CI que barra o merge e uma documentação que explica os trade-offs
valem mais aqui do que vinte rotas sem nada disso.

Objetivo de aprendizado: **Python** moderno (3.13, `typing.Protocol`, dataclasses congeladas),
**FastAPI** e Pydantic v2, **SQLAlchemy 2.0** e Alembic sobre **PostgreSQL**, **Testcontainers**,
**Docker** e **CI** — e a arquitetura hexagonal que faz as três primeiras coisas serem trocáveis
sem que a quarta perceba.

## 2. O que construir

Requisitos funcionais, e nada além deles:

1. **Encurtar** — `POST /links` recebe a URL longa, devolve o código de sete caracteres e a URL
   curta montada. A mesma URL longa enviada duas vezes devolve **o mesmo código**, e cria **uma
   linha só**.
2. **Redirecionar** — `GET /{code}` responde `302` com `Location` apontando para o destino.
3. **Registrar o acesso** — cada redirect grava uma linha de clique, com data, `user-agent`,
   `referer` e IP de origem.
4. **Consultar** — `GET /links/{code}` devolve destino, data de criação e o **total de acessos**.
5. **Recusar destino inválido** — uma URL que não seja `http`/`https`, ou que aponte para dentro da
   própria infraestrutura, é recusada com erro de negócio e nunca vira link.
6. **Reportar saúde** — `GET /health` diz se o serviço consegue falar com o banco, e responde `503`
   quando não consegue.

## 3. Requisitos técnicos

- **Arquitetura hexagonal** (ports & adapters) com dependências apontando para dentro
  (`adapter -> application -> domain`), e o domínio importando **só a biblioteca padrão**.
- A regra de dependência **verificada por ferramenta**, não por convenção — um contrato que roda no
  CI e reprova o merge.
- **Deduplicação garantida pelo banco**, por constraint, e não por uma checagem em Python.
- **Schema por migration** (Alembic), aplicada como passo de deploy — nunca por `create_all()`, nem
  mesmo nos testes.
- **Testes de integração contra um PostgreSQL de verdade**, subido pela própria suíte
  (Testcontainers), verificando **estado do banco** e não valor de retorno.
- **Erros num envelope único** — Problem Details (RFC 7807), `application/problem+json`, sem
  exceção.
- **Um comando** sobe tudo: `docker compose up`.
- **CI no GitHub Actions** barrando o merge: lint, formatação, tipos, contratos de arquitetura,
  testes unitários, testes de integração e a imagem construída e exercitada.
- **Nenhum segredo no código.** Configuração por variável de ambiente.

## 4. A origem: o capítulo 8 do Alex Xu

O desenho do código curto segue o capítulo 8 — *Design a URL Shortener* — de **System Design
Interview**, de Alex Xu. O que foi mantido é o núcleo do algoritmo; o que foi tirado só existe lá
por causa de escala que este projeto não tem.

**O que foi mantido:**

| Peça | Como está aqui |
|---|---|
| Alfabeto de **62 caracteres** (`0-9a-zA-Z`) | `domain/service/base62.py` |
| Comprimento **7**, e o dimensionamento que o justifica | `62^7` é cerca de `3,52e12`; `62^6` daria `5,68e10`, curto demais para a projeção de dez anos do capítulo |
| **Id sequencial convertido para base 62**, em vez de hash da URL com resolução de colisão | O id vem da `BIGSERIAL`; colisão é impossível por construção, e não apenas improvável |
| A discussão **301 versus 302** | Resolvida em `302`, e o motivo está na [ADR-0001](adr/0001-redirect-302.md) |

**O que foi tirado, e o que cada peça resolvia lá:**

| Peça do capítulo | O que ela resolve | Por que sai daqui |
|---|---|---|
| **Gerador de id distribuído** (Snowflake) | Vários nós escrevendo precisam de ids únicos sem coordenar entre si | Há **um** PostgreSQL escrevendo. A `BIGSERIAL` já **é** o gerador, é transacional e é de graça. Um Snowflake aqui seria complexidade sem premissa |
| **Cache Redis** na frente da leitura | Absorver o redirect, que é o caminho quente | Sem número de tráfego, um cache é uma segunda fonte de verdade e um problema de invalidação comprados de graça. O repositório está atrás de uma porta: quando o número existir, o cache entra como implementação nova e **nenhuma outra camada muda** |
| **Bloom filter** | Perguntar "esse código já existe?" sem ir ao banco | A pergunta não existe aqui. O código não é escolhido, é derivado de um id que o banco acabou de emitir |
| **Sharding** | Volume que não cabe numa instância | Problema de volume que este projeto não tem, e cuja solução torna toda consulta mais cara |

Saber **quais peças saíram e por quê** é o resultado mais valioso deste projeto. Cada uma tem
resposta pronta na tabela **"o que ficou de fora"** do [`README.md`](../README.md) da raiz.

## 5. O que ficou de fora, e por quê

Além das peças de escala acima, o escopo corta funcionalidade de propósito: sem interface web, sem
fila, sem expiração de link, sem alias customizado, sem rotas de estatística, sem autenticação, sem
limite de taxa e sem nenhum LLM.

Cada corte tem justificativa e um lugar para onde foi — a tabela do [`README.md`](../README.md) da
raiz carrega a resposta curta, e [`PROGRESS-V2.md`](PROGRESS-V2.md) carrega o item de roadmap
correspondente. **As duas coisas andam juntas:** puxar um item para o código sem tirar a linha
correspondente da tabela deixa o README mentindo.

## 6. Critérios de aceite

- [x] `POST /links` com uma URL nova responde **`201 Created`**, com `Location` para os metadados.
- [x] `POST /links` com uma URL já encurtada responde **`200 OK`** e **o mesmo código** — e o banco
      continua com **uma linha**.
- [x] Oito requisições **simultâneas** com a mesma URL criam **exatamente um** link.
- [x] `GET /{code}` responde **`302`** com `Location` para o destino, e nunca `301` nem `307`.
- [x] Cada redirect deixa **uma linha nova** em `click`, e `GET /links/{code}` a conta.
- [x] `javascript:`, `file://`, `localhost` e faixas de IP privadas são **recusados** com `400` no
      envelope Problem Details.
- [x] Um corpo malformado responde **`422`** — e não `400` — no mesmo envelope.
- [x] `GET /health` responde **`503`** com o banco fora, e volta a `200` quando ele retorna.
- [x] O domínio não importa nenhum framework, e uma ferramenta prova isso no CI.
- [x] `docker compose up` num clone limpo sobe banco, migration e API, **nessa ordem**, sem nenhum
      passo manual — e uma migration que falha impede a API de subir.
- [x] `uv run pytest -m ""` verde, com os dois gates de cobertura em **100%**.
- [ ] O pipeline verde num pull request, barrando o merge quando vermelho — verificável só depois
      do `push`, que é passo manual fora deste repositório.
